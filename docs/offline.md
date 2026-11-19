# 离线使用与转移

最可靠的流程是在目标 Windows 11 笔记本联网运行一次 `setup.bat`，确认下载与 SHA256 校验完成，然后断网运行 `start.bat`。首次安装不等同于离线推理：GitHub 源码、PyPI/PyTorch 依赖和 Hugging Face 权重都需提前获取。

若目标机从一开始就不能联网，在另一台相同 Windows x64、Python 3.12 的机器准备安装介质。Python 虚拟环境包含绝对路径，不建议直接复制 `.venv` 后改目录。需要准备：

1. Python 3.12 x64 与 Git for Windows 离线安装程序，以及目标机所需的 NVIDIA 驱动安装程序。
2. 完整本项目、固定提交的 `engine/ComfyUI` 源码（包含 Git 信息，启动器会校验 HEAD），及已 SHA256 验证的 `engine/ComfyUI/models`。
3. 与已验证安装记录匹配的 Windows cp312 GPU 轮子包及其全部依赖。安装记录是 `data/install/app-freeze.txt` 和 `engine-freeze.txt`。

在联网准备机完成一次安装后，可以创建轮子目录：

```powershell
# 在目标同平台 Windows x64 + Python 3.12 上收集，不从 Linux 下载
.\.venv\Scripts\python.exe -m pip download -r data\install\app-freeze.txt --only-binary=:all: -d wheelhouse\app
.\engine\.venv\Scripts\python.exe -m pip download -r data\install\engine-freeze.txt --extra-index-url https://download.pytorch.org/whl/cu128 --only-binary=:all: -d wheelhouse\engine
```

如有依赖没有预编译轮子，上面的命令会明确失败；先在准备机审查并构建所需轮子，再继续，不能声称已具备完整离线安装介质。

把整个项目及 `wheelhouse` 转移到目标机，在项目目录新建环境并离线安装：

```powershell
py -3.12 -m venv .venv
py -3.12 -m venv engine\.venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse\app -r data\install\app-freeze.txt
.\engine\.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse\engine -r data\install\engine-freeze.txt
.\.venv\Scripts\python.exe scripts\download_models.py --check --sha256
.\start.ps1
```

这些离线介质制作命令未在当前环境实际执行；它们要求准备机先有一套已成功安装的目标平台环境。三组模型去重后 7 个权重共 94,646,241,490 字节，约 94.65GB，不能通过普通 GitHub 仓库保存。`.gitignore` 会排除权重、环境、下载缓存、日志及用户作品；请使用移动硬盘传输。
