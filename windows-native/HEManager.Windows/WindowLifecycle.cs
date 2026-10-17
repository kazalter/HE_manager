using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
using Windows.Graphics;

namespace HEManager.Windows;

internal sealed class WindowLifecycle
{
    readonly Window window;
    OverlappedPresenter? Normal => window.AppWindow.Presenter as OverlappedPresenter;
    RectInt32 restore;
    bool wasMaximized;
    public bool IsFullscreen { get; private set; }
    public WindowLifecycle(Window window)
    {
        this.window = window;
        ApplyMinimum();
        var area = DisplayArea.GetFromWindowId(window.AppWindow.Id, DisplayAreaFallback.Nearest).WorkArea;
        double scale = Dpi / 96d;
        int width = Math.Min(area.Width, (int)Math.Round(1200 * scale));
        int height = Math.Min(area.Height, (int)Math.Round(760 * scale));
        window.AppWindow.MoveAndResize(new(area.X + (area.Width-width)/2, area.Y + (area.Height-height)/2, width, height));
    }
    public uint Dpi => GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(window));
    public void ApplyMinimum()
    {
        if(IsFullscreen)return;
        double scale = Dpi / 96d;
        if(Normal is not { } normal)return;
        normal.PreferredMinimumWidth = (int)Math.Ceiling(860 * scale);
        normal.PreferredMinimumHeight = (int)Math.Ceiling(520 * scale);
    }
    public void HandleScaleChange()
    {
        ApplyMinimum();
        if(IsFullscreen)return;
        var work=DisplayArea.GetFromWindowId(window.AppWindow.Id,DisplayAreaFallback.Nearest).WorkArea;
        var size=window.AppWindow.Size;
        if(size.Width>work.Width || size.Height>work.Height)
        {
            int width=Math.Min(size.Width,work.Width),height=Math.Min(size.Height,work.Height);
            window.AppWindow.MoveAndResize(new(Math.Clamp(window.AppWindow.Position.X,work.X,work.X+work.Width-width),Math.Clamp(window.AppWindow.Position.Y,work.Y,work.Y+work.Height-height),width,height));
        }
    }
    public void ToggleFullscreen()
    {
        if (!IsFullscreen)
        {
            restore = new(window.AppWindow.Position.X, window.AppWindow.Position.Y, window.AppWindow.Size.Width, window.AppWindow.Size.Height);
            wasMaximized = Normal?.State == OverlappedPresenterState.Maximized;
            IsFullscreen=true;
            window.AppWindow.SetPresenter(AppWindowPresenterKind.FullScreen);
        }
        else
        {
            window.AppWindow.SetPresenter(AppWindowPresenterKind.Overlapped);
            IsFullscreen=false;
            ApplyMinimum();
            window.AppWindow.MoveAndResize(ClampToVisibleWorkArea(restore));
            if (wasMaximized) Normal?.Maximize();
        }
    }
    static RectInt32 ClampToVisibleWorkArea(RectInt32 rect)
    {
        var all = DisplayArea.FindAll();
        // Indexing avoids the WinRT IIterable projection used by foreach.
        for(int i=0;i<all.Count;i++)
        {
            var b = all[i].WorkArea;
            int overlapWidth=Math.Min(rect.X+rect.Width,b.X+b.Width)-Math.Max(rect.X,b.X);
            int titleOverlap=Math.Min(rect.Y+Math.Min(32,rect.Height),b.Y+b.Height)-Math.Max(rect.Y,b.Y);
            // Preserve intentional spanning/partly off-screen positions while the title bar remains reachable.
            if(overlapWidth>=Math.Min(128,rect.Width) && titleOverlap>=Math.Min(24,rect.Height))return rect;
        }
        var work = DisplayArea.GetFromRect(rect, DisplayAreaFallback.Nearest).WorkArea;
        int width = Math.Min(rect.Width, work.Width), height = Math.Min(rect.Height, work.Height);
        return new(Math.Clamp(rect.X,work.X,work.X+work.Width-width),Math.Clamp(rect.Y,work.Y,work.Y+work.Height-height),width,height);
    }
    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr hwnd);
}
