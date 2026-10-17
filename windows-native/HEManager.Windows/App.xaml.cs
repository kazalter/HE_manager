using Microsoft.UI.Xaml;
namespace HEManager.Windows;

public partial class App : Application
{
    Window? window;
    public App() { InitializeComponent(); UnhandledException += (_, e) => { System.IO.File.AppendAllText(System.IO.Path.Combine(System.IO.Path.GetTempPath(), "he-native-crash.log"), e.Exception + Environment.NewLine); }; }
    protected override void OnLaunched(LaunchActivatedEventArgs args) { window = new MainWindow(); window.Activate(); }
}
