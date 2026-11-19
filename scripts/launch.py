"""Supervise the offline engine and Intelligent Cockpit AIGC; stop both on Ctrl+C or failure."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from download_models import inspect_files, model_files

ROOT = Path(__file__).resolve().parents[1]


def assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"127.0.0.1:{port} is already in use. Close its owner or choose another port; no existing process will be killed.") from exc


def wait_ready(process: subprocess.Popen, url: str, seconds: int, name: str) -> None:
    deadline = time.monotonic() + seconds
    next_notice = 0.0
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"{name} exited during startup (code {code}). See data/logs.")
        try:
            with opener.open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        if time.monotonic() >= next_notice:
            print(f"Waiting for {name} at {url} ...", flush=True)
            next_notice = time.monotonic() + 15
        time.sleep(0.5)
    raise RuntimeError(f"{name} did not become ready within {seconds}s. See data/logs.")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        if os.name == "nt":
            # Only the process tree created by this launcher is targeted.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui-only", action="store_true")
    parser.add_argument("--verify-hashes", action="store_true")
    parser.add_argument("--fast-disk", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--models", choices=("all", "image", "video", "ref2va"), default="all")
    parser.add_argument("--studio-port", type=int, default=8230)
    parser.add_argument("--engine-port", type=int, default=8188)
    args = parser.parse_args()
    if any(not 1024 <= port <= 65535 for port in (args.studio_port, args.engine_port)) or args.studio_port == args.engine_port:
        raise RuntimeError("Choose two different ports in the range 1024..65535")
    assert_port_free(args.studio_port)
    if not args.ui_only:
        assert_port_free(args.engine_port)
    env = os.environ.copy()
    env.update({
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1", "COMFYUI_DISABLE_PRODUCT_TIPS": "1",
        "COMFY_URL": f"http://127.0.0.1:{args.engine_port}",
        "COMFY_DIR": str(ROOT / "engine/ComfyUI"), "STUDIO_HOST": "127.0.0.1",
        "STUDIO_PORT": str(args.studio_port), "STUDIO_DATA_DIR": str(ROOT / "data"),
        "NO_PROXY": "127.0.0.1,localhost,::1", "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1",
    })
    env.setdefault("STUDIO_JOB_TIMEOUT", "86400")
    env.setdefault("STUDIO_UNLOAD_AFTER_JOB", "1")
    engine_python = ROOT / "engine/.venv/Scripts/python.exe"
    engine = ROOT / "engine/ComfyUI"
    if not args.ui_only:
        if not engine_python.is_file() or not (engine / "main.py").is_file():
            raise RuntimeError("ComfyUI is not installed. Run setup.bat first, or use start.bat -UiOnly for the interface.")
        lock = json.loads((ROOT / "runtime-lock.json").read_text(encoding="utf-8"))
        source_head = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
        if source_head != lock["comfyui"]["commit"]:
            raise RuntimeError("ComfyUI revision differs from runtime-lock.json. Run setup.bat -SkipModels to restore the pinned revision.")
        print("Checking local model files" + (" and full SHA256 hashes ..." if args.verify_hashes else " (size only) ..."), flush=True)
        failures = inspect_files(model_files(args.models), engine / "models", args.verify_hashes)
        if failures:
            raise RuntimeError("Model preflight failed:\n" + "\n".join(failures) + "\nRun .venv\\Scripts\\python.exe scripts\\download_models.py")
        subprocess.run([str(engine_python), "-c", "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable: inspect NVIDIA driver'; print('GPU:', torch.cuda.get_device_name(0), '| PyTorch', torch.__version__, '| CUDA', torch.version.cuda)"], env=env, check=True)
    logs = ROOT / "data/logs"
    logs.mkdir(parents=True, exist_ok=True)
    children: list[subprocess.Popen] = []
    handles = []
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

    def spawn(command: list[str], name: str, cwd: Path) -> subprocess.Popen:
        log = (logs / f"{name}.log").open("a", encoding="utf-8")
        handles.append(log)
        log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} local launch ===\n")
        log.flush()
        child = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        children.append(child)
        return child

    try:
        if not args.ui_only:
            for directory in ("input", "output", "temp", "user"):
                (ROOT / "data/comfy" / directory).mkdir(parents=True, exist_ok=True)
            command = [str(engine_python), str(engine / "main.py"), "--listen", "127.0.0.1", "--port", str(args.engine_port),
                       "--disable-auto-launch", "--offline", "--disable-all-custom-nodes", "--disable-product-tips",
                       "--reserve-vram", "2", "--cache-none", "--disable-smart-memory", "--preview-method", "none"]
            for directory in ("input", "output", "temp", "user"):
                command.extend([f"--{directory}-directory", str(ROOT / "data/comfy" / directory)])
            if args.fast_disk:
                command.append("--fast-disk")
            child = spawn(command, "engine", engine)
            wait_ready(child, f"http://127.0.0.1:{args.engine_port}/system_stats", 300, "ComfyUI")
        app = spawn([sys.executable, "-m", "backend.main"], "studio", ROOT)
        url = f"http://127.0.0.1:{args.studio_port}"
        wait_ready(app, url + "/api/health", 60, "Intelligent Cockpit AIGC")
        print(f"智能座舱AIGC ready: {url}\nLogs: {logs}\nPress Ctrl+C in this window to stop both services.", flush=True)
        if args.ui_only:
            print("UI-only mode: generation requires completing the engine and model setup.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        while True:
            for child in children:
                code = child.poll()
                if code is not None:
                    raise RuntimeError(f"A local service exited (PID {child.pid}, code {code}). See data/logs.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping local services ...", flush=True)
        return 0
    finally:
        for child in reversed(children):
            stop(child)
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
