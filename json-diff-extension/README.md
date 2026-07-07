# JSON Diff Comparator Edge Extension

一个离线 Edge 浏览器扩展，用于对比两段 JSON 的变化。

## 功能

- 输入修改前 JSON 和修改后 JSON。
- 点击“确定”后按 key 对 JSON 进行稳定排序。
- 高亮新增、删除、修改字段。
- 输出变化结论和变化字段明细。

## 安装

1. 打开 Edge，访问 `edge://extensions/`。
2. 开启“开发人员模式”。
3. 点击“加载解压缩的扩展”。
4. 选择本目录 `json-diff-extension`。

## 文件

- `manifest.json`: Edge/Chrome Manifest V3 扩展配置。
- `popup.html`: 插件弹窗页面。
- `popup.css`: 页面样式。
- `popup.js`: JSON 排序、对比、高亮和结论逻辑。
