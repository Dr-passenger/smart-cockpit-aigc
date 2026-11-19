# 排错

| 现象 | 检查与处理 |
| --- | --- |
| 双击后提示 Python 不存在 | 安装 Python 3.12 x64，重新打开终端；也可 `setup.ps1 -Python "绝对路径\python.exe"`。Microsoft Store 执行别名不代表已安装 Python。 |
| Git 不存在 | 安装 Git for Windows，重新打开终端。 |
| 脚本被执行策略阻止 | 双击 `.bat`，其 Bypass 仅作用于当前进程；不需要修改系统策略。 |
| `CUDA unavailable` | 检查设备管理器、`nvidia-smi` 和 NVIDIA 驱动；确认不是 CPU 版 torch。脚本只报错，不会替你改驱动。 |
| CUDA kernel 或 unsupported operator | 查看 engine.log 的完整异常及 `data/install/engine-freeze.txt`。默认 cu128 会关闭 Kitchen CUDA 优化并走 eager 后备，速度可能较慢；不能据此推断目标机一定成功。不要在出错后同时升级多个依赖。 |
| 下载超时或中断 | 保持同一项目路径重新执行下载命令，Hugging Face 下载会复用有效暂存；已通过 SHA256 的成品会跳过。首次下载需要访问 Hugging Face；推理不需要。 |
| SHA256 不一致 | 不启动模型。删除提示的损坏暂存文件后重试；不要只改清单里的 hash 或 size。 |
| 启动前缺模型 | 先执行 `.venv\Scripts\python.exe scripts\download_models.py`；或只准备某一模型并使用相同的 `-Models` 启动参数。 |
| GPU OOM | 先降到 512×512，短视频，关其他 GPU 应用。等待当前任务退出并卸载后再试；长期持续 OOM 时停止并重启。16GB 显存无法保证运行。 |
| 系统内存接近 64GB、机器卡顿 | 立即减少工作负载，关闭其他程序；可在快速 NVMe 上尝试 `-FastDisk`。脚本不修改分页文件，磁盘卸载也不能保证内存足够。 |
| 很长时间无预览 | 文本编码器和权重卸载可能耗时，默认关闭采样预览以省显存；查看引擎日志与任务状态。默认单任务最长等待 24 小时，可取消。不要把没有报错当作已验证生成成功。 |
| 端口占用 | 关闭自己已启动的实例，或 `start.ps1 -StudioPort 8231 -EnginePort 8189`。启动器不会杀掉未知服务。 |
| 智能座舱AIGC 正常但模型未就绪 | `-UiOnly` 仅演示界面；完成引擎和权重安装。确认 engine.log 无导入错误。 |
| FL2VA 就绪但多参考视频未就绪 | Ref2VA 使用独立 DiT。执行 `setup.ps1 -Models ref2va` 或下载脚本 `--models ref2va`；仅装 FL2VA 不等于已装 Ref2VA。 |
| Ref2VA 没把参考图作为首帧 | 多参考模式按内容参考生成；需要固定首帧时改用 FL2VA 首帧图生视频。 |
| 引擎提前退出 | 打开 `data/logs/engine.log`。启动器会停止界面并保留错误码；安装或模型失败不能只忽略后继续生成。 |
| 黑图或质量不佳 | 先确认生成配置、模型与 VAE 完整，换简单提示词；512px 仅为内存探测。不要随意改成全 FP16 来尝试节省量化模型内存。 |
| 4 秒视频变成约 4.46 秒 | 这是 24fps、`17k+5` 帧网格向上对齐的结果：107 帧。 |

离线完整检查：

```powershell
.\.venv\Scripts\python.exe scripts\download_models.py --check --sha256
```

启动成功后断网，先运行小图，再运行短视频，确认结果文件可打开和下载。这才是目标笔记本的实际离线验收。仓库内 CPU 测试不能替代此步骤。
