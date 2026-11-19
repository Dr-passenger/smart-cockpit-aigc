# 模型与推理接口核对记录

核对日期：2026-11-19。此记录来自模型发布者与 Comfy 官方代码、模型仓库和模板；没有在目标 RTX 4090 Laptop 上加载权重、执行生成或测量速度、显存峰值。

## 部署范围

- MiniMax-H3：FL2VA 的剪枝 INT8 权重执行文生音视频、首帧图生音视频；独立的 Ref2VA 剪枝 INT8 权重执行多图参考生音视频。
- MiniMax-H3-Image：使用剪枝 INT8 权重，执行文生图和最多 16 张参考图的编辑。
- 图像、两种视频任务共享 Qwen3-VL-32B INT8 文本编码器。下载全部任务去重后 7 个文件共 94,646,241,490 字节，约 94.65 GB / 88.15 GiB。Ref2VA 单独文件组含共享组件为 51,528,041,760 字节；已备齐 FL2VA 时只需多下载 20,970,379,616 字节的 Ref2VA DiT。每个文件的固定 revision、精确大小和 LFS SHA256 均记录在 [models.json](../runtime/models.json)。
- 运行时仅访问本机回环地址的 ComfyUI；首次安装与准备权重需要联网，准备完成后生成可离线运行。不使用 Context-IR、托管 2K 再生成、远程 GPU 或付费生成节点。可选提示词扩写模型也没有加载。

