using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.ComponentModel;
using System.Windows;
using System.Windows.Input;

namespace Simple_Windows_Reminder;

public partial class MainWindow : Window
{
    private readonly Action _save;

    public MainWindow(ReminderState state, Action save)
    {
        State = state;
        _save = save;
        DisplayItems = new ObservableCollection<ReminderItem>(State.Items.Reverse());

        InitializeComponent();
        DataContext = this;

        Loaded += OnLoaded;
        LocationChanged += (_, _) => SavePosition();
        MouseLeftButtonDown += OnMouseLeftButtonDown;
        State.PropertyChanged += OnStateChanged;
        State.Items.CollectionChanged += OnItemsChanged;
    }

    public ReminderState State { get; }

    public ObservableCollection<ReminderItem> DisplayItems { get; }

    public void RefreshDisplayItems()
    {
        DisplayItems.Clear();
        foreach (ReminderItem item in State.Items.Reverse())
        {
            DisplayItems.Add(item);
        }
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        Opacity = State.Opacity;
        if (State.Left < 0)
        {
            Left = SystemParameters.WorkArea.Right - Width - 32;
            Top = State.Top;
            SavePosition();
        }
        else
        {
            Left = State.Left;
            Top = State.Top;
        }

        NativeMethods.SetClickThrough(this, State.ClickThrough);
    }

    private void OnMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (!State.ClickThrough && e.ButtonState == MouseButtonState.Pressed)
        {
            DragMove();
        }
    }

    private void OnStateChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(ReminderState.Opacity))
        {
            Opacity = State.Opacity;
        }

        if (e.PropertyName == nameof(ReminderState.ClickThrough))
        {
            NativeMethods.SetClickThrough(this, State.ClickThrough);
        }

        _save();
    }

    private void OnItemsChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        RefreshDisplayItems();
        _save();
    }

    private void SavePosition()
    {
        if (!IsLoaded)
        {
            return;
        }

        State.Left = Left;
        State.Top = Top;
    }
}
