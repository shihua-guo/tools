using System.Windows;
using WpfApplication = System.Windows.Application;

namespace Simple_Windows_Reminder;

public partial class App : WpfApplication
{
    private ReminderStore? _store;
    private MainWindow? _mainWindow;
    private SettingsWindow? _settingsWindow;
    private TrayIconService? _trayIcon;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        _store = new ReminderStore();
        ReminderState state = _store.Load();

        _mainWindow = new MainWindow(state, SaveState);
        _mainWindow.Show();

        _trayIcon = new TrayIconService(
            showSettings: ShowSettings,
            toggleOverlay: ToggleOverlay,
            setPositionAdjusting: SetPositionAdjusting,
            exit: ShutdownApp);
    }

    private void ShowSettings()
    {
        if (_store is null || _mainWindow is null)
        {
            return;
        }

        if (_settingsWindow is null)
        {
            _settingsWindow = new SettingsWindow(_mainWindow.State, SaveState);
            _settingsWindow.Closed += (_, _) => _settingsWindow = null;
        }

        _settingsWindow.Owner = _mainWindow;
        _settingsWindow.Show();
        _settingsWindow.Activate();
    }

    private void ToggleOverlay()
    {
        if (_mainWindow is null)
        {
            return;
        }

        if (_mainWindow.IsVisible)
        {
            _mainWindow.Hide();
        }
        else
        {
            _mainWindow.Show();
        }
    }

    private void SetPositionAdjusting(bool enabled)
    {
        _mainWindow?.SetPositionAdjusting(enabled);
    }

    private void SaveState()
    {
        if (_store is not null && _mainWindow is not null)
        {
            _store.Save(_mainWindow.State);
        }
    }

    private void ShutdownApp()
    {
        SaveState();
        _trayIcon?.Dispose();
        Shutdown();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _trayIcon?.Dispose();
        base.OnExit(e);
    }
}
