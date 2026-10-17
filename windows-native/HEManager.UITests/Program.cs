using System.Diagnostics;
using System.IO;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows.Automation;
using Drawing = System.Drawing;

namespace HEManager.UITests;

internal static class Program
{
    static string directory = "";
    static Process? app;
    static string executable = "";
    static readonly List<object> results = [];
    static JsonElement State()
    {
        for (int i=0;i<40;i++)
        {
            try
            {
                using var file=new FileStream(Path.Combine(directory,"state.json"),FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);
                using var json=JsonDocument.Parse(file);
                return json.RootElement.Clone();
            }
            catch(IOException) {Thread.Sleep(50);}
            catch(JsonException) {Thread.Sleep(50);}
        }
        throw new Exception("No readable probe state");
    }
    static double Number(JsonElement e,string key)=>e.GetProperty(key).GetDouble();
    static bool Flag(JsonElement e,string key)=>e.GetProperty(key).GetBoolean();
    static string Text(JsonElement e,string key)=>e.GetProperty(key).ToString();
    static void Require(bool condition,string message) {if(!condition)throw new Exception(message);}
    static JsonElement Wait(Func<JsonElement,bool> predicate,string message,int seconds=15)
    {
        var watch=Stopwatch.StartNew();
        while(watch.Elapsed.TotalSeconds<seconds)
        {
            if(app?.HasExited==true)throw new Exception("Application exited: "+app.ExitCode);
            var state=State();if(predicate(state))return state;Thread.Sleep(100);
        }
        throw new TimeoutException(message+"; last state="+State());
    }
    static AutomationElement Window()=>AutomationElement.FromHandle(new IntPtr(State().GetProperty("hwnd").GetInt64()));
    static AutomationElement Element(string id)
    {
        for(int i=0;i<30;i++)
        {
            var element=Window().FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,id));
            if(element!=null)return element;
            Thread.Sleep(100);
        }
        var tree=Window().FindAll(TreeScope.Descendants,Condition.TrueCondition).Cast<AutomationElement>().Select(e=>new {id=e.Current.AutomationId,name=e.Current.Name,type=e.Current.ControlType.ProgrammaticName});
        File.WriteAllText(Path.Combine(directory,"missing-control-tree.json"),JsonSerializer.Serialize(tree));
        Capture("missing-control");
        throw new Exception("Missing accessible control: "+id);
    }
    static void Invoke(string id)=>((InvokePattern)Element(id).GetCurrentPattern(InvokePattern.Pattern)).Invoke();
    static void Value(string id,double value)=>((RangeValuePattern)Element(id).GetCurrentPattern(RangeValuePattern.Pattern)).SetValue(value);
    static void Checkpoint(string name)
    {
        var state=State();results.Add(new {name,state});
        File.WriteAllText(Path.Combine(directory,"results.json"),JsonSerializer.Serialize(results,new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine("PASS "+name);
    }
    static void Capture(string name)
    {
        var hwnd=new IntPtr(State().GetProperty("hwnd").GetInt64());
        for(int attempt=0;attempt<10;attempt++)
        {
            Native.Activate(hwnd);Thread.Sleep(200);
            if(Native.GetForegroundWindow()==hwnd)break;
        }
        if(Native.GetForegroundWindow()!=hwnd)
        {
            File.WriteAllText(Path.Combine(directory,name+"-capture-skipped.txt"),"Player was not foreground; screenshot omitted to avoid capturing another application.");
            return;
        }
        Require(Native.GetWindowRect(hwnd,out var rect),"Cannot read window bounds");
        var area=Drawing.Rectangle.FromLTRB(rect.Left,rect.Top,rect.Right,rect.Bottom);
        var visible=Drawing.Rectangle.Intersect(area,System.Windows.Forms.SystemInformation.VirtualScreen);
        using var bitmap=new Drawing.Bitmap(visible.Width,visible.Height);
        using(var graphics=Drawing.Graphics.FromImage(bitmap))graphics.CopyFromScreen(visible.Location,Drawing.Point.Empty,visible.Size);
        bitmap.Save(Path.Combine(directory,name+".png"),ImageFormat.Png);
    }
    static void Key(ushort key,string focus="Pause")
    {
        var hwnd=new IntPtr(State().GetProperty("hwnd").GetInt64());
        Native.Activate(hwnd);Element(focus).SetFocus();Thread.Sleep(100);
        Require(Native.GetForegroundWindow()==hwnd,$"App is not foreground; input injection refused: actual={Native.GetForegroundWindow():X}, expected={hwnd:X}, visible={Native.IsWindowVisible(hwnd)}, iconic={Native.IsIconic(hwnd)}");
        var inputs=new[]{Native.Keyboard(key,false),Native.Keyboard(key,true)};
        Require(Native.SendInput(2,inputs,Marshal.SizeOf<Native.INPUT>())==2,"Input injection failed");
    }
    static void Close()
    {
        if(app==null||app.HasExited)return;
        Native.PostMessage(new IntPtr(State().GetProperty("hwnd").GetInt64()),0x0010,IntPtr.Zero,IntPtr.Zero);
        Require(app.WaitForExit(10000),"Application did not close within 10 seconds");
        Require(app.ExitCode==0,"Application exit was not clean");
        string log=Path.Combine(Path.GetDirectoryName(directory)!,"player.log");
        if(File.Exists(log))
        {
            File.Copy(log,Path.Combine(directory,"player.log"),true);
            string text=File.ReadAllText(log);
            Require(text.Contains("shutdown complete"),"Missing orderly renderer shutdown");
            Require(!text.Contains("Fullscreen transition failed:") && !text.Contains("Stop did not become idle"),"Lifecycle error recorded in player log");
        }
    }
    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            Native.SetProcessDpiAwarenessContext(new IntPtr(-4));
            executable=Path.GetFullPath(args[0]);
            string mode=args.Length>1?args[1]:"ui";
            directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"HEManager","WN01","acceptance-"+mode+"-"+DateTime.Now.ToString("yyyyMMdd-HHmmss"));
            Directory.CreateDirectory(directory);
            string buildInfo=Path.Combine(Path.GetDirectoryName(executable)!,"build-info.json");
            if(File.Exists(buildInfo))File.Copy(buildInfo,Path.Combine(directory,"build-info.json"));
            File.WriteAllText(Path.Combine(directory,"test-binary-sha256.txt"),Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(typeof(Program).Assembly.Location))));
            File.WriteAllText(Path.Combine(directory,"inventory.json"),JsonSerializer.Serialize(System.Windows.Forms.Screen.AllScreens.Select(s=>new {s.DeviceName,s.Primary,bounds=new {s.Bounds.X,s.Bounds.Y,s.Bounds.Width,s.Bounds.Height}})));
            Console.WriteLine("Evidence: "+directory);
            app=Process.Start(new ProcessStartInfo(executable){ArgumentList={"--probe",directory}})??throw new Exception("Cannot launch app");
            Thread.Sleep(1500);
            Wait(s=>Number(s,"frames")>10&&Number(s,"graphicsError")==0,"No embedded frames");
            if(mode=="scales")ObserveScales(args.Length>2?int.Parse(args[2]):600);
            else if(mode=="soak")Soak(args.Length>2?int.Parse(args[2]):1800);
            else Interactions(mode=="ui");
            Close();Checkpoint("clean-exit");
            File.WriteAllText(Path.Combine(directory,"PASS"),DateTimeOffset.UtcNow.ToString("O"));
            return 0;
        }
        catch(Exception ex)
        {
            Console.Error.WriteLine(ex);
            if(directory!="")File.WriteAllText(Path.Combine(directory,"FAIL.txt"),ex.ToString());
            try{Close();}catch(Exception cleanup){Console.Error.WriteLine(cleanup);}
            return 1;
        }
    }
    static void CheckControlsInsideWindow()
    {
        var window=State().GetProperty("window");
        foreach(string id in new[]{"OpenSample","Pause","Volume","Seek","Preset","Fullscreen"})
        {
            var b=Element(id).Current.BoundingRectangle;
            Require(!b.IsEmpty && b.Left>=Number(window,"x")-2 && b.Top>=Number(window,"y")-2 && b.Right<=Number(window,"x")+Number(window,"width")+2 && b.Bottom<=Number(window,"y")+Number(window,"height")+2,"Control clipped: "+id);
        }
    }
    static void ResizeAndFocus()
    {
        var baseline=State();double scale=Number(baseline,"scale");
        var transform=(TransformPattern)Window().GetCurrentPattern(TransformPattern.Pattern);
        transform.Resize(Math.Ceiling(860*scale),Math.Ceiling(520*scale));
        Thread.Sleep(800);CheckControlsInsideWindow();
        var before=Number(State(),"frames");Wait(s=>Number(s,"frames")>before+3,"Rendering stalled at minimum window size");
        Capture("minimum-window");Checkpoint("minimum-window-controls");
        transform.Resize(Number(baseline.GetProperty("window"),"width"),Number(baseline.GetProperty("window"),"height"));
        using var other=new System.Windows.Forms.Form {Text="HE Manager focus test",Width=300,Height=120,ShowInTaskbar=true};
        other.Show();Native.Activate(other.Handle);System.Windows.Forms.Application.DoEvents();
        Require(Native.GetForegroundWindow()==other.Handle,"Could not move focus to test window");
        before=Number(State(),"frames");Thread.Sleep(1200);
        Wait(s=>Number(s,"frames")>before+3,"Rendering stalled while another window has focus");
        Native.Activate(new IntPtr(State().GetProperty("hwnd").GetInt64()));other.Close();
        Require(Native.GetForegroundWindow()==new IntPtr(State().GetProperty("hwnd").GetInt64()),"Focus did not return to player");
        Checkpoint("focus-away-return-rendering");
    }
    static void Interactions(bool inject)
    {
        var baseline=State();string session=Text(baseline,"session"),mpv=Text(baseline,"mpv"),render=Text(baseline,"render");
        foreach(string id in new[]{"Pause","Volume","Seek","Preset","Fullscreen"})
        {
            var control=Element(id);Require(control.Current.IsEnabled&&!control.Current.IsOffscreen,"Control unavailable: "+id);
            Require(!control.Current.BoundingRectangle.IsEmpty,"Empty control bounds: "+id);
        }
        if(inject) {Capture("window-initial");ResizeAndFocus();}Checkpoint("overlay-accessibility");
        Invoke("Pause");var paused=Wait(s=>Text(s,"paused")=="yes","Pause button failed");
        double position=Number(paused,"time");Thread.Sleep(1200);Require(Math.Abs(Number(State(),"time")-position)<0.15,"Pause did not stop position");
        Value("Seek",4);Wait(s=>Math.Abs(Number(s,"time")-4)<0.25,"Seek did not reach 4 seconds");
        Value("Volume",37);Wait(s=>Math.Abs(Number(s,"volume")-37)<0.1,"Volume slider failed");Checkpoint("pause-seek-volume");
        // The focused Button consumes Space exactly once, without root-level double toggling.
        if(inject) {Key(0x20);Wait(s=>Text(s,"paused")=="no","Space on button did not resume");Checkpoint("space-button-single-toggle");Key(0x7A);}
        else {Invoke("Pause");Wait(s=>Text(s,"paused")=="no","Resume failed");Invoke("Fullscreen");}
        Wait(s=>Flag(s,"fullscreen"),"Fullscreen entry failed");
        var fullscreen=State();
        var bounds=fullscreen.GetProperty("window");var display=fullscreen.GetProperty("display");
        Require(Math.Abs(Number(bounds,"width")-Number(display,"width"))<=2 && Math.Abs(Number(bounds,"height")-Number(display,"height"))<=2,"Fullscreen is not on current display");
        if(inject) {Capture("fullscreen");Key(0x1B);} else Invoke("Fullscreen");
        Wait(s=>!Flag(s,"fullscreen"),"Fullscreen exit failed");
        var restored=State().GetProperty("window");var original=baseline.GetProperty("window");
        foreach(string key in new[]{"x","y","width","height"})Require(Math.Abs(Number(restored,key)-Number(original,key))<=2,"Window restore mismatch: "+key);
        Checkpoint(inject?"f11-esc-original-bounds":"uia-fullscreen-original-bounds");
        if(inject)
        {
            Key(0x7A);Wait(s=>Flag(s,"fullscreen"),"F11 re-entry failed");
            ((ExpandCollapsePattern)Element("Preset").GetCurrentPattern(ExpandCollapsePattern.Pattern)).Expand();
            Thread.Sleep(300);Key(0x1B,"Preset");
            Wait(s=>!Flag(s,"fullscreen"),"First Esc from ComboBox did not exit fullscreen");
            Checkpoint("escape-from-preset-exits-fullscreen");
            Key(0x20,"Volume");Thread.Sleep(700);
            Require(Text(State(),"paused")=="no","Space on slider toggled playback");
            Checkpoint("slider-keyboard-isolation");
        }
        var hwnd=new IntPtr(State().GetProperty("hwnd").GetInt64());
        Native.ShowWindow(hwnd,6);Thread.Sleep(1500);Native.ShowWindow(hwnd,9);
        var before=Number(State(),"frames");Wait(s=>Number(s,"frames")>before+3,"Minimize/restore stalled rendering");Checkpoint("minimize-restore");
        for(int i=0;i<50;i++)
        {
            int count=State().GetProperty("loadedFiles").GetInt32();double frames=Number(State(),"frames");
            Invoke("OpenSample");Wait(s=>s.GetProperty("loadedFiles").GetInt32()>count&&Number(s,"frames")>frames+2&&Number(s,"time")>0.08,"Video reload failed "+i);
        }
        var end=State();Require(Text(end,"session")==session&&Text(end,"mpv")==mpv&&Text(end,"render")==render,"Native session objects were recreated");
        Require(Number(end,"graphicsError")==0,"Render failure after input/lifecycle tests");
        Checkpoint("50-video-reloads-same-native-session");if(inject)Capture("window-after-reloads");
    }
    static void ObserveScales(int seconds)
    {
        double[] expected=Math.Abs(Number(State(),"scale")-1.5)<0.02 ? [1.5,2,1] : [1,1.5,2,1];int index=0;
        var watch=Stopwatch.StartNew();
        while(index<expected.Length && watch.Elapsed.TotalSeconds<seconds)
        {
            var state=State();double scale=Number(state,"scale");
            if(Math.Abs(scale-expected[index])>0.02){Thread.Sleep(250);continue;}
            double before=Number(state,"frames");
            state=Wait(s=>Number(s,"frames")>before+3 && Number(s,"readbackFrame")>before && Number(s,"graphicsError")==0,"No fresh GPU readback after DPI change");
            var surface=state.GetProperty("surface");
            Require(Math.Abs(Number(surface,"pixelWidth")-Number(surface,"width")*scale)<=2,"DPI render width mismatch");
            Require(Math.Abs(Number(surface,"pixelHeight")-Number(surface,"height")*scale)<=2,"DPI render height mismatch");
            Require(Math.Abs(Number(state,"dpi")-scale*96)<=1,"Window DPI differs from XAML scale");
            Require(Number(state,"pixelSpread")>32,"Blank GPU output after DPI change");
            var window=state.GetProperty("window");
            foreach(string id in new[]{"OpenSample","Pause","Volume","Seek","Preset","Fullscreen"})
            {
                var b=Element(id).Current.BoundingRectangle;
                Require(!b.IsEmpty && b.Left>=Number(window,"x")-2 && b.Right<=Number(window,"x")+Number(window,"width")+2 && b.Bottom<=Number(window,"y")+Number(window,"height")+2,"Control clipped at DPI "+scale+": "+id);
            }
            Checkpoint("actual-dpi-"+scale.ToString(System.Globalization.CultureInfo.InvariantCulture)+"-step-"+index);
            Capture("dpi-"+(int)(scale*100)+"-step-"+index);index++;
        }
        Require(index==expected.Length,"DPI sequence incomplete: need real 100%, 150%, 200%, then restore 100%; completed "+index);
    }
    static void SelectQuality()
    {
        ((ExpandCollapsePattern)Element("Preset").GetCurrentPattern(ExpandCollapsePattern.Pattern)).Expand();
        Thread.Sleep(300);
        ((SelectionItemPattern)Element("PresetQuality").GetCurrentPattern(SelectionItemPattern.Pattern)).Select();
        Wait(s=>Text(s,"preset")=="quality" && s.GetProperty("passes").EnumerateArray().Any(p=>p.ToString().Contains("Restore-CNN-(VL)")),"Quality render pipeline did not become active",30);
    }
    static void Soak(int seconds)
    {
        SelectQuality();Thread.Sleep(30000); // exclude startup/shader warmup from steady observation
        var start=State();string session=Text(start,"session");
        Checkpoint("soak-baseline-after-warmup");
        var watch=Stopwatch.StartNew();double previous=Number(start,"frames");int samples=0;
        while(watch.Elapsed.TotalSeconds<seconds)
        {
            Thread.Sleep(5000);var state=State();
            Require(Number(state,"frames")>previous,"No presented frames during soak");previous=Number(state,"frames");
            Require(Text(state,"session")==session&&Number(state,"graphicsError")==0,"Session/render failure during soak");
            Require(Text(state,"hwdec")=="d3d11va","Hardware decode lost during soak");
            if(++samples%12==0)Checkpoint("soak-minute-"+(int)watch.Elapsed.TotalMinutes);
        }
        var end=State();
        var growth=new {seconds,privateBytes=Number(end,"privateBytes")-Number(start,"privateBytes"),handles=Number(end,"handles")-Number(start,"handles"),threads=Number(end,"threads")-Number(start,"threads"),gpuBytes=Number(end,"gpuBytes")-Number(start,"gpuBytes"),presentedFrames=Number(end,"frames")-Number(start,"frames")};
        File.WriteAllText(Path.Combine(directory,"resource-growth.json"),JsonSerializer.Serialize(growth,new JsonSerializerOptions{WriteIndented=true}));
        Require(growth.privateBytes<=64*1024*1024,"Private memory grew beyond 64 MiB after warmup");
        Require(growth.handles<=32 && growth.threads<=8,"Handles/threads kept growing after warmup");
        Require(Number(start,"gpuBytes")>=0 && growth.gpuBytes<=16*1024*1024,"GPU budget usage unavailable or grew beyond 16 MiB after warmup");
        Checkpoint("soak-complete-"+seconds+"s");Capture("soak-final");
    }
}
internal static class Native
{
    [StructLayout(LayoutKind.Sequential)] internal struct RECT {public int Left,Top,Right,Bottom;}
    [StructLayout(LayoutKind.Sequential)] internal struct INPUT {public uint type; public InputUnion data;}
    [StructLayout(LayoutKind.Explicit)] internal struct InputUnion {[FieldOffset(0)]public MOUSEINPUT mouse;[FieldOffset(0)]public KEYBDINPUT keyboard;}
    [StructLayout(LayoutKind.Sequential)] internal struct MOUSEINPUT {public int x,y;public uint data,flags,time;public UIntPtr extra;}
    [StructLayout(LayoutKind.Sequential)] internal struct KEYBDINPUT {public ushort key,scan;public uint flags,time;public UIntPtr extra;}
    internal static INPUT Keyboard(ushort key,bool up)=>new(){type=1,data=new(){keyboard=new(){key=key,flags=up?2u:0u}}};
    internal static void Activate(IntPtr hwnd)
    {
        ShowWindow(hwnd,9);
        uint current=GetCurrentThreadId(),fgThread=GetWindowThreadProcessId(GetForegroundWindow(),out _);
        bool attached=fgThread!=0 && fgThread!=current && AttachThreadInput(current,fgThread,true);
        try {BringWindowToTop(hwnd);SetForegroundWindow(hwnd);}
        finally {if(attached)AttachThreadInput(current,fgThread,false);}
    }
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint processId);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint from,uint to,bool attach);
    [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] internal static extern uint SendInput(uint count,INPUT[] inputs,int size);
    [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr hwnd,out RECT rect);
    [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr hwnd,int command);
    [DllImport("user32.dll")] internal static extern bool PostMessage(IntPtr hwnd,uint message,IntPtr w,IntPtr l);
}