官方模型入口：[MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)、[MiniMax-H3-Image](https://huggingface.co/MiniMaxAI/MiniMax-H3-Image)。Comfy 原始模板：[图像](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_minimax_h3_image_t2i.json)、[图生视频](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_i2v.json)、[参考生视频](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_r2v.json)。

## 固定代码版本与 INT8 回退

ComfyUI 固定在 `a277b5bf213e8a44fa34817b7770b54f86ef4cea`，其 [requirements.txt](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/requirements.txt) 固定 `comfy-kitchen==0.2.41`。

本项目选择 PyTorch CUDA 12.8，以兼容更多现有驱动。这带来一个明确限制：[comfy/quant_ops.py 第 26 行起](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy/quant_ops.py#L26) 检查 `torch.version.cuda`，低于 13 时禁用 Kitchen 的优化 CUDA backend。因此本配置不能声称启用了 Kitchen 的融合 CUDA ConvRot 内核。

INT8 仍有代码支持的 PyTorch eager 回退路径：

1. Comfy 的 [comfy/ops.py](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy/ops.py#L1404) 在 `_load_quantized_module` 中读取 `int8_tensorwise` 及 `convrot` 标记、比例与组大小；[comfy/quant_ops.py](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy/quant_ops.py#L238) 将该格式注册为 `TensorWiseINT8Layout`。
2. Kitchen v0.2.41 的 [tensor/int8.py](https://github.com/Comfy-Org/comfy-kitchen/blob/v0.2.41/comfy_kitchen/tensor/int8.py#L79) 给出 INT8 Tensor Core 的最低计算能力为 SM 7.5。其 `_handle_int8_linear_tensorwise` 把输入、INT8 权重、比例及 ConvRot 参数传给 Kitchen 算子。
3. Kitchen 的 [eager/quantization.py 第 985 行起](https://github.com/Comfy-Org/comfy-kitchen/blob/v0.2.41/comfy_kitchen/backends/eager/quantization.py#L985) 中，`int8_linear` 在需要时执行激活 Hadamard 旋转、按行量化，然后调用 `_int8_matmul_accumulate`。后者在[第 750 行起](https://github.com/Comfy-Org/comfy-kitchen/blob/v0.2.41/comfy_kitchen/backends/eager/quantization.py#L750) 选择 `torch.int8_mm` 或 `torch._int_mm`，并处理矩阵尺寸对齐。

这里的 eager 指 PyTorch 算子组合，仍可在 CUDA GPU 上计算；不能把它理解为强制整模型在 CPU 上执行。CPU/显存/磁盘卸载是另一个独立的内存管理机制。上述源码证明存在回退实现，并不能替代 Windows + Ada + 目标笔记本的实测，也不能给出速度或容量保证。

## 真实节点接口

生成图由 [runtime/workflow.py](../runtime/workflow.py) 构建，直接提交 ComfyUI `/prompt` 所需的节点字典；不是把编辑器工作流 JSON 冒充 API prompt。

| 任务 | 主要节点 | 参数与连接 |
| --- | --- | --- |
| 图像生成/编辑 | `MiniMaxH3ImageConditioning` | `clip`、`vae`、`prompt`、`width`、`height`；参考图以 `images.image_1` 连接 |
| 音视频生成 | `MiniMaxH3ImageToVideo` | `clip`、视频 `vae`、`prompt`、`width`、`height`、`length`；图生视频连接 `first_frame` |
| 多图参考生音视频 | `MiniMaxH3ReferenceToVideo` | 独立 Ref2VA 模型；`clip`、`vae`、`audio_vae`、`prompt`、画布及帧数；参考图片以 `ref_images.ref_image_0` 起连接，`ref_image_size=match` |
| 图像采样 | `KSampler` | 固定 6 步、CFG 1、Euler、simple、denoise 1 |
| 视频采样 | `SamplerCustomAdvanced` | `RandomNoise`、`BasicGuider`、`res_multistep`、simple；默认 20 步，不使用 Turbo LoRA |
| 媒体保存 | `SaveImage` / `SaveVideo` | 视频 `format=mp4`、动态字段 `format.codec=h264`；`CreateVideo` 同时连接图像和音频 |

`images.image_1` 是 io.Autogrow 的真实扁平 API 字段，Comfy 会在执行时重建分组；不能改成嵌套 `images: {image_1: ...}`。见 [节点定义](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy_extras/nodes_minimax_h3.py) 和 [动态输入测试](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/tests-unit/execution_test/dynamic_inputs_test.py)。`format.codec` 同理由 `io.DynamicCombo` 解析；见 [SaveVideo 定义](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy_extras/nodes_video.py)。

### Ref2VA 连接与参考顺序

参考生视频不是把多张图接到首帧节点。它需要 `minimax_h3_ref2va_pruned_int8_convrot.safetensors` 与 `MiniMaxH3ReferenceToVideo`，同时把图像参考的 VAE latent 作为 `minimax_refs` 提供给扩散模型。`ref_image_size=match` 会保持比例，只向下缩到输出画布的像素面积；`max` 可增加参考清晰度，但参考 token 会参与每次采样，可能明显增加显存和耗时。本项目固定 `match`。

本项目 Ref2VA 界面和 API 支持 1–9 张参考图片，按上传顺序对应提示词 `<Picture 1>`、`<Picture 2>` 等；Comfy API 输入名则按官方模板从 `ref_images.ref_image_0`、`ref_images.ref_image_1` 起。普通首帧图生视频只接受一张图。权重清单单列 `id=ref2va`，普通 `video` 文件组只需要 FL2VA，避免只用首帧任务也必须下载 Ref2VA。

固定核心的 Ref2VA 节点也支持视频和音频参考，但本项目当前上传流程只接入图片，不会把图片功能描述为已实现音视频上传。若扩展原生 Comfy 工作流：

| 参考类型 | 核心 API 字段 | 连接规则 |
| --- | --- | --- |
| 视频帧 | `ref_videos.ref_video_0` 起，最多 3 组 | 输入 IMAGE 帧批次，按 24fps 准备；`LoadVideo` → `GetVideoComponents` 的输出 0 是帧批次，帧率不同需先重采样 |
| 视频声轨 | `ref_video_audios.ref_video_audio_0` 起，最多 3 组 | `GetVideoComponents` 的输出 1 是 AUDIO；编号必须与同一视频配对 |
| 独立音频 | `ref_audios.ref_audio_0` 起，最多 3 组 | 输入 AUDIO，同时连接 `audio_vae` |

核心按图片、视频（声轨标签在所属视频之前）、独立音频的次序编码，提示词的 `<Picture n>`、`<Video n>`、`<Audio n>` 各自从 1 编号。视频需满足该模型的帧网格和长度约束；核心会截到输出长度，并向下取有效 `17k+5` 帧数。上述规则见同一 [MiniMaxH3ReferenceToVideo 定义](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy_extras/nodes_minimax_h3.py) 与 [GetVideoComponents 定义](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy_extras/nodes_video.py)。

视频与音频采样结果是联合 NestedTensor。`VAEDecode` 选择 `samples.unbind()[0]` 的视频部分；`VAEDecodeAudio` 选择 `samples.unbind()[-1]` 的音频部分，分别解码后送入 `CreateVideo`。见 [nodes.py](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/nodes.py) 与 [nodes_audio.py](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy_extras/nodes_audio.py)。

使用普通 `VAEDecode` 是有意的：MiniMax VAE 已始终在内部进行空间分块和视频时间分块；[MiniMaxH3VideoVAE.decode_tiled 第 988 行](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy/ldm/minimax/vae.py#L988) 会忽略外部 tile 参数。正常 [VAE.decode](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy/sd.py#L1391) 支持预分配 CPU 输出并流式写入视频块，显式 `VAEDecodeTiled` 反而会通过 `_decode_tiled_owned` 再复制完整输出。

`SaveVideo` 的 history UI 输出实际使用 `images` 键，并附加 `animated`；文件后缀为 `.mp4`。后端必须按文件后缀识别媒体类型，不能只读取 `videos` 键。证据：[PreviewVideo.as_dict 第 426 行起](https://github.com/Comfy-Org/ComfyUI/blob/a277b5bf213e8a44fa34817b7770b54f86ef4cea/comfy_api/latest/_ui.py#L426)。

## 16GB 显存与 64GB 内存的边界

三份任务扩散权重的单文件均约 21GB，文本编码器约 27.14GB，不能全部常驻 16GB 显存。每个任务只使用对应的一份扩散权重，模型串行按需加载；动态卸载、释放节点缓存与积极卸载可降低占用，但中间激活、解量化临时张量、系统占用和分页都会影响实际峰值。Ref2VA 的参考图越多，参与每步采样的 token 越多；建议目标机器先试一张参考图，再逐张增加。

默认图像 1024×1024、视频 512×512 / 名义 4 秒是内存探测起点，不是官方质量基准。图像官方有效范围约 4–20MP，通常以 16MP 最佳；[Comfy 官方指南](https://docs.comfy.org/tutorials/image/minimax/minimax-h3-image) 的低显存模板仍从 4MP 起步。视频固定 24fps，帧数向上对齐 `17k+5`；4 秒实际得到 107 帧（约 4.458 秒），5 秒得到 124 帧，15 秒得到 362 帧。

[SGLang 官方硬件说明](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3-Image) 也列出消费卡 layerwise offload 派生配置，但原精度方案假定约 256GB 主存与本地 NVMe，且明确不提供消费卡延迟或容量保证；不能将其当作本项目 64GB Windows 配置已验证的证据。
