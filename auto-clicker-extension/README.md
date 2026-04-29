# Auto Clicker Extension

## 功能
- CSS 选择器配置
- 每隔 `N ms` 查找并点击（最小 100ms）
- 连续 3 秒未找到自动停止
- 不可见或 `disabled` 视为未找到
- 点击方式：自动兜底（先 `element.click()`，再补发鼠标事件）
- 仅作用于当前标签页
- Popup 界面支持“测试元素”
- 按网站（host）保存配置
- 刷新/跳转后不会自动恢复运行
- 日志仅保留关键事件，最多 50 条

## 安装
1. 打开 Chrome/Edge 扩展管理页面：
- Chrome: `chrome://extensions`
- Edge: `edge://extensions`
2. 开启“开发者模式”。
3. 点击“加载已解压的扩展程序”并选择本目录 `auto-clicker-extension`。

## 使用
1. 打开目标网页，点击扩展图标。
2. 填写 CSS 选择器和间隔（ms）。
3. 可先点“测试元素”验证选择器是否能命中可点击元素。
4. 点击“开始”执行自动点击。
5. 点击“停止”终止。
