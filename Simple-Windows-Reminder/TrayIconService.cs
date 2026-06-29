using System.Drawing;
using System.Windows.Forms;

namespace Simple_Windows_Reminder;

public sealed class TrayIconService : IDisposable
{
    private readonly NotifyIcon _notifyIcon;
    private readonly ToolStripMenuItem _adjustPositionItem;

    public TrayIconService(Action showSettings, Action toggleOverlay, Action<bool> setPositionAdjusting, Action exit)
    {
        ToolStripMenuItem settingsItem = new("设置/编辑", null, (_, _) => showSettings());
        ToolStripMenuItem toggleItem = new("显示/隐藏悬浮窗", null, (_, _) => toggleOverlay());
        _adjustPositionItem = new ToolStripMenuItem("调整位置")
        {
            CheckOnClick = true
        };
        _adjustPositionItem.CheckedChanged += (_, _) => setPositionAdjusting(_adjustPositionItem.Checked);
        ToolStripMenuItem exitItem = new("退出", null, (_, _) => exit());

        ContextMenuStrip menu = new();
        menu.Items.Add(settingsItem);
        menu.Items.Add(toggleItem);
        menu.Items.Add(_adjustPositionItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(exitItem);

        _notifyIcon = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Text = "Simple Windows Reminder",
            ContextMenuStrip = menu,
            Visible = true
        };

        _notifyIcon.DoubleClick += (_, _) => showSettings();
    }

    public void Dispose()
    {
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
    }
}
