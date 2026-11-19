from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    data_dir: Path = Path(os.environ.get("STUDIO_DATA_DIR", str(BASE_DIR / "data")))
    comfy_dir: Path = Path(os.environ.get("COMFY_DIR", str(BASE_DIR / "engine" / "ComfyUI")))
    comfy_url: str = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
    port: int = int(os.environ.get("STUDIO_PORT", "8230"))
    job_timeout: int = int(os.environ.get("STUDIO_JOB_TIMEOUT", "86400"))
    unload_after_job: bool = os.environ.get("STUDIO_UNLOAD_AFTER_JOB", "1") == "1"

    def __post_init__(self):
        url = urlsplit(self.comfy_url)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username or url.password or url.path not in {"", "/"}
                or url.query or url.fragment):
            raise ValueError("COMFY_URL 必须是本机回环 HTTP 地址，例如 http://127.0.0.1:8188")
        if not 1024 <= self.port <= 65535:
            raise ValueError("STUDIO_PORT 必须在 1024..65535")

    def prepare(self):
        for name in ("jobs", "assets", "outputs"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
