"""Start the desktop studio or its per-installation inference service."""
import errno
import filecmp
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil
from filelock import FileLock

ROOT = Path(__file__).resolve().parent
PORTABLE = ROOT / "ComfyUI_windows_portable"
PYTHON = PORTABLE / "python_embeded/python.exe"
HOST = "127.0.0.1"
DEFAULT_PORT = 8188
LOG = ROOT / "studio.log"
NODE_FILES = ("__init__.py", "storage.py", "session_nodes.py")
SOURCE = ROOT / "custom_nodes/imagemagic_studio"
INSTALLED = PORTABLE / "ComfyUI/custom_nodes/imagemagic_studio"


def ready(port):
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/studio/api/models", timeout=2) as response:
            return isinstance(json.load(response), dict)
    except (OSError, ValueError):
        return False


def running_studio():
    for conn in psutil.net_connections(kind="tcp4"):
        if conn.status != psutil.CONN_LISTEN or conn.laddr.ip != HOST or not conn.pid:
            continue
        try:
            process = psutil.Process(conn.pid)
            executable = Path(process.exe())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if executable == PYTHON and ready(conn.laddr.port):
            return conn.laddr.port, process
    return None


def running_port():
    studio = running_studio()
    return studio[0] if studio else None


def stop_studio():
    studio = running_studio()
    if not studio:
        return
    port, process = studio
    with urllib.request.urlopen(f"http://{HOST}:{port}/queue", timeout=5) as response:
        queue = json.load(response)
    if queue["queue_running"] or queue["queue_pending"]:
        raise SystemExit("ImageMagic still has jobs. Wait for them to finish and try again.")
    process.terminate()
    process.wait(timeout=15)


def port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((HOST, port))
        except OSError as error:
            if error.errno in (errno.EADDRINUSE, errno.EACCES):
                return False
            raise
        return True


def needs_update():
    return any(not (INSTALLED / name).is_file() or
               not filecmp.cmp(SOURCE / name, INSTALLED / name, shallow=False) for name in NODE_FILES)


def start_studio():
    INSTALLED.mkdir(exist_ok=True)
    for name in NODE_FILES:
        shutil.copyfile(SOURCE / name, INSTALLED / name)
    print("Starting ImageMagic on your GPU...", flush=True)
    for port in range(DEFAULT_PORT, 65536):
        if not port_available(port):
            continue
        with LOG.open("ab") as log:
            process = subprocess.Popen(
                [str(PYTHON), "-s", "ComfyUI/main.py",
                 "--windows-standalone-build", "--disable-auto-launch",
                 "--listen", HOST, "--port", str(port)],
                cwd=PORTABLE, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        for _ in range(180):
            if process.poll() is not None:
                if not port_available(port):
                    break  # Another app claimed this port during ComfyUI startup.
                raise SystemExit(f"ComfyUI stopped during startup. See {LOG}")
            if running_port() == port:
                return port
            time.sleep(1)
        else:
            process.terminate()
            process.wait()
            raise SystemExit(f"ComfyUI timed out starting on port {port}. See {LOG}")
    raise SystemExit("No available local port for ImageMagic.")


def main():
    if not {"--stop", "--server-only", "--no-browser"}.intersection(sys.argv):
        desktop = ROOT / "ImageMagic.exe"
        if not desktop.is_file():
            subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "RemoteSigned",
                            "-File", str(ROOT / "desktop/build.ps1")], check=True)
        subprocess.Popen([str(desktop)], cwd=ROOT)
        return
    # Serialize discovery and startup across installs, including simultaneous double-clicks.
    with FileLock(Path(tempfile.gettempdir()) / "ImageMagic-launcher.lock"):
        if "--stop" in sys.argv:
            stop_studio()
            return
        port = running_port()
        if port and needs_update():
            stop_studio()
            port = None
        port = port or start_studio()
    print(port, flush=True)


if __name__ == "__main__":
    main()
