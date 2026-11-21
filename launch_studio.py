"""Start the local studio and open the prompt gallery."""
import filecmp
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORTABLE = ROOT / "ComfyUI_windows_portable"
URL = "http://127.0.0.1:8188/studio"
LOG = ROOT / "studio.log"


def ready():
    try:
        with urllib.request.urlopen(URL + "/api/models", timeout=2) as response:
            return "fp8" in json.load(response)
    except (OSError, ValueError):
        return False


def main():
    if not ready():
        source = ROOT / "custom_nodes" / "imagemagic_studio"
        installed = PORTABLE / "ComfyUI" / "custom_nodes" / source.name
        installed.mkdir(exist_ok=True)
        for name in ("__init__.py", "studio.html"):
            dest = installed / name
            if not dest.exists() or not filecmp.cmp(source / name, dest, shallow=False):
                shutil.copyfile(source / name, dest)
        print("Starting ImageMagic on your GPU…", flush=True)
        with LOG.open("ab") as log:
            process = subprocess.Popen(
                [str(PORTABLE / "python_embeded/python.exe"), "-s", "ComfyUI/main.py",
                 "--windows-standalone-build", "--disable-auto-launch",
                 "--listen", "127.0.0.1", "--port", "8188"],
                cwd=PORTABLE, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        for _ in range(180):
            if ready():
                break
            if process.poll() is not None:
                raise SystemExit(f"ComfyUI stopped during startup. See {LOG}")
            time.sleep(1)
        else:
            raise SystemExit(f"ComfyUI is still starting. See {LOG}")
    print(URL, flush=True)
    if "--no-browser" not in sys.argv:
        webbrowser.open(URL)


if __name__ == "__main__":
    main()
