using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;
using System.Windows.Media;
using MediaBrush = System.Windows.Media.Brush;

namespace Simple_Windows_Reminder;

public sealed class ReminderItem : INotifyPropertyChanged
{
    private string _text = string.Empty;

    public Guid Id { get; set; } = Guid.NewGuid();

    public DateTime CreatedAt { get; set; } = DateTime.Now;

    public string Text
    {
        get => _text;
        set
        {
            if (_text != value)
            {
                _text = value;
                OnPropertyChanged();
            }
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}

public sealed class ReminderState : INotifyPropertyChanged
{
    private double _left = -1;
    private double _top = 24;
    private double _opacity = 0.82;
    private double _fontSize = 22;
    private string _textColor = "#FFFFFFFF";
    private bool _clickThrough = true;
    private bool _startWithWindows;

    public ObservableCollection<ReminderItem> Items { get; set; } = [];

    public double Left
    {
        get => _left;
        set => SetField(ref _left, value);
    }

    public double Top
    {
        get => _top;
        set => SetField(ref _top, value);
    }

    public double Opacity
    {
        get => _opacity;
        set => SetField(ref _opacity, value);
    }

    public double FontSize
    {
        get => _fontSize;
        set => SetField(ref _fontSize, value);
    }

    public string TextColor
    {
        get => _textColor;
        set => SetField(ref _textColor, value);
    }

    public bool ClickThrough
    {
        get => _clickThrough;
        set => SetField(ref _clickThrough, value);
    }

    public bool StartWithWindows
    {
        get => _startWithWindows;
        set => SetField(ref _startWithWindows, value);
    }

    [JsonIgnore]
    public MediaBrush TextBrush
    {
        get
        {
            try
            {
                return (MediaBrush)new BrushConverter().ConvertFromString(TextColor)!;
            }
            catch
            {
                return System.Windows.Media.Brushes.White;
            }
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    private void SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return;
        }

        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        if (propertyName == nameof(TextColor))
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(TextBrush)));
        }
    }
}
