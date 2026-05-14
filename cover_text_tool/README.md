# 自媒体封面文字工具

这是一个本地运行的 Python WebUI 小工具，用来给竖屏、横屏封面图批量叠加中文标题文字。

## 使用方式

双击运行：

```bat
start.bat
```

或在命令行运行：

```powershell
cd C:\Users\shihu\Documents\workspace\tools\cover_text_tool
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

然后打开：

```text
http://127.0.0.1:7860
```

## 功能

- 上传竖屏图片和横屏图片。
- 输入主标题、副标题、角标。
- 选择文字位置、对齐方式、文字颜色、角标颜色。
- 支持渐变压暗、半透明底板、仅文字描边三种可读性样式。
- 支持上传 `.ttf` / `.ttc` / `.otf` 字体文件。
- 生成后的图片保存在 `outputs` 文件夹。

## 建议

- 竖屏封面建议使用 1080x1920 或 1080x1440。
- 横屏封面建议使用 1920x1080 或 1280x720。
- 标题太长时会自动换行，并尽量缩小到可读范围内。
