"""Build local ComfyUI API prompts using verified core nodes.

Sources (checked 2026-11-19):
https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_minimax_h3_image_t2i.json
https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_i2v.json
https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json
https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy_extras/nodes_minimax_h3.py

The optional prompt expander, LoRAs and all hosted nodes are omitted. The INT8
text encoder is shared by image and video. MiniMax's own VAE always tiles
internally; VAEDecode also streams video chunks into a CPU output buffer. Using
VAEDecodeTiled would not change these models' internal tile sizes and would
introduce an extra full output copy. Offload is still needed in 16 GB VRAM.
"""

from __future__ import annotations

import math
from pathlib import PurePosixPath
from typing import Any

TEXT_ENCODER = "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
IMAGE_MODEL = "minimax_h3_image_pruned_int8_convrot.safetensors"
VIDEO_MODEL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
REFERENCE_VIDEO_MODEL = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
IMAGE_VAE = "minimax_h3_image_vae_fp16.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"


def video_frame_count(duration: float) -> int:
    """Round up to the H3 17k+5 frame grid at its fixed 24 fps."""
    seconds = float(duration)
    if not math.isfinite(seconds) or not 4 <= seconds <= 15:
        raise ValueError("视频时长必须介于 4 和 15 秒之间。")
    frames = max(5, math.ceil(seconds * 24))
    return frames + (5 - frames % 17) % 17


