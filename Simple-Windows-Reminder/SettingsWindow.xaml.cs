using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Windows;
using System.Windows.Input;
using WpfKeyEventArgs = System.Windows.Input.KeyEventArgs;

namespace Simple_Windows_Reminder;

public partial class SettingsWindow : Window
{
    private readonly Action _save;

    public SettingsWindow(ReminderState state, Action save)
    {
        State = state;
        _save = save;
        DisplayItems = new ObservableCollection<ReminderItem>(State.Items.Reverse());

        InitializeComponent();
        DataContext = this;

        State.PropertyChanged += OnStateChanged;
    }

    public ReminderState State { get; }

    public ObservableCollection<ReminderItem> DisplayItems { get; }

    private void AddButton_OnClick(object sender, RoutedEventArgs e)
    {
        AddTask();
    }

    private void TaskInput_OnKeyDown(object sender, WpfKeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            AddTask();
            e.Handled = true;
        }
    }

    private void DeleteButton_OnClick(object sender, RoutedEventArgs e)
    {
        if (TaskList.SelectedItem is not ReminderItem item)
        {
            return;
        }

        State.Items.Remove(item);
        RefreshDisplayItems();
        _save();
    }

    private void AddTask()
    {
        string text = TaskInput.Text.Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        State.Items.Add(new ReminderItem
        {
            Text = text,
            CreatedAt = DateTime.Now
        });
        TaskInput.Clear();
        RefreshDisplayItems();
        _save();
    }

    private void RefreshDisplayItems()
    {
        DisplayItems.Clear();
        foreach (ReminderItem item in State.Items.Reverse())
        {
            DisplayItems.Add(item);
        }
    }

    private void OnStateChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(ReminderState.StartWithWindows))
        {
            StartupService.SetEnabled(State.StartWithWindows);
        }

        _save();
    }
}
