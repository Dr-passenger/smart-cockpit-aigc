"""Generate MODEL_DOWNLOADS.md from the pinned model manifest, using only stdlib."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def collect(manifest: dict) -> list[dict]:
    unique = {}
    for model in manifest["models"]:
        for source in model["files"]:
            entry = dict(source)
            if not re.fullmatch(r"[0-9a-f]{40}", entry["revision"]):
                raise ValueError("Every file must pin a full repository commit")
            if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) or entry["size_bytes"] <= 0:
                raise ValueError("Every file must include SHA256 and exact byte size")
            key = entry["folder"], entry["filename"]
            if key not in unique:
                entry["groups"] = []
                unique[key] = entry
            existing = unique[key]
            for field in ("repo_id", "revision", "path", "size_bytes", "sha256"):
                if existing[field] != entry[field]:
                    raise ValueError(f"Conflicting metadata for shared file: {key}")
            if model["id"] not in existing["groups"]:
                existing["groups"].append(model["id"])
    return list(unique.values())


def size_text(size: int) -> str:
    return f"{Decimal(size) / Decimal(10**9):.9f} GB / {Decimal(size) / Decimal(1024**3):.6f} GiB"


def direct_url(entry: dict) -> str:
    return f"https://huggingface.co/{quote(entry['repo_id'], safe='/')}/resolve/{entry['revision']}/{quote(entry['path'], safe='/')}?download=true"


def purpose(entry: dict) -> str:
    if entry["folder"] == "diffusion_models":
        return "DiT 扩散模型"
    if entry["folder"] == "text_encoders":
        return "共享文本与图像编码器"
    return "音频 VAE" if "audio" in entry["filename"] else "图像 VAE" if "image" in entry["filename"] else "视频 VAE"


def render(manifest: dict) -> str:
    files = collect(manifest)
    total = sum(entry["size_bytes"] for entry in files)
    lines = [
        "# 智能座舱AIGC · 模型下载地址与部署清单", "",
        "> 本文件由 `scripts/export_model_list.py` 从 [runtime/models.json](runtime/models.json) 自动生成。修改模型信息时只编辑 JSON，然后重新生成；下载器也直接读取同一 JSON。", "",
        f"清单核查日期：{manifest.get('verified_on', '未记录')}。去重后 **{len(files)} 个文件，共 {total:,} 字节（{size_text(total)}）**。GB 为十进制，GiB 为二进制并显示至小数点后六位；精确字节数是校验依据。共享编码器和 VAE 只下载一次。", "",
        "## 按清单一键部署", "",
        "1. 在目标 Windows 11 笔记本安装 Python 3.12 x64、Git for Windows，预留至少 200GB 空闲空间。完整安装会检查至少 150GiB 空闲。",
        "2. 在本项目目录双击 `setup.bat`：安装应用和本机 ComfyUI 引擎，自动按 JSON 下载全部模型，校验精确大小及 SHA256，并放入下表目录。无需逐个手动下载。",
        "3. 安装成功后双击 `start.bat`，浏览器打开 `http://127.0.0.1:8230`。此后可断网进行本地生成。", "",
        "首次准备需要联网访问 GitHub、PyPI、PyTorch 和 Hugging Face；准备完毕后的推理使用本机权重，无云端 API。16GB 显存目标机尚未实际验证，加载和视频生成可能很慢或内存不足。", "",
        "按组选择（在项目目录的终端执行）：", "",
        "```powershell", ".\\setup.bat -Models image", ".\\setup.bat -Models video", ".\\setup.bat -Models ref2va", "```", "",
        "`image` 为 H3-Image；`video` 仅为 FL2VA 文生/首帧视频；`ref2va` 为独立 Ref2VA 多参考视频。默认 `all` 下载三组并去重共享文件。", "",
        "仅下载权重而暂不安装 PyTorch：先运行 `setup.bat -UiOnly` 创建轻量应用环境，再双击 `download-models.bat`；指定组可执行 `download-models.bat --models ref2va`。仅完成下载不代表已具备生成引擎，之后仍需完整 `setup.bat -SkipModels`。", "",
        "## 完整文件表", "",
        "所有存放位置相对于项目目录 `minimax-h3-studio/`。下载直链固定到已核查 revision，避免 `main` 后续变化。浏览器手动下载时保留完整文件名，按表放置，最后执行下方离线校验。", "",
        "| 文件名称 | 用途 / 模型组 | 精确字节数 | GB / GiB | 官方仓库 | 固定 revision | 下载 | 存放相对位置 |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for entry in files:
        repository = f"https://huggingface.co/{quote(entry['repo_id'], safe='/')}"
        target = f"engine/ComfyUI/models/{entry['folder']}/{entry['filename']}"
        lines.append(f"| `{entry['filename']}` | {purpose(entry)} / {'、'.join(entry['groups'])} | {entry['size_bytes']:,} | {size_text(entry['size_bytes'])} | [{entry['repo_id']}]({repository}) | `{entry['revision']}` | [固定版本直链]({direct_url(entry)}) | `{target}` |")
    lines += ["", "<details>", "<summary>展开全部文件的 SHA256（下载器会自动核对）</summary>", "", "```text"]
    for entry in files:
        lines.append(f"{entry['sha256']}  engine/ComfyUI/models/{entry['folder']}/{entry['filename']}")
    lines += ["```", "", "</details>", "", "## 离线校验与维护", "", "```powershell", "# 不联网，检查全部文件的精确大小及 SHA256", ".\\.venv\\Scripts\\python.exe scripts\\download_models.py --check --sha256", "", "# 仅校验 Ref2VA 与其必需共享文件", ".\\.venv\\Scripts\\python.exe scripts\\download_models.py --models ref2va --check --sha256", "", "# 维护清单后重新生成此文档，无需安装第三方库", "py -3.12 scripts\\export_model_list.py", "", "# 检查文档是否与 JSON 一致，不修改文件", "py -3.12 scripts\\export_model_list.py --check", "```", "", "权重文件与虚拟环境不包含在源码仓库中。GitHub 保存下载地址、固定版本、SHA256、下载器及部署代码；实际权重从上表官方仓库下载。更完整的步骤见 [README](README.md) 和 [离线转移说明](docs/offline.md)。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "runtime/models.json")
    parser.add_argument("--output", type=Path, default=ROOT / "MODEL_DOWNLOADS.md")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render(json.loads(args.manifest.read_text(encoding="utf-8")))
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != expected:
            print("Model download document is stale; run scripts/export_model_list.py", file=sys.stderr)
            return 1
        print("Model download document matches the manifest")
    else:
        args.output.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Generated {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Model list export failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
