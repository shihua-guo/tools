# 离线 MP4 转 MP3 并转写文字工具

这是一个 Windows 离线命令行工具。它把多个目录里的 `.mp4`/`.mp3` 扫描出来，统一输出同名 `.mp3`、`.txt`、`.srt` 到一个目录，并把进度写入 `progress.jsonl`。

当前版本仅用于中文普通话识别，配置中的 `language` 请保持 `Chinese`。

`chunk_size` 建议保持 `20`。Qwen3-ASR 的 llama.cpp 后端不适合过长分段，本工具会拒绝超过 `40` 秒的配置。程序会把 Aligner 的 `n_ctx`/`n_batch` 统一设为 `4096`，并按真实的 `batch.n_tokens` 做 decode 前保护；Qwen MRoPE 的四路 position 数据不会被误算为四倍 token。

## 推荐部署方式：源码 + 独立虚拟环境

不要将本项目打成 PyInstaller EXE 后跨机器复制。CapsWriter-Offline 自带的 `internal` 是其私有的冻结 Python 运行时，里面有 `python313.dll`、`unicodedata.pyd` 等二进制模块；它和打包 EXE 的 Python 运行时混用时，可能报：

```text
ImportError: Module use of python313.dll conflicts with this version of Python.
```

当前代码只引用 CapsWriter 的 `util` 源码，依赖库全部由本工具自己的 Python 虚拟环境提供，因此不会加载 `CapsWriter-Offline\internal` 中的 Python 扩展。

### 在可联网的机器准备

1. 安装 **64 位 Python 3.13**（内外网机器均使用同一主版本）。
2. 在项目根目录执行：

```powershell
.\prepare_offline_wheels.ps1
```

这会把本工具依赖及其传递依赖下载到 `wheelhouse`。将整个 `mp4_asr_offline` 目录复制到内网机器；无需复制或运行本项目的 EXE。

### 在内网 Win11 安装

1. 安装 64 位 Python 3.13；可不加入 PATH，但需要记录 `python.exe` 的完整路径。
2. 确保该机器已有完整的 CapsWriter-Offline 与 Qwen3-ASR 模型。
3. 编辑 `config.yaml` 中的路径，尤其是 `capswriter_dir`。
4. 在项目目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_offline.ps1
```

若 Python 未加入 PATH：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_offline.ps1 -Python 'C:\Path\To\Python313\python.exe'
```

安装脚本会创建本工具专属的 `.venv`，完全离线安装 `wheelhouse` 中的依赖，并执行 `--check-runtime` 检查；检查通过才可开始批量转写。

运行：

```powershell
.\run.cmd
```

带命令行覆盖参数：

```powershell
.\run.cmd --output D:\Result --overwrite
```

Qwen3-ASR 模型目录需要包含 ASR 文件和 aligner 文件，否则无法生成 `.srt` 时间轴。

### 目录内容

内网拷贝目录应至少包含：

- `mp4_asr_offline.py`
- `webui.py`
- `config.yaml`
- `requirements.txt`
- `wheelhouse\`（在联网机器运行准备脚本后生成）
- `install_offline.ps1`
- `run.cmd`
- `start_webui.cmd`
- `ffmpeg.exe`、`ffprobe.exe`（或已加入系统 PATH）

`.venv` 是内网安装后自动生成的目录，不建议从外网机器直接复制。
`ffmpeg.exe` 和 `ffprobe.exe` 不提交到 Git：当前构建中的单个文件约 223 MB，超过 GitHub 单文件限制。请从外网机器现有的 `dist\mp4_asr_offline\` 目录复制这两个文件到内网项目根目录，或由内网管理员提供并加入 PATH。

## WebUI

安装完成后可直接运行：

```powershell
.\start_webui.cmd
```

默认监听 `http://127.0.0.1:8765/`。如果端口被占用，可以指定：

```powershell
$env:MP4_ASR_WEBUI_PORT=8766
.\start_webui.cmd
```

WebUI 会生成临时配置文件并调用同目录下的 `mp4_asr_offline.py`；进度来自输出目录中的 `progress.jsonl` 和实时控制台日志。

## 续跑规则

默认不会重复处理完整结果。如果输出目录里已经有同名 `.mp3`、`.txt`、`.srt`，程序会跳过该视频。

如果只存在 `.mp3`，程序会复用它，只补 `.txt` 和 `.srt`。

需要全部重跑时加：

```powershell
.\run.cmd --overwrite
```

## 进度文件

`progress.jsonl` 位于 `output_dir` 下，每行是一条 JSON 记录，包含输入文件、输出文件、状态、百分比、chunk 进度、耗时和错误信息。

常见状态：

- `queued`
- `extracting_audio`
- `audio_done`
- `transcribing`
- `done`
- `skipped`
- `failed`

## 开发检查

```powershell
python .\mp4_asr_offline.py --config .\config.yaml --check-runtime
```

`build.py` 与 `build_webui.py` 是历史打包脚本，不用于跨机器发布。
