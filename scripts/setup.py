"""Windows native, project-local online preparation. Does not change system settings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str | Path], cwd: Path = ROOT) -> None:
    print("\n> " + subprocess.list2cmdline([str(part) for part in command]), flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def create_environment(path: Path) -> Path:
    executable = path / "Scripts/python.exe"
    if not executable.is_file():
        venv.EnvBuilder(with_pip=True).create(path)
    run([executable, "-c", "import sys; assert sys.version_info[:2] == (3,12), 'Use Python 3.12 for both environments'"])
    run([executable, "-m", "pip", "install", "pip==25.3"])
    return executable


def freeze(executable: Path, name: str) -> None:
    output = ROOT / "data/install"
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(executable), "-m", "pip", "freeze"], check=True, capture_output=True, text=True)
    (output / name).write_text(result.stdout, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--ui-only", action="store_true")
    parser.add_argument("--models", choices=("all", "image", "video", "ref2va"), default="all")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or platform.architecture()[0] != "64bit":
        raise RuntimeError("Install Python 3.12 x64; e.g. setup.ps1 -Python C:\\Python312\\python.exe")
    if os.name != "nt":
        raise RuntimeError("These deployment scripts target Windows 11 x64")
    if not args.ui_only and not shutil.which("git"):
        raise RuntimeError("Install Git for Windows from git-scm.com, reopen the terminal, and retry")
    if not args.skip_models and not args.ui_only:
        free = shutil.disk_usage(ROOT).free
        if free < 150 * 1024**3:
            raise RuntimeError("Full setup needs at least 150 GiB free; 200 GB or more is recommended. Use --skip-models to install first.")
    app_python = create_environment(ROOT / ".venv")
    run([app_python, "-m", "pip", "install", "-r", ROOT / "requirements.txt"])
    run([app_python, "-m", "pip", "check"])
    freeze(app_python, "app-freeze.txt")
    if args.ui_only:
        print("UI-only setup complete. Run start.bat -UiOnly (no model inference).")
        return 0
    lock = json.loads((ROOT / "runtime-lock.json").read_text(encoding="utf-8"))
    engine = ROOT / "engine/ComfyUI"
    if not engine.exists():
        engine.mkdir(parents=True)
        run(["git", "init", engine])
        run(["git", "-C", engine, "remote", "add", "origin", lock["comfyui"]["repository"]])
    if not (engine / ".git").is_dir():
        raise RuntimeError(f"{engine} is not a Git checkout; move it aside and retry")
    changes = subprocess.check_output(["git", "-C", str(engine), "status", "--porcelain", "--untracked-files=no"], text=True)
    if changes.strip():
        raise RuntimeError("ComfyUI has local tracked changes; setup will not overwrite them")
    run(["git", "-C", engine, "fetch", "--depth", "1", "origin", lock["comfyui"]["commit"]])
    run(["git", "-C", engine, "checkout", "--detach", lock["comfyui"]["commit"]])
    actual = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
    if actual != lock["comfyui"]["commit"]:
        raise RuntimeError("ComfyUI source revision did not match the lock")
    engine_python = create_environment(ROOT / "engine/.venv")
    torch = lock["pytorch"]
    run([engine_python, "-m", "pip", "install", f"torch=={torch['torch']}", f"torchvision=={torch['torchvision']}", "--index-url", torch["index_url"]])
    run([engine_python, "-m", "pip", "install", "-r", engine / "requirements.txt", "-c", ROOT / "scripts/engine-constraints.txt"])
    run([engine_python, "-m", "pip", "check"])
    freeze(engine_python, "engine-freeze.txt")
    run([engine_python, "-c", "import torch; print('PyTorch:',torch.__version__,'CUDA:',torch.version.cuda); assert torch.cuda.is_available(), 'CUDA unavailable: check the installed NVIDIA driver'; print(torch.cuda.get_device_name(0), round(torch.cuda.get_device_properties(0).total_memory / 1024**3,1), 'GiB VRAM')"])
    if not args.skip_models:
        run([app_python, ROOT / "scripts/download_models.py", "--models", args.models])
    print("Setup complete. Run start.bat" + (" after downloading models." if args.skip_models else "."))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
