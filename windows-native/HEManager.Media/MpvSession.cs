using System.Runtime.InteropServices;
namespace HEManager.Media;

public sealed class MpvSession : IDisposable
{
    const string Dll = "libmpv-2.dll";
    public IntPtr Handle { get; private set; }
    public ulong ApiVersion { get; }
    public Guid SessionId { get; } = Guid.NewGuid();
    public string Preset { get; private set; } = "off";
    public event Action<string>? Log;
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern uint mpv_client_api_version();
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern IntPtr mpv_create();
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern int mpv_initialize(IntPtr h);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern void mpv_terminate_destroy(IntPtr h);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern int mpv_set_option_string(IntPtr h, [MarshalAs(UnmanagedType.LPUTF8Str)] string key, [MarshalAs(UnmanagedType.LPUTF8Str)] string value);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern int mpv_command_async(IntPtr h, ulong id, IntPtr argv);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern IntPtr mpv_get_property_string(IntPtr h, [MarshalAs(UnmanagedType.LPUTF8Str)] string key);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern void mpv_free(IntPtr p);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern IntPtr mpv_wait_event(IntPtr h, double timeout);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern int mpv_request_log_messages(IntPtr h, [MarshalAs(UnmanagedType.LPUTF8Str)] string level);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern IntPtr mpv_error_string(int error);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern int mpv_command(IntPtr h, IntPtr argv);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern int mpv_get_property(IntPtr h, [MarshalAs(UnmanagedType.LPUTF8Str)] string name, int format, out Node value);
    [DllImport(Dll, CallingConvention = CallingConvention.Cdecl)] static extern void mpv_free_node_contents(ref Node value);
    [StructLayout(LayoutKind.Explicit, Size = 16)] struct Node { [FieldOffset(0)] public IntPtr Pointer; [FieldOffset(8)] public int Format; }
    [StructLayout(LayoutKind.Sequential)] struct NodeList { public int Count; public IntPtr Values, Keys; }
    public string[] RenderPasses()
    {
        if (mpv_get_property(Handle, "vo-passes", 6, out var node) < 0) return [];
        var descriptions = new List<string>();
        try { Collect(node, descriptions); return descriptions.ToArray(); } finally { mpv_free_node_contents(ref node); }
    }
    static void Collect(Node node, List<string> descriptions)
    {
        if (node.Format is not (7 or 8)) return;
        var list = Marshal.PtrToStructure<NodeList>(node.Pointer);
        for (int i = 0; i < list.Count; i++)
        {
            var value = Marshal.PtrToStructure<Node>(list.Values + i * 16);
            if (node.Format == 8 && value.Format == 1 && Marshal.PtrToStringUTF8(Marshal.ReadIntPtr(list.Keys, i * IntPtr.Size)) == "desc") descriptions.Add(Marshal.PtrToStringUTF8(value.Pointer) ?? "");
            else Collect(value, descriptions);
        }
    }
    [StructLayout(LayoutKind.Sequential)] struct Event { public int Id, Error; public ulong UserData; public IntPtr Data; }
    [StructLayout(LayoutKind.Sequential)] struct LogMessage { public IntPtr Prefix, Level, Text; public int NumericLevel; }
    public static void Check(int result) { if (result < 0) throw new InvalidOperationException($"libmpv: {Marshal.PtrToStringUTF8(mpv_error_string(result))} ({result})"); }
    public MpvSession()
    {
        ApiVersion = mpv_client_api_version();
        if (ApiVersion >> 16 != 2 || (ApiVersion & 65535) < 6) throw new NotSupportedException($"Expected libmpv ABI 2.6+, found {ApiVersion:X}.");
        Handle = mpv_create(); if (Handle == IntPtr.Zero) throw new InvalidOperationException("mpv_create failed");
        try
        {
            foreach (var (k, v) in new (string, string)[] { ("config", "no"), ("load-scripts", "no"), ("ytdl", "no"), ("terminal", "no"), ("vo", "libmpv"), ("hwdec", "d3d11va"), ("idle", "yes"), ("keep-open", "yes"), ("osc", "no"), ("input-default-bindings", "no") }) Check(mpv_set_option_string(Handle, k, v));
            var shaderCache=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"HEManager","shader-cache");
            Directory.CreateDirectory(shaderCache);
            Check(mpv_set_option_string(Handle,"gpu-shader-cache-dir",shaderCache));
            Check(mpv_initialize(Handle)); Check(mpv_request_log_messages(Handle, "v"));
        }
        catch { Dispose(); throw; }
    }
    public void Command(params string[] args) => Send(false, args);
    public void Stop()
    {
        Send(true, ["stop"]);
        var deadline = Environment.TickCount64 + 3000;
        while (Read("idle-active") != "yes" && Environment.TickCount64 < deadline) { PumpEvents(); Thread.Sleep(10); }
        if (Read("idle-active") != "yes") Log?.Invoke("Stop did not become idle within 3 seconds");
    }
    void Send(bool synchronous, params string[] args)
    {
        ObjectDisposedException.ThrowIf(Handle == IntPtr.Zero, this);
        var pointers = args.Select(Marshal.StringToCoTaskMemUTF8).ToArray();
        var argv = Marshal.AllocHGlobal((pointers.Length + 1) * IntPtr.Size);
        try { for (int i = 0; i < pointers.Length; i++) Marshal.WriteIntPtr(argv, i * IntPtr.Size, pointers[i]); Marshal.WriteIntPtr(argv, pointers.Length * IntPtr.Size, IntPtr.Zero); Check(synchronous ? mpv_command(Handle, argv) : mpv_command_async(Handle, 0, argv)); }
        finally { foreach (var p in pointers) Marshal.FreeCoTaskMem(p); Marshal.FreeHGlobal(argv); }
    }
    public string Read(string property)
    {
        if (Handle == IntPtr.Zero) return "";
        var p = mpv_get_property_string(Handle, property);
        try { return Marshal.PtrToStringUTF8(p) ?? ""; } finally { if (p != IntPtr.Zero) mpv_free(p); }
    }
    public void PumpEvents()
    {
        for (int i = 0; i < 256 && Handle != IntPtr.Zero; i++)
        {
            var e = Marshal.PtrToStructure<Event>(mpv_wait_event(Handle, 0)); if (e.Id == 0) break;
            if (e.Id == 2 && e.Data != IntPtr.Zero) { var l = Marshal.PtrToStructure<LogMessage>(e.Data); Log?.Invoke($"[{Marshal.PtrToStringUTF8(l.Prefix)}] {Marshal.PtrToStringUTF8(l.Text)?.TrimEnd()}"); }
            if (e.Error < 0) Log?.Invoke($"mpv event {e.Id} failed: {Marshal.PtrToStringUTF8(mpv_error_string(e.Error))}");
        }
    }
    public void SetPreset(string preset, string shaderRoot)
    {
        string[] shared = ["Anime4K_Clamp_Highlights.glsl"];
        string[] names = preset switch
        {
            "off" => [],
            "efficiency" => [.. shared, "Anime4K_Restore_CNN_M.glsl", "Anime4K_Upscale_CNN_x2_M.glsl", "Anime4K_AutoDownscalePre_x2.glsl", "Anime4K_AutoDownscalePre_x4.glsl", "Anime4K_Upscale_CNN_x2_M.glsl"],
            "quality" => [.. shared, "Anime4K_Restore_CNN_VL.glsl", "Anime4K_Upscale_CNN_x2_VL.glsl", "Anime4K_AutoDownscalePre_x2.glsl", "Anime4K_AutoDownscalePre_x4.glsl", "Anime4K_Upscale_CNN_x2_M.glsl"],
            _ => throw new ArgumentOutOfRangeException(nameof(preset))
        };
        var paths = names.Select(n => Path.Combine(shaderRoot, n)).ToArray();
        foreach (var p in paths) if (!File.Exists(p)) throw new FileNotFoundException("Shader missing", p);
        Command("change-list", "glsl-shaders", "set", string.Join(';', paths)); Preset = preset;
    }
    // Graphics render context must already be stopped/freed by its owner.
    public void Dispose() { if (Handle != IntPtr.Zero) { mpv_terminate_destroy(Handle); Handle = IntPtr.Zero; } }
}
