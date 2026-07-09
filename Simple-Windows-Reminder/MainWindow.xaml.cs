using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.ComponentModel;
using System.Windows;
using System.Windows.Input;

namespace Simple_Windows_Reminder;

public partial class MainWindow : Window
{
    private readonly Action _save;
    private bool _isPositionAdjusting;

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

    public bool IsPositionAdjusting => _isPositionAdjusting;

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

        ApplyClickThrough();
    }

    private void OnMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if ((_isPositionAdjusting || !State.ClickThrough) && e.ButtonState == MouseButtonState.Pressed)
        {
            DragMove();
        }
    }

    public void SetPositionAdjusting(bool enabled)
    {
        if (_isPositionAdjusting == enabled)
        {
            return;
        }

        _isPositionAdjusting = enabled;
        Cursor = enabled ? System.Windows.Input.Cursors.SizeAll : System.Windows.Input.Cursors.Arrow;
        RootBorder.BorderThickness = enabled ? new Thickness(1) : new Thickness(0);
        RootBorder.BorderBrush = enabled ? System.Windows.Media.Brushes.DodgerBlue : null;
        ApplyClickThrough();

        if (enabled && !IsVisible)
        {
            Show();
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
            ApplyClickThrough();
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

    private void ApplyClickThrough()
    {
        NativeMethods.SetClickThrough(this, State.ClickThrough && !_isPositionAdjusting);
    }
}
