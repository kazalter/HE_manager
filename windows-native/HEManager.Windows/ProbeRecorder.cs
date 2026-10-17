using System.Diagnostics;
using System.Text.Json;

namespace HEManager.Windows;

// Opt-in diagnostics only. Never accepts player commands or server credentials.
internal sealed class ProbeRecorder : IDisposable
{
    readonly string directory;
    readonly StreamWriter history;
    readonly Stopwatch clock = Stopwatch.StartNew();
    long last;
    public ProbeRecorder(string directory)
    {
        this.directory = Path.GetFullPath(directory);
        Directory.CreateDirectory(this.directory);
        history = new(Path.Combine(this.directory, "samples.jsonl"), false) { AutoFlush = true };
    }
    public void Record(object value)
    {
        string json = JsonSerializer.Serialize(value);
        string temporary = Path.Combine(directory, "state.tmp");
        File.WriteAllText(temporary, json);
        File.Move(temporary, Path.Combine(directory, "state.json"), true);
        if (clock.ElapsedMilliseconds - last >= 1000)
        {
            history.WriteLine(json);
            last = clock.ElapsedMilliseconds;
        }
    }
    public void Dispose() => history.Dispose();
}
