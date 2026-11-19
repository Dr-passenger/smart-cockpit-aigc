from __future__ import annotations

import json
import platform
import shutil
import subprocess

import psutil

from .comfy_client import ComfyClient, EngineError
from .config import Settings


def model_inventory(settings: Settings):
    manifest_path = settings.base_dir / "runtime" / "models.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    models = []
    for model in manifest["models"]:
        files = []
        for item in model["files"]:
            target = settings.comfy_dir / "models" / item["folder"] / item["filename"]
            present = target.is_file() and target.stat().st_size > 0
            expected = item.get("size_bytes")
            if present and expected:
                present = target.stat().st_size == expected
            files.append({"filename": item["filename"], "folder": item["folder"],
                          "ready": present, "size_bytes": expected})
        models.append({"id": model["id"], "name": model["name"], "files": files,
                       "ready": bool(files) and all(f["ready"] for f in files),
                       "message": model.get("notes", "16GB 显存未实机验证，请先用低分辨率试跑")})
    return models


def inspect_system(settings: Settings, engine: ComfyClient):
    stats = None
    message = ""
    try:
        stats = engine.system_stats()
        message = "本机 ComfyUI 已连接；模型按需加载，任务串行执行"
    except EngineError as exc:
        message = str(exc)
    gpu = None
    if stats:
        for device in stats.get("devices", []):
            if device.get("type") in {"cuda", "hip"}:
                gpu = {"name": device.get("name", "GPU"),
                       "vram_gb": round(device.get("vram_total", 0) / 1024**3, 1)}
                break
    if gpu is None and shutil.which("nvidia-smi"):
        try:
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if platform.system() == "Windows" else {}
            result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                    capture_output=True, text=True, timeout=5, **flags)
            if result.returncode == 0 and result.stdout.strip():
                name, memory = result.stdout.splitlines()[0].rsplit(",", 1)
                gpu = {"name": name.strip(), "vram_gb": round(float(memory) / 1024, 1)}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    models = model_inventory(settings)
    return {
        "gpu": gpu, "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "platform": platform.platform(), "offline": True,
        "backends": {"local": {"available": bool(stats), "message": message}},
        "models": models,
        "defaults": {"image": {"width": 1024, "height": 1024, "steps": 6},
                     "video": {"width": 512, "height": 512, "steps": 20, "duration": 4},
                     "ref2va": {"width": 512, "height": 512, "steps": 20, "duration": 4, "max_references": 9}},
        "warning": "完整模型大于16GB显存，使用 Comfy 官方量化和动态卸载；64GB内存下仍可能OOM或很慢。此配置未在目标GPU实测。",
    }
