using System.Diagnostics;
using System.Drawing.Imaging;
using System.IO;
using System.Text.Json;
using System.Windows.Automation;
using Drawing=System.Drawing;

namespace HEManager.UITests;

// Human enters the real password in the native control; the test never reads it.
internal static class AccountAcceptance
{
    static Process? app;
    static AutomationElement? window;
    static string directory="";
    static readonly List<string> passed=[];
    static AutomationElement? Find(string id)=>window?.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,id));
    static AutomationElement Element(string id)
    {
        for(int i=0;i<30;i++) {var item=Find(id);if(item!=null)return item;Thread.Sleep(100);}
        throw new Exception("Missing account control: "+id);
    }
    static void Require(bool result,string message) {if(!result)throw new Exception(message);}
    static void Wait(Func<bool> test,string message,int seconds=20)
    {
        var timer=Stopwatch.StartNew();
        while(timer.Elapsed.TotalSeconds<seconds)
        {
            if(app!.HasExited)throw new Exception("Account window exited: "+app.ExitCode);
            try {if(test())return;} catch(ElementNotAvailableException) {}
            Thread.Sleep(200);
        }
        throw new TimeoutException(message);
    }
    static void Pass(string name)
    {
        passed.Add(name);File.WriteAllText(Path.Combine(directory,"results.json"),JsonSerializer.Serialize(passed));Console.WriteLine("PASS "+name);
    }
    static IntPtr Hwnd()=>new(unchecked((long)(uint)window!.Current.NativeWindowHandle));
    static void Start(string executable)
    {
        app=Process.Start(new ProcessStartInfo(executable))??throw new Exception("Cannot start account window");
        window=null;
        Wait(()=>
        {
            window=AutomationElement.RootElement.FindFirst(TreeScope.Children,new AndCondition(new PropertyCondition(AutomationElement.ProcessIdProperty,app.Id),new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Window)));
            return window!=null;
        },"No native account window",30);
        Native.Activate(Hwnd());
        Wait(()=>SignedIn() || Find("Login")?.Current.IsEnabled==true,"Server did not become ready");
    }
    static bool SignedIn()=>!string.IsNullOrWhiteSpace(Find("SignedInUser")?.Current.Name);
    static void SelectNavigation(string id)
    {
        var item=Element(id);
        if(item.TryGetCurrentPattern(SelectionItemPattern.Pattern,out var select))((SelectionItemPattern)select).Select();
        else ((InvokePattern)item.GetCurrentPattern(InvokePattern.Pattern)).Invoke();
    }
    static void Theme(string name)
    {
        ((ExpandCollapsePattern)Element("Theme").GetCurrentPattern(ExpandCollapsePattern.Pattern)).Expand();Thread.Sleep(300);
        var option=window!.FindFirst(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.NameProperty,name),new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ListItem)))??throw new Exception("Theme option missing: "+name);
        ((SelectionItemPattern)option.GetCurrentPattern(SelectionItemPattern.Pattern)).Select();Thread.Sleep(400);
    }
    static void Capture(string name)
    {
        var hwnd=Hwnd();Native.Activate(hwnd);Thread.Sleep(300);
        if(Native.GetForegroundWindow()!=hwnd) {File.WriteAllText(Path.Combine(directory,name+"-capture-skipped.txt"),"Player is not foreground");return;}
        Require(Native.GetWindowRect(hwnd,out var rect),"Window bounds unavailable");
        var visible=Drawing.Rectangle.Intersect(Drawing.Rectangle.FromLTRB(rect.Left,rect.Top,rect.Right,rect.Bottom),System.Windows.Forms.SystemInformation.VirtualScreen);
        using var bitmap=new Drawing.Bitmap(visible.Width,visible.Height);
        using(var graphics=Drawing.Graphics.FromImage(bitmap))graphics.CopyFromScreen(visible.Location,Drawing.Point.Empty,visible.Size);
        bitmap.Save(Path.Combine(directory,name+".png"),ImageFormat.Png);
    }
    static void Close()
    {
        if(app==null||app.HasExited)return;
        Native.PostMessage(Hwnd(),0x0010,IntPtr.Zero,IntPtr.Zero);
        Require(app.WaitForExit(10000)&&app.ExitCode==0,"Account window did not exit cleanly");
    }
    internal static int Run(string executable,int seconds)
    {
        directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"HEManager","WN02","acceptance-"+DateTime.Now.ToString("yyyyMMdd-HHmmss"));Directory.CreateDirectory(directory);
        try
        {
            string info=Path.Combine(Path.GetDirectoryName(executable)!,"build-info.json");if(File.Exists(info))File.Copy(info,Path.Combine(directory,"build-info.json"));
            File.WriteAllText(Path.Combine(directory,"test-binary-sha256.txt"),Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(typeof(AccountAcceptance).Assembly.Location))));
            Console.WriteLine("Evidence: "+directory);Start(executable);Pass("native-window-existing-server-ready");Capture("connection");
            string settingsPath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"HEManager","settings.json");
            string originalTheme="system";
            if(File.Exists(settingsPath)) {using var value=JsonDocument.Parse(File.ReadAllText(settingsPath));if(value.RootElement.TryGetProperty("Theme",out var theme))originalTheme=theme.GetString()??"system";}
            SelectNavigation("NavigateSettings");
            Theme("深色");Capture("theme-dark");Theme("浅色");Capture("theme-light");
            Theme(originalTheme switch {"dark"=>"深色","light"=>"浅色",_=>"跟随系统"});
            Pass("native-navigation-theme-switch-and-restore");SelectNavigation("NavigateAccount");Native.Activate(Hwnd());
            bool remembered=SignedIn();
            if(!remembered)Console.WriteLine("READY_FOR_LOGIN: Enter credentials directly in the Windows account window; no password is read by this test.");
            Wait(SignedIn,"Waiting for real user login was not completed",seconds);Pass(remembered?"existing-session-verified":"real-server-login");Capture("signed-in");
            string identity=Element("SignedInUser").Current.Name;
            SelectNavigation("NavigatePlayer");
            Wait(()=>
            {
                string text=Element("PlaybackDiagnostics").Current.Name;
                var match=System.Text.RegularExpressions.Regex.Match(text,"帧 ([0-9]+)");
                return match.Success && int.Parse(match.Groups[1].Value)>10 && text.Contains("render error 00000000");
            },"Local playback did not present frames");
            Capture("local-playback");SelectNavigation("NavigateAccount");Wait(SignedIn,"Account was lost after local playback");
            Require(Element("SignedInUser").Current.Name==identity,"Navigation changed account identity");Pass("same-window-local-playback-and-return");
            Close();Pass("normal-account-window-exit");
            Start(executable);Wait(SignedIn,"Remembered login was not restored");
            Require(Element("SignedInUser").Current.Name==identity,"Reopened window restored a different account");
            Pass("restart-restores-same-account");Capture("restored-account");Close();Pass("clean-exit");
            File.WriteAllText(Path.Combine(directory,"PASS"),DateTimeOffset.UtcNow.ToString("O"));return 0;
        }
        catch(Exception ex)
        {
            Console.Error.WriteLine(ex);File.WriteAllText(Path.Combine(directory,"FAIL.txt"),ex.ToString());
            try {Capture("failed");Close();} catch(Exception cleanup) {Console.Error.WriteLine(cleanup.Message);}return 1;
        }
    }
}
