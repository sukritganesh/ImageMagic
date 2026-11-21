"""Start the local studio and open the prompt gallery."""
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
import webbrowser
from pathlib import Path

import psutil
from filelock import FileLock

ROOT = Path(__file__).resolve().parent
PORTABLE = ROOT / "ComfyUI_windows_portable"
PYTHON = PORTABLE / "python_embeded/python.exe"
HOST = "127.0.0.1"
DEFAULT_PORT = 8188
LOG = ROOT / "studio.log"


def ready(port):
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/studio/api/models", timeout=2) as response:
            return isinstance(json.load(response), dict)
    except (OSError, ValueError):
        return False


def running_port():
    for conn in psutil.net_connections(kind="tcp4"):
        if conn.status != psutil.CONN_LISTEN or conn.laddr.ip != HOST or not conn.pid:
            continue
        try:
            executable = Path(psutil.Process(conn.pid).exe())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if executable == PYTHON and ready(conn.laddr.port):
            return conn.laddr.port
    return None


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


def start_studio():
    source = ROOT / "custom_nodes" / "imagemagic_studio"
    installed = PORTABLE / "ComfyUI" / "custom_nodes" / source.name
    installed.mkdir(exist_ok=True)
    for name in ("__init__.py", "studio.html", "sessions.html", "style.css"):
        dest = installed / name
        if not dest.exists() or not filecmp.cmp(source / name, dest, shallow=False):
            shutil.copyfile(source / name, dest)
    print("Starting ImageMagic on your GPU…", flush=True)
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
    # Serialize discovery and startup across installs, including simultaneous double-clicks.
    with FileLock(Path(tempfile.gettempdir()) / "ImageMagic-launcher.lock"):
        port = running_port() or start_studio()
    url = f"http://{HOST}:{port}/studio"
    print(url, flush=True)
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)


if __name__ == "__main__":
    main()
