"""Download only pinned local model files; --check never uses the network."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def model_files(selection: str = "all", manifest: Path | None = None) -> list[dict]:
    document = json.loads((manifest or ROOT / "runtime/models.json").read_text(encoding="utf-8"))
    unique: dict[tuple[str, str], dict] = {}
    for model in document["models"]:
        if selection != "all" and model["id"] != selection:
            continue
        for entry in model["files"]:
            item = dict(entry)
            if item["folder"] not in {"diffusion_models", "text_encoders", "vae"}:
                raise ValueError("Unknown model folder")
            if Path(item["filename"]).name != item["filename"] or "/" in item["filename"] or "\\" in item["filename"]:
                raise ValueError("Unsafe model filename")
            if not re.fullmatch(r"[0-9a-f]{40}", item.get("revision", "")):
                raise ValueError("Each model must pin a 40-character repository revision")
            if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) or item.get("size_bytes", 0) <= 0:
                raise ValueError("Each model must pin its SHA256 and byte size")
            key = item["folder"], item["filename"]
            if key in unique and (unique[key]["sha256"], unique[key]["size_bytes"]) != (item["sha256"], item["size_bytes"]):
                raise ValueError(f"Conflicting model files: {key}")
            unique[key] = item
    if not unique:
        raise ValueError(f"No models selected: {selection}")
    return list(unique.values())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_files(files: list[dict], models_dir: Path, full_hash: bool = False) -> list[str]:
    failures = []
    for entry in files:
        path = models_dir / entry["folder"] / entry["filename"]
        if not path.is_file():
            failures.append(f"MISSING {path.name}")
        elif path.stat().st_size != entry["size_bytes"]:
            failures.append(f"SIZE MISMATCH {path.name}")
        elif full_hash and sha256(path) != entry["sha256"]:
            failures.append(f"SHA256 MISMATCH {path.name}")
    return failures


def download(selection: str, models_dir: Path) -> None:
    files = model_files(selection)
    models_dir.mkdir(parents=True, exist_ok=True)
    print("Verifying existing files; hashing the full shared encoder can take a few minutes ...", flush=True)
    missing = [entry for entry in files if inspect_files([entry], models_dir, full_hash=True)]
    required = sum(entry["size_bytes"] for entry in missing) + 20 * 1024**3
    free = shutil.disk_usage(models_dir).free
    print(f"Unique model total: {sum(e['size_bytes'] for e in files) / 1e9:.2f} GB. Free: {free / 1e9:.1f} GB.", flush=True)
    if free < required:
        raise RuntimeError(f"Need at least {required / 1e9:.1f} GB free for missing files and working space")
    cache = ROOT / "data/downloads"
    os.environ.setdefault("HF_XET_CACHE", str(cache / "xet"))
    os.environ.setdefault("HF_XET_CHUNK_CACHE_SIZE_BYTES", "0")
    from huggingface_hub import hf_hub_download

    for entry in files:
        target = models_dir / entry["folder"] / entry["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry not in missing:
            print(f"Verified, skipped: {target.name}", flush=True)
            continue
        staging = cache / entry["repo_id"].replace("/", "--") / entry["revision"]
        print(f"Downloading {entry['repo_id']}/{entry['path']} ({entry['size_bytes'] / 1e9:.2f} GB)", flush=True)
        downloaded = Path(hf_hub_download(
            repo_id=entry["repo_id"], filename=entry["path"], revision=entry["revision"],
            local_dir=str(staging), local_files_only=False,
        ))
        if downloaded.stat().st_size != entry["size_bytes"] or sha256(downloaded) != entry["sha256"]:
            raise RuntimeError(f"Integrity verification failed: {downloaded}; remove the damaged staging file and retry")
        # Staging is inside this project, so atomic replace needs no second full copy.
        os.replace(downloaded, target)
        print(f"SHA256 OK: {target.name}", flush=True)
    print("All selected model files are ready for offline use.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", choices=("all", "image", "video", "ref2va"), default="all")
    parser.add_argument("--models-dir", type=Path, default=ROOT / "engine/ComfyUI/models")
    parser.add_argument("--check", action="store_true", help="Offline file existence and size check")
    parser.add_argument("--sha256", action="store_true", help="Also hash all files during --check")
    args = parser.parse_args()
    try:
        if args.check:
            failures = inspect_files(model_files(args.models), args.models_dir, args.sha256)
            for failure in failures:
                print(failure)
            if failures:
                return 1
            print("Offline model check passed" + (" (SHA256)" if args.sha256 else " (size; use --sha256 for full integrity)"))
        else:
            download(args.models, args.models_dir)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Model preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
