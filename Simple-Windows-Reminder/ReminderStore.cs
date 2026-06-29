using System.IO;
using System.Text.Json;

namespace Simple_Windows_Reminder;

public sealed class ReminderStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true
    };

    private readonly string _configFile;

    public ReminderStore()
    {
        string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        string appDir = Path.Combine(appData, "Simple-Windows-Reminder");
        Directory.CreateDirectory(appDir);
        _configFile = Path.Combine(appDir, "config.json");
    }

    public ReminderState Load()
    {
        if (!File.Exists(_configFile))
        {
            return new ReminderState
            {
                Items =
                [
                    new ReminderItem { Text = "写下今天最重要的事" }
                ]
            };
        }

        try
        {
            string json = File.ReadAllText(_configFile);
            return JsonSerializer.Deserialize<ReminderState>(json, JsonOptions) ?? new ReminderState();
        }
        catch
        {
            return new ReminderState();
        }
    }

    public void Save(ReminderState state)
    {
        string json = JsonSerializer.Serialize(state, JsonOptions);
        File.WriteAllText(_configFile, json);
    }
}