def _node(class_type: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def _dimension(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是 32 的整数倍。")
    number = int(value)
    if float(value) != number or not 32 <= number <= 8192 or number % 32:
        raise ValueError(f"{name} 必须是 32–8192 范围内 32 的整数倍。")
    return number


def _reference(filename: str | None) -> str | None:
    if filename is None:
        return None
    # A Comfy upload result may contain a generated subfolder, but never an
    # absolute path or traversal supplied by the UI.
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (not normalized or path.is_absolute() or ":" in normalized
            or any(part in ("", ".", "..") for part in normalized.split("/"))):
        raise ValueError("参考图必须是 ComfyUI input 目录内的上传文件。")
    return normalized


def required_nodes(model: str, has_reference: bool = False, mode: str | None = None) -> list[str]:
    """Core node classes required by the chosen generated API prompt."""
    common = ["UNETLoader", "CLIPLoader", "VAELoader", "VAEDecode"]
    if model == "image":
        result = common + ["MiniMaxH3ImageConditioning", "ConditioningZeroOut", "KSampler", "SaveImage"]
    elif model == "video":
        conditioning = "MiniMaxH3ReferenceToVideo" if mode == "ref2va" else "MiniMaxH3ImageToVideo"
        result = common + [conditioning, "RandomNoise", "BasicGuider",
                           "KSamplerSelect", "BasicScheduler", "SamplerCustomAdvanced",
                           "VAEDecodeAudio", "CreateVideo", "SaveVideo"]
    else:
        raise ValueError("未知模型，只支持 image 和 video。")
    return result + (["LoadImage"] if has_reference else [])


def build_prompt(request: dict[str, Any], reference_filename: str | None = None,
                 reference_filenames: list[str] | None = None) -> dict[str, Any]:
    """Return a ComfyUI /prompt-compatible node dictionary.

    Request fields: model (image/video), prompt, width, height, seed, steps,
    duration (video seconds), and optional mode (t2i/edit/t2v/i2v/ref2va).
    Ref2VA accepts 1-9 ordered reference pictures; editing accepts up to 16.
    The legacy single filename is prepended if absent from reference_filenames.
    A reference selects editing or first-frame I2V when mode is absent. Image defaults
    to 1024x1024/6 steps; video to 512x512/4 seconds/20 steps. These deliberately
    small canvases are memory probes, below the official native output sizes.
    """
    model = request.get("model", "image")
    if model not in ("image", "video"):
        raise ValueError("未知模型，只支持 image 和 video。")
    prompt = request.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("请填写提示词。")
    if reference_filenames is not None and not isinstance(reference_filenames, list):
        raise ValueError("参考图片必须是按顺序排列的文件名列表。")
    refs: list[str] = []
    filenames = ([reference_filename] if reference_filename is not None else []) + (reference_filenames or [])
    for filename in filenames:
        if not isinstance(filename, str):
            raise ValueError("参考图片文件名无效。")
        normalized = _reference(filename)
        if normalized not in refs:
            refs.append(normalized)
    mode = request.get("mode") or ({"image": "edit", "video": "i2v"}[model] if refs else {"image": "t2i", "video": "t2v"}[model])
    allowed_modes = ("t2i", "edit") if model == "image" else ("t2v", "i2v", "ref2va")
    if mode not in allowed_modes:
        raise ValueError("任务类型与所选模型不匹配。")
    if mode in ("edit", "i2v", "ref2va") and not refs:
        raise ValueError("该任务需要上传参考图片。")
    if mode in ("t2i", "t2v") and refs:
        raise ValueError("纯文本任务不应包含参考图片，请切换到编辑或图生视频。")
    if mode == "i2v" and len(refs) > 1:
        raise ValueError("首帧图生视频只接受 1 张图片；多图参考请选择 Ref2VA。")
    if mode == "ref2va" and len(refs) > 9:
        raise ValueError("Ref2VA 最多接受 9 张参考图片。")
    if mode == "edit" and len(refs) > 16:
        raise ValueError("图像编辑最多接受 16 张参考图片。")
    default_side = 1024 if model == "image" else 512
    width = _dimension(request.get("width", default_side), "宽度")
    height = _dimension(request.get("height", default_side), "高度")
    raw_seed = request.get("seed", 0)
    seed = int(raw_seed)
    if isinstance(raw_seed, bool) or seed != raw_seed or not 0 <= seed <= 2**64 - 1:
        raise ValueError("随机种子必须是 0 到 2^64-1 之间的整数。")
    raw_steps = request.get("steps", 6 if model == "image" else 20)
    steps = int(raw_steps)
    if isinstance(raw_steps, bool) or steps != raw_steps or not 1 <= steps <= 100:
        raise ValueError("采样步数必须是 1–100 的整数。")
    if model == "image" and steps != 6:
        raise ValueError("MiniMax-H3-Image 使用官方蒸馏的 6 步采样。")
    if model == "video" and width * height > 1280 * 768:
        raise ValueError("此笔记本配置的视频画布面积上限为 1280×768。")

    graph = {
        "1": _node("UNETLoader", unet_name=IMAGE_MODEL if model == "image" else REFERENCE_VIDEO_MODEL if mode == "ref2va" else VIDEO_MODEL, weight_dtype="default"),
        "2": _node("CLIPLoader", clip_name=TEXT_ENCODER, type="minimax", device="default"),
        "3": _node("VAELoader", vae_name=IMAGE_VAE if model == "image" else VIDEO_VAE),
    }
    for index, filename in enumerate(refs):
        graph[str(20 + index)] = _node("LoadImage", image=filename)
    if model == "image":
        conditioning: dict[str, Any] = {"clip": ["2", 0], "vae": ["3", 0],
                                        "prompt": prompt, "width": width, "height": height}
        if refs:
            # io.Autogrow inputs are submitted with dotted API keys, not a
            # nested images dictionary. Comfy reconstructs the group.
            for index in range(len(refs)):
                conditioning[f"images.image_{index + 1}"] = [str(20 + index), 0]
        graph.update({
            "4": _node("MiniMaxH3ImageConditioning", **conditioning),
            "5": _node("ConditioningZeroOut", conditioning=["4", 0]),
            "6": _node("KSampler", model=["1", 0], seed=seed, steps=6, cfg=1.0,
                       sampler_name="euler", scheduler="simple", positive=["4", 0],
                       negative=["5", 0], latent_image=["4", 1], denoise=1.0),
            "7": _node("VAEDecode", samples=["6", 0], vae=["3", 0]),
            "8": _node("SaveImage", images=["7", 0], filename_prefix="MiniMax-H3-Studio/image"),
        })
    else:
        length = video_frame_count(request.get("duration", 4))
        conditioning = {"clip": ["2", 0], "vae": ["3", 0], "prompt": prompt,
                        "width": width, "height": height, "length": length}
        conditioning_class = "MiniMaxH3ImageToVideo"
        if mode == "ref2va":
            conditioning_class = "MiniMaxH3ReferenceToVideo"
            conditioning.update(audio_vae=["11", 0], ref_image_size="match")
            # Official Ref2VA template slots start at zero; the prompt labels
            # are one-based (<Picture 1>, <Picture 2>, ...), in this order.
            for index in range(len(refs)):
                conditioning[f"ref_images.ref_image_{index}"] = [str(20 + index), 0]
        elif refs:
            conditioning["first_frame"] = ["20", 0]
        graph.update({
            "4": _node(conditioning_class, **conditioning),
            "5": _node("RandomNoise", noise_seed=seed),
            "6": _node("BasicGuider", model=["1", 0], conditioning=["4", 0]),
            "7": _node("KSamplerSelect", sampler_name="res_multistep"),
            "8": _node("BasicScheduler", model=["1", 0], scheduler="simple", steps=steps, denoise=1.0),
            "9": _node("SamplerCustomAdvanced", noise=["5", 0], guider=["6", 0],
                       sampler=["7", 0], sigmas=["8", 0], latent_image=["4", 1]),
            "10": _node("VAEDecode", samples=["9", 0], vae=["3", 0]),
            "11": _node("VAELoader", vae_name=AUDIO_VAE),
            "12": _node("VAEDecodeAudio", samples=["9", 0], vae=["11", 0]),
            "13": _node("CreateVideo", images=["10", 0], audio=["12", 0], fps=24.0, bit_depth=8),
            "14": _node("SaveVideo", video=["13", 0], filename_prefix="MiniMax-H3-Studio/video",
                        **{"format": "mp4", "format.codec": "h264"}),
        })
    return graph
