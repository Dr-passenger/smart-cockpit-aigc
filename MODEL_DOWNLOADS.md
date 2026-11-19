# 智能座舱AIGC · 模型下载地址与部署清单

> 本文件由 `scripts/export_model_list.py` 从 [runtime/models.json](runtime/models.json) 自动生成。修改模型信息时只编辑 JSON，然后重新生成；下载器也直接读取同一 JSON。

清单核查日期：2026-11-19。去重后 **7 个文件，共 94,646,241,490 字节（94.646241490 GB / 88.146181 GiB）**。GB 为十进制，GiB 为二进制并显示至小数点后六位；精确字节数是校验依据。共享编码器和 VAE 只下载一次。

## 按清单一键部署

1. 在目标 Windows 11 笔记本安装 Python 3.12 x64、Git for Windows，预留至少 200GB 空闲空间。完整安装会检查至少 150GiB 空闲。
2. 在本项目目录双击 `setup.bat`：安装应用和本机 ComfyUI 引擎，自动按 JSON 下载全部模型，校验精确大小及 SHA256，并放入下表目录。无需逐个手动下载。
3. 安装成功后双击 `start.bat`，浏览器打开 `http://127.0.0.1:8230`。此后可断网进行本地生成。

首次准备需要联网访问 GitHub、PyPI、PyTorch 和 Hugging Face；准备完毕后的推理使用本机权重，无云端 API。16GB 显存目标机尚未实际验证，加载和视频生成可能很慢或内存不足。

按组选择（在项目目录的终端执行）：

```powershell
.\setup.bat -Models image
.\setup.bat -Models video
.\setup.bat -Models ref2va
```

`image` 为 H3-Image；`video` 仅为 FL2VA 文生/首帧视频；`ref2va` 为独立 Ref2VA 多参考视频。默认 `all` 下载三组并去重共享文件。

仅下载权重而暂不安装 PyTorch：先运行 `setup.bat -UiOnly` 创建轻量应用环境，再双击 `download-models.bat`；指定组可执行 `download-models.bat --models ref2va`。仅完成下载不代表已具备生成引擎，之后仍需完整 `setup.bat -SkipModels`。

## 完整文件表

所有存放位置相对于项目目录 `minimax-h3-studio/`。下载直链固定到已核查 revision，避免 `main` 后续变化。浏览器手动下载时保留完整文件名，按表放置，最后执行下方离线校验。

| 文件名称 | 用途 / 模型组 | 精确字节数 | GB / GiB | 官方仓库 | 固定 revision | 下载 | 存放相对位置 |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| `minimax_h3_image_pruned_int8_convrot.safetensors` | DiT 扩散模型 / image | 20,979,314,802 | 20.979314802 GB / 19.538509 GiB | [Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image) | `89c635085f539d03ad35485ed542c5a286e3c6d6` | [固定版本直链](https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/89c635085f539d03ad35485ed542c5a286e3c6d6/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors?download=true) | `engine/ComfyUI/models/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors` |
| `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | 共享文本与图像编码器 / image、video、ref2va | 27,141,342,152 | 27.141342152 GB / 25.277345 GiB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) | `4b53a35191437de05370da548e59aeabe2a5a09a` | [固定版本直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors?download=true) | `engine/ComfyUI/models/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors` |
| `minimax_h3_image_vae_fp16.safetensors` | 图像 VAE / image | 1,168,505,312 | 1.168505312 GB / 1.088255 GiB | [Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image) | `89c635085f539d03ad35485ed542c5a286e3c6d6` | [固定版本直链](https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/89c635085f539d03ad35485ed542c5a286e3c6d6/vae/minimax_h3_image_vae_fp16.safetensors?download=true) | `engine/ComfyUI/models/vae/minimax_h3_image_vae_fp16.safetensors` |
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | DiT 扩散模型 / video | 20,970,379,616 | 20.970379616 GB / 19.530188 GiB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) | `4b53a35191437de05370da548e59aeabe2a5a09a` | [固定版本直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors?download=true) | `engine/ComfyUI/models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| `minimax_h3_video_vae_int8_convrot.safetensors` | 视频 VAE / video、ref2va | 2,811,065,184 | 2.811065184 GB / 2.618008 GiB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) | `4b53a35191437de05370da548e59aeabe2a5a09a` | [固定版本直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/vae/minimax_h3_video_vae_int8_convrot.safetensors?download=true) | `engine/ComfyUI/models/vae/minimax_h3_video_vae_int8_convrot.safetensors` |
| `minimax_h3_audio_vae_fp32.safetensors` | 音频 VAE / video、ref2va | 605,254,808 | 0.605254808 GB / 0.563687 GiB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) | `4b53a35191437de05370da548e59aeabe2a5a09a` | [固定版本直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/vae/minimax_h3_audio_vae_fp32.safetensors?download=true) | `engine/ComfyUI/models/vae/minimax_h3_audio_vae_fp32.safetensors` |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | DiT 扩散模型 / ref2va | 20,970,379,616 | 20.970379616 GB / 19.530188 GiB | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) | `4b53a35191437de05370da548e59aeabe2a5a09a` | [固定版本直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/4b53a35191437de05370da548e59aeabe2a5a09a/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors?download=true) | `engine/ComfyUI/models/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors` |

<details>
<summary>展开全部文件的 SHA256（下载器会自动核对）</summary>

```text
83eb140f1ff95c068f8a6886e6d3f3d0d4ab2e07bb2fe6d2ef992a51146ee622  engine/ComfyUI/models/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors
bc2ced0fbea64757fa9acddccfc0b3f4819d1dcf1da6c124d690d368be283923  engine/ComfyUI/models/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors
d80e9c2e5cfc9844869961ff5a58c9a9e52182df6bfb30b26018dd7f348721af  engine/ComfyUI/models/vae/minimax_h3_image_vae_fp16.safetensors
e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a  engine/ComfyUI/models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors
52a2c8c73583c86e4f41cdcce3a6ad0ea562987bc0bf3d60a0cef5f5c8e60c0e  engine/ComfyUI/models/vae/minimax_h3_video_vae_int8_convrot.safetensors
8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48  engine/ComfyUI/models/vae/minimax_h3_audio_vae_fp32.safetensors
9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779  engine/ComfyUI/models/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors
```

</details>

## 离线校验与维护

```powershell
# 不联网，检查全部文件的精确大小及 SHA256
.\.venv\Scripts\python.exe scripts\download_models.py --check --sha256

# 仅校验 Ref2VA 与其必需共享文件
.\.venv\Scripts\python.exe scripts\download_models.py --models ref2va --check --sha256

# 维护清单后重新生成此文档，无需安装第三方库
py -3.12 scripts\export_model_list.py

# 检查文档是否与 JSON 一致，不修改文件
py -3.12 scripts\export_model_list.py --check
```

权重文件与虚拟环境不包含在源码仓库中。GitHub 保存下载地址、固定版本、SHA256、下载器及部署代码；实际权重从上表官方仓库下载。更完整的步骤见 [README](README.md) 和 [离线转移说明](docs/offline.md)。
