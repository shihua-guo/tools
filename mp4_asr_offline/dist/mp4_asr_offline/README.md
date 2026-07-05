# 离线 MP4 转 MP3 并转写文字工具

这是一个 Windows 便携命令行工具。它把多个目录里的 `.mp4`/`.mp3` 扫描出来，统一输出同名 `.mp3`、`.txt`、`.srt` 到一个目录，并把进度写入 `progress.jsonl`。

当前版本仅用于中文普通话识别，配置中的 `language` 请保持 `Chinese`。

## 目录内容

便携发布目录应包含：

- `mp4_asr_offline.exe`
- `ffmpeg.exe`
- `ffprobe.exe`
- `config.yaml`
- `README.md`

发布目录不包含 CapsWriter-Offline 和 Qwen3-ASR 模型。内网机器上需要已有这两部分文件。

Qwen3-ASR 模型目录需要包含 ASR 文件和 aligner 文件，否则无法生成 `.srt` 时间轴。

## 使用方法

先编辑 `config.yaml`，填好：

- `inputs`: 一个或多个 MP4/MP3 来源目录，也可以直接写单个 `.mp4` 或 `.mp3` 文件
- `output_dir`: 统一输出目录
- `capswriter_dir`: CapsWriter-Offline 根目录
- `model_dir`: 可留空，默认从 CapsWriter 目录推导

运行：

```powershell
.\mp4_asr_offline.exe --config .\config.yaml
```

也可以用 CLI 覆盖配置：

```powershell
.\mp4_asr_offline.exe --config .\config.yaml --output D:\Result --overwrite
```

## WebUI

便携目录中如果包含 `mp4_asr_webui.exe`，可直接运行它打开本地 WebUI：

```powershell
.\mp4_asr_webui.exe
```

默认监听 `http://127.0.0.1:8765/`。如果端口被占用，可以指定：

```powershell
$env:MP4_ASR_WEBUI_PORT=8766
.\mp4_asr_webui.exe
```

WebUI 会生成临时配置文件并调用同目录下的 `mp4_asr_offline.exe`，进度来自输出目录中的 `progress.jsonl` 和实时控制台日志。

## 续跑规则

默认不会重复处理完整结果。如果输出目录里已经有同名 `.mp3`、`.txt`、`.srt`，程序会跳过该视频。

如果只存在 `.mp3`，程序会复用它，只补 `.txt` 和 `.srt`。

需要全部重跑时加：

```powershell
.\mp4_asr_offline.exe --config .\config.yaml --overwrite
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

## 本机开发运行

```powershell
python .\mp4_asr_offline.py --config .\config.yaml --dry-run
```

打包：

```powershell
python .\build.py
python .\build_webui.py
```
