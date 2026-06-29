# Simple-Windows-Reminder

极简 Windows 待办提示工具。它把待办文字显示为置顶悬浮窗，默认鼠标穿透，不影响操作其他窗口。

## 功能

- 置顶悬浮显示待办事项
- 添加、删除待办
- 待办按添加时间倒序显示，最新任务在最上方
- 调整文字颜色、字号、透明度
- 默认鼠标穿透，可在设置窗口关闭后拖动悬浮窗
- 支持开机自启动
- 配置保存到 `%APPDATA%\Simple-Windows-Reminder\config.json`

## 运行

需要 Windows 和 .NET 8 SDK。

```powershell
cd Simple-Windows-Reminder
dotnet run
```

## 打包

```powershell
cd Simple-Windows-Reminder
dotnet publish -c Release -r win-x64 --self-contained true `
  /p:PublishSingleFile=true `
  /p:IncludeNativeLibrariesForSelfExtract=true
```

生成文件位于：

```text
bin\Release\net8.0-windows\win-x64\publish\Simple-Windows-Reminder.exe
```

## 使用

- 双击托盘图标打开设置窗口。
- 托盘右键可打开设置、显示/隐藏悬浮窗、退出。
- 添加任务后会立即显示到悬浮窗顶部。
- 默认开启鼠标穿透；需要移动悬浮窗时，在设置里取消“鼠标穿透”，拖动悬浮窗后再打开。
