using HEManager.Media;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Input;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;
using Windows.System;
using Windows.Storage.Pickers;
namespace HEManager.Windows;

public partial class MainWindow : Window
{
    MpvSession? player;
    IntPtr bridge;
    readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromMilliseconds(100) };
    bool updating, closing;
    readonly WindowLifecycle lifecycle;
    ProbeRecorder? probe;
    bool full => lifecycle.IsFullscreen;
    long lastProbe;
    int loads;
    readonly string reportDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HEManager", "WN01");
    StreamWriter? log;
    int ticks;
    readonly bool smoke = Environment.GetCommandLineArgs().Contains("--smoke");
    readonly List<object> samples = [];
    [DllImport("HEManager.Graphics.dll", CallingConvention = CallingConvention.Cdecl)] static extern int he_graphics_create(IntPtr mpv, IntPtr panel, out IntPtr b);
    [DllImport("HEManager.Graphics.dll", CallingConvention = CallingConvention.Cdecl)] static extern void he_graphics_resize(IntPtr b, uint w, uint h, float scale);
    [DllImport("HEManager.Graphics.dll", CallingConvention = CallingConvention.Cdecl)] static extern ulong he_graphics_frames(IntPtr b);
    [DllImport("HEManager.Graphics.dll", CallingConvention = CallingConvention.Cdecl)] static extern int he_graphics_error(IntPtr b);
    [DllImport("HEManager.Graphics.dll", CallingConvention = CallingConvention.Cdecl)] static extern void he_graphics_destroy(IntPtr b);
    [DllImport("HEManager.Graphics.dll", CallingConvention = CallingConvention.Cdecl)] static extern void he_graphics_probe(IntPtr b);
    [DllImport("HEManager.Graphics.dll", CallingConvention = CallingConvention.Cdecl)] static extern uint he_graphics_pixel_spread(IntPtr b);
    public MainWindow()
    {
        InitializeComponent();
        lifecycle = new(this);
        Root.AddHandler(UIElement.KeyDownEvent, new KeyEventHandler(OnKeyDown), true);
        AppWindow.Changed += WindowChanged;
        timer.Tick += Tick; Closed += (_, _) => Shutdown();
    }
    void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (player != null) return;
        Directory.CreateDirectory(reportDir); log = new(Path.Combine(reportDir, "player.log"), false) { AutoFlush = true };
        try
        {
            player = new(); player.Log += line => log?.WriteLine(line);
            var p = WinRT.MarshalInspectable<SwapChainPanel>.FromManaged(Video);
            try { int result = he_graphics_create(player.Handle, p, out bridge); if (result != 0) throw new InvalidOperationException($"D3D11 render context failed: {result:X8}"); }
            finally { Marshal.Release(p); }
            Video.XamlRoot.Changed += RootChanged;
            ResizeVideo(); timer.Start(); player.Command("set", "volume", "70");
            string[] arguments=Environment.GetCommandLineArgs();
            int probeIndex=Array.IndexOf(arguments,"--probe");
            if(probeIndex>=0 && probeIndex+1<arguments.Length)probe=new(arguments[probeIndex+1]);
            if (smoke || probe!=null) { he_graphics_probe(bridge); player.Command("set", "loop-file", "inf"); }
            OpenSample(null!, null!);
        }
        catch (Exception ex) { Diagnostics.Text = ex.Message; log?.WriteLine(ex); Shutdown(); if(smoke)Close(); }
    }
    void RootChanged(Microsoft.UI.Xaml.XamlRoot sender, Microsoft.UI.Xaml.XamlRootChangedEventArgs e) {lifecycle.HandleScaleChange();ResizeVideo();}
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
    void WindowChanged(AppWindow sender, AppWindowChangedEventArgs args)
    {
        if(bridge!=IntPtr.Zero)he_graphics_suspend(bridge, IsIconic(WinRT.Interop.WindowNative.GetWindowHandle(this)));
    }
    void ResizeVideo() { if (bridge != IntPtr.Zero) { double scale = Video.XamlRoot?.RasterizationScale ?? 1; he_graphics_resize(bridge, (uint)Math.Max(1, Video.ActualWidth * scale), (uint)Math.Max(1, Video.ActualHeight * scale), (float)scale); } }
    void VideoSizeChanged(object sender, SizeChangedEventArgs e) => ResizeVideo();
    void LoadFile(string path) { ++loads; player?.Command("loadfile",path,"replace"); player?.Command("set","pause","no"); }
    void OpenSample(object sender, RoutedEventArgs e) => LoadFile(Path.Combine(AppContext.BaseDirectory,"resources","sample.mp4"));
    async void OpenFile(object sender, RoutedEventArgs e)
    {
        try { var picker = new FileOpenPicker(); WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this)); foreach (var ext in new[] { ".mp4", ".mkv", ".webm", ".mov" }) picker.FileTypeFilter.Add(ext); var file = await picker.PickSingleFileAsync(); if (file != null && !closing) LoadFile(file.Path); }
        catch (Exception ex) { Diagnostics.Text = ex.Message; }
    }
    void Pause(object sender, RoutedEventArgs e) => player?.Command("cycle", "pause");
    void VolumeChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e) => player?.Command("set", "volume", e.NewValue.ToString(CultureInfo.InvariantCulture));
    void SeekChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e) { if (!updating) player?.Command("seek", e.NewValue.ToString(CultureInfo.InvariantCulture), "absolute"); }
    void PresetChanged(object sender, SelectionChangedEventArgs e)
    {
        try { if (Preset.SelectedItem is ComboBoxItem item) player?.SetPreset((string)item.Tag, Path.Combine(AppContext.BaseDirectory, "resources", "shaders")); }
        catch (Exception ex) { Diagnostics.Text = ex.Message; log?.WriteLine(ex); }
    }
    void Fullscreen(object sender, RoutedEventArgs e) => ToggleFullscreen();
    void ToggleFullscreen()
    {
        try {lifecycle.ToggleFullscreen();}
        catch(Exception ex) {log?.WriteLine("Fullscreen transition failed: "+ex);Diagnostics.Text=ex.Message;return;}
        Chrome.Visibility=full?Visibility.Collapsed:Visibility.Visible;
        log?.WriteLine($"fullscreen={full}; session={player?.SessionId}; position={player?.Read("time-pos")}");
    }
    void OnKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if(e.Key==VirtualKey.F11) {ToggleFullscreen();e.Handled=true;return;}
        if(e.Key==VirtualKey.Escape && full)
        {
            // Viewer contract: the first Escape exits fullscreen, including from its controls.
            if(Preset.IsDropDownOpen)Preset.IsDropDownOpen=false;
            ToggleFullscreen();e.Handled=true;return;
        }
        // Buttons/Sliders/ComboBox retain native Space/arrow key behavior.
        if(e.Key==VirtualKey.Space && !e.Handled && !ControlOwnsKeyboard(e.OriginalSource as DependencyObject))
        {player?.Command("cycle","pause");e.Handled=true;}
    }
    static bool ControlOwnsKeyboard(DependencyObject? source)
    {
        while(source!=null)
        {
            if(source is Microsoft.UI.Xaml.Controls.Primitives.ButtonBase or Slider or ComboBox or ComboBoxItem or TextBox)return true;
            source=VisualTreeHelper.GetParent(source);
        }
        return false;
    }

    static double Number(string value) => double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out double n) ? n : 0;
    object Snapshot() => new { tick = ticks, session = player?.SessionId, frames = bridge == IntPtr.Zero ? 0 : he_graphics_frames(bridge), graphicsError = bridge == IntPtr.Zero ? 0 : he_graphics_error(bridge), hwdec = player?.Read("hwdec-current"), decoder = player?.Read("video-codec"), time = player?.Read("time-pos"), pixelSpread = bridge == IntPtr.Zero ? 0 : he_graphics_pixel_spread(bridge), preset = player?.Preset, shaders = player?.Read("glsl-shaders"), passes = player?.RenderPasses(), fullscreen = full };
    object ProbeSnapshot()
    {
        using var process=Process.GetCurrentProcess();
        var area=DisplayArea.GetFromWindowId(AppWindow.Id,DisplayAreaFallback.Nearest);
        return new {
            timestamp=DateTimeOffset.UtcNow,hwnd=WinRT.Interop.WindowNative.GetWindowHandle(this).ToInt64(), session=player?.SessionId, mpv=player?.Handle.ToString("X"),render=bridge.ToString("X"),loads,loadedFiles=player?.LoadedFiles,
            frames=he_graphics_frames(bridge),readbackFrame=he_graphics_readback_frame(bridge),graphicsError=he_graphics_error(bridge),pixelSpread=he_graphics_pixel_spread(bridge),
            hwdec=player?.Read("hwdec-current"),time=Number(player?.Read("time-pos")??""),duration=Number(player?.Read("duration")??""),
            paused=player?.Read("pause"),volume=Number(player?.Read("volume")??""),dropCount=Number(player?.Read("frame-drop-count")??""),
            preset=player?.Preset,passes=player?.RenderPasses(),fullscreen=full,presenter=AppWindow.Presenter.Kind.ToString(),
            window=new {x=AppWindow.Position.X,y=AppWindow.Position.Y,width=AppWindow.Size.Width,height=AppWindow.Size.Height},
            scale=Video.XamlRoot.RasterizationScale,dpi=lifecycle.Dpi,
            surface=new {width=Video.ActualWidth,height=Video.ActualHeight,pixelWidth=he_graphics_width(bridge),pixelHeight=he_graphics_height(bridge)},
            display=new {id=area.DisplayId.Value,x=area.OuterBounds.X,y=area.OuterBounds.Y,width=area.OuterBounds.Width,height=area.OuterBounds.Height},
            privateBytes=process.PrivateMemorySize64,workingSet=process.WorkingSet64,handles=process.HandleCount,threads=process.Threads.Count,
            gpuBytes=he_graphics_gpu_bytes(bridge)
        };
    }
    [DllImport("HEManager.Graphics.dll",CallingConvention=CallingConvention.Cdecl)] static extern void he_graphics_suspend(IntPtr b,[MarshalAs(UnmanagedType.I1)]bool suspended);
    [DllImport("HEManager.Graphics.dll",CallingConvention=CallingConvention.Cdecl)] static extern long he_graphics_gpu_bytes(IntPtr b);
    [DllImport("HEManager.Graphics.dll",CallingConvention=CallingConvention.Cdecl)] static extern uint he_graphics_width(IntPtr b);
    [DllImport("HEManager.Graphics.dll",CallingConvention=CallingConvention.Cdecl)] static extern uint he_graphics_height(IntPtr b);
    [DllImport("HEManager.Graphics.dll",CallingConvention=CallingConvention.Cdecl)] static extern ulong he_graphics_readback_frame(IntPtr b);
    void Tick(object? sender, object e)
    {
        if (player == null || closing) return;
        try
        {
            player.PumpEvents(); ++ticks;
            double time = Number(player.Read("time-pos")), duration = Number(player.Read("duration"));
            updating = true; Seek.Maximum = Math.Max(1, duration); Seek.Value = Math.Clamp(time, 0, Seek.Maximum); updating = false;
            Position.Text = $"{TimeSpan.FromSeconds(time):mm\\:ss} / {TimeSpan.FromSeconds(duration):mm\\:ss}";
            Diagnostics.Text = $"D3D11 → SwapChainPanel | {player.Read("hwdec-current")} | {player.Read("video-params/w")}×{player.Read("video-params/h")}\n帧 {he_graphics_frames(bridge)} · 掉帧 {player.Read("frame-drop-count")} · {player.Preset} · render error {he_graphics_error(bridge):X8}";
            if(probe!=null && Environment.TickCount64-lastProbe>=500)
            {probe.Record(ProbeSnapshot());lastProbe=Environment.TickCount64;}
            if (smoke)
            {
                if (ticks % 20 == 0 || ticks is 101 or 121 or 139 or 179 or 229) samples.Add(Snapshot());
                if (ticks == 30) Preset.SelectedIndex = 1;
                if (ticks == 60) Preset.SelectedIndex = 2;
                if (ticks == 90) Preset.SelectedIndex = 0;
                if (ticks >= 100 && ticks < 180 && ticks % 2 == 0) ToggleFullscreen();
                if (ticks == 185) OpenSample(null!, null!);
                if (ticks == 230) { File.WriteAllText(Path.Combine(reportDir, "smoke.json"), JsonSerializer.Serialize(samples, new JsonSerializerOptions { WriteIndented = true })); Close(); }
            }
        }
        catch (Exception ex) { log?.WriteLine(ex); Diagnostics.Text = ex.Message; timer.Stop(); }
    }
    void Shutdown()
    {
        if (closing) return; closing = true; timer.Stop();
        AppWindow.Changed -= WindowChanged;
        probe?.Dispose();probe=null;
        if (Video.XamlRoot != null) Video.XamlRoot.Changed -= RootChanged;
        // Stop decoding while the independent render thread can still service mpv.
        if (player != null) { try { player.Stop(); player.PumpEvents(); } catch (Exception ex) { log?.WriteLine(ex); } }
        // Render callback/thread/context stop before mpv core; panel detached on UI thread.
        if (bridge != IntPtr.Zero) { he_graphics_destroy(bridge); bridge = IntPtr.Zero; }
        player?.PumpEvents(); player?.Dispose(); player = null; log?.WriteLine("shutdown complete"); log?.Dispose(); log = null;
    }
}
