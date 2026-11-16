// Explorer wallpaper host. Runs in its own process; the Electron window belongs
// to HE Manager. Stdout is a small line protocol, never arbitrary shell input.
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <commctrl.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

struct DesktopWindows { HWND icons = nullptr; HWND layer = nullptr; HWND view = nullptr; bool raised = false; };

static BOOL CALLBACK findDesktop(HWND top, LPARAM parameter) {
    auto* result = reinterpret_cast<DesktopWindows*>(parameter);
    HWND view = FindWindowExW(top, nullptr, L"SHELLDLL_DefView", nullptr);
    if (!view) return TRUE;
    result->view = view;
    result->icons = FindWindowExW(view, nullptr, L"SysListView32", nullptr);
    // Since Windows 11 24H2 a raised Progman has layered children. The
    // wallpaper must be a sibling immediately below the desktop icon view.
    result->raised = (GetWindowLongPtrW(top, GWL_EXSTYLE) & WS_EX_NOREDIRECTIONBITMAP) != 0;
    result->layer = result->raised ? top : FindWindowExW(nullptr, top, L"WorkerW", nullptr);
    return FALSE;
}

static bool desktopForeground(HWND foreground, HWND progman, const DesktopWindows& desktop) {
    if (!foreground) return false;
    const HWND root = GetAncestor(foreground, GA_ROOT);
    return root == progman || root == desktop.layer ||
        (desktop.icons && root == GetAncestor(desktop.icons, GA_ROOT));
}

// Chromium may retain non-client insets even for a frameless child window.
// Match the drawable client area, not just the outer window, to the monitor.
static void fitClientToMonitor(HWND target, const DesktopWindows& desktop, HWND insertAfter, const RECT& monitor) {
    RECT window{}, client{};
    if (!GetWindowRect(target, &window) || !GetClientRect(target, &client)) return;
    POINT clientOrigin{client.left, client.top};
    if (!ClientToScreen(target, &clientOrigin)) return;
    const int leftInset = clientOrigin.x - window.left;
    const int topInset = clientOrigin.y - window.top;
    const int rightInset = window.right - clientOrigin.x - (client.right - client.left);
    const int bottomInset = window.bottom - clientOrigin.y - (client.bottom - client.top);
    const RECT desired{monitor.left - leftInset, monitor.top - topInset,
        monitor.right + rightInset, monitor.bottom + bottomInset};
    if (EqualRect(&window, &desired)) return;
    POINT origin{desired.left, desired.top};
    if (!ScreenToClient(desktop.layer, &origin)) return;
    SetWindowPos(target, insertAfter, origin.x, origin.y,
        desired.right - desired.left, desired.bottom - desired.top, SWP_NOACTIVATE);
}

static bool discoverDesktop(HWND& progman, DesktopWindows& desktop) {
    progman = FindWindowW(L"Progman", nullptr);
    if (!progman) return false;
    DWORD_PTR ignored = 0;
    SendMessageTimeoutW(progman, 0x052c, 0x0d, 0x01, SMTO_ABORTIFHUNG, 1000, &ignored);
    desktop = {};
    EnumWindows(findDesktop, reinterpret_cast<LPARAM>(&desktop));
    if (!desktop.layer) desktop.layer = FindWindowExW(progman, nullptr, L"WorkerW", nullptr);
    return desktop.layer != nullptr && desktop.icons != nullptr;
}

static HWND resolveInsertAfter(const DesktopWindows& desktop, HWND target, HWND& behind) {
    if (behind && (behind == target || !IsWindow(behind) || GetParent(behind) != desktop.layer)) {
        behind = nullptr;
    }
    return behind ? behind : (desktop.raised ? desktop.view : HWND_BOTTOM);
}

static int attachToDesktop(HWND target, HWND& progman, DesktopWindows& desktop, HWND& behind, const RECT& monitor, LONG_PTR baseExStyle) {
    if (desktop.raised) {
        SetWindowLongPtrW(target, GWL_EXSTYLE, baseExStyle | WS_EX_LAYERED);
        if (!SetLayeredWindowAttributes(target, 0, 255, LWA_ALPHA)) return 9;
    } else {
        SetWindowLongPtrW(target, GWL_EXSTYLE, baseExStyle);
    }
    SetLastError(0);
    if (!SetParent(target, desktop.layer) && GetLastError()) return 6;
    POINT origin{monitor.left, monitor.top};
    ScreenToClient(desktop.layer, &origin);
    const HWND insertAfter = resolveInsertAfter(desktop, target, behind);
    if (!SetWindowPos(target, insertAfter, origin.x, origin.y,
        monitor.right - monitor.left, monitor.bottom - monitor.top,
        SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW)) return 8;
    // Correct any non-client border insets immediately so no gap flashes on startup.
    fitClientToMonitor(target, desktop, insertAfter, monitor);
    return 0;
}

// LVM_HITTEST uses the receiving process's address space. If Explorer cannot
// be queried, treat the point as occupied instead of stealing desktop input.
static bool isBackground(HWND icons, POINT point) {
    if (!icons || !IsWindowVisible(icons)) return false;
    // Do not forward clicks through another window, taskbar, or shell menu.
    const HWND hit = WindowFromPoint(point);
    if (hit != icons && !IsChild(icons, hit)) return false;
    RECT bounds{};
    if (!GetWindowRect(icons, &bounds) || !PtInRect(&bounds, point)) return false;
    DWORD pid = 0; GetWindowThreadProcessId(icons, &pid);
    HANDLE process = OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE, FALSE, pid);
    if (!process) return false;
    void* remote = VirtualAllocEx(process, nullptr, sizeof(LVHITTESTINFO), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remote) { CloseHandle(process); return false; }
    ScreenToClient(icons, &point);
    LVHITTESTINFO info{}; info.pt = point;
    DWORD_PTR result = 0;
    const bool written = WriteProcessMemory(process, remote, &info, sizeof(info), nullptr) != FALSE;
    const bool sent = written && SendMessageTimeoutW(icons, LVM_HITTEST, 0, reinterpret_cast<LPARAM>(remote),
        SMTO_ABORTIFHUNG | SMTO_BLOCK, 100, &result) != 0;
    const bool ok = sent && ReadProcessMemory(process, remote, &info, sizeof(info), nullptr) != FALSE;
    // A timed-out cross-process message may still be reading its argument.
    // A tiny allocation in Explorer is safer than freeing memory it may use.
    if (!written || sent) VirtualFreeEx(process, remote, 0, MEM_RELEASE);
    CloseHandle(process);
    return ok && info.iItem == -1;
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 3 || argc > 4) return 2;
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    const HWND target = reinterpret_cast<HWND>(static_cast<uintptr_t>(_wcstoui64(argv[1], nullptr, 10)));
    const DWORD ownerPid = wcstoul(argv[2], nullptr, 10);
    HWND behind = argc == 4 ? reinterpret_cast<HWND>(static_cast<uintptr_t>(_wcstoui64(argv[3], nullptr, 10))) : nullptr;
    DWORD actualPid = 0; GetWindowThreadProcessId(target, &actualPid);
    if (!IsWindow(target) || !ownerPid || actualPid != ownerPid) return 3;
    HWND progman = nullptr;
    DesktopWindows desktop;
    if (!discoverDesktop(progman, desktop)) return progman ? 5 : 4;
    HMONITOR monitor = MonitorFromWindow(target, MONITOR_DEFAULTTOPRIMARY);
    MONITORINFO monitorInfo{}; monitorInfo.cbSize = sizeof(monitorInfo);
    if (!GetMonitorInfoW(monitor, &monitorInfo)) return 7;
    POINT monitorAnchor{
        (monitorInfo.rcMonitor.left + monitorInfo.rcMonitor.right) / 2,
        (monitorInfo.rcMonitor.top + monitorInfo.rcMonitor.bottom) / 2,
    };
    const LONG_PTR oldStyle = GetWindowLongPtrW(target, GWL_STYLE);
    const LONG_PTR baseExStyle = GetWindowLongPtrW(target, GWL_EXSTYLE);
    // Electron's frameless top-level window can still carry a resize frame.
    // Once reparented, Windows reserves that non-client border inside the
    // monitor-sized window, leaving gaps around the rendered wallpaper.
    SetWindowLongPtrW(target, GWL_STYLE,
        (oldStyle & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_BORDER | WS_DLGFRAME)) | WS_CHILD);
    const int attachResult = attachToDesktop(target, progman, desktop, behind, monitorInfo.rcMonitor, baseExStyle);
    if (attachResult != 0) {
        if (attachResult == 6) SetWindowLongPtrW(target, GWL_STYLE, oldStyle);
        return attachResult;
    }
    printf("ready\n"); fflush(stdout);
    bool pressed = false, forwarding = false;
    bool lastForeground = false, lastDown = false, lastForwarding = false, sentState = false;
    POINT lastCursor{};
    unsigned int ticks = 0;
    while (IsWindow(target)) {
        if (!IsWindow(desktop.layer) || !IsWindow(desktop.icons)) {
            bool reattached = false;
            for (int attempt = 0; attempt < 20 && IsWindow(target); ++attempt) {
                Sleep(250);
                if (discoverDesktop(progman, desktop) &&
                    attachToDesktop(target, progman, desktop, behind, monitorInfo.rcMonitor, baseExStyle) == 0) {
                    reattached = true;
                    break;
                }
            }
            if (!reattached) break;
            ticks = 0;
        }
        ++ticks;
        if (ticks <= 120 ? (ticks % 2 == 0) : (ticks % 60 == 0)) {
            // Resolution, DPI, or monitor layout may change while running, and
            // Electron's showInactive() can briefly re-apply non-client insets.
            monitor = MonitorFromPoint(monitorAnchor, MONITOR_DEFAULTTOPRIMARY);
            MONITORINFO updated{}; updated.cbSize = sizeof(updated);
            const HWND insertAfter = resolveInsertAfter(desktop, target, behind);
            if (GetMonitorInfoW(monitor, &updated) &&
                !EqualRect(&updated.rcMonitor, &monitorInfo.rcMonitor)) {
                monitorInfo = updated;
                monitorAnchor = {
                    (updated.rcMonitor.left + updated.rcMonitor.right) / 2,
                    (updated.rcMonitor.top + updated.rcMonitor.bottom) / 2,
                };
                POINT nextOrigin{updated.rcMonitor.left, updated.rcMonitor.top};
                ScreenToClient(desktop.layer, &nextOrigin);
                SetWindowPos(target, insertAfter, nextOrigin.x, nextOrigin.y,
                    updated.rcMonitor.right - updated.rcMonitor.left,
                    updated.rcMonitor.bottom - updated.rcMonitor.top,
                    SWP_NOACTIVATE);
            }
            fitClientToMonitor(target, desktop, insertAfter, monitorInfo.rcMonitor);
        }
        const bool foreground = desktopForeground(GetForegroundWindow(), progman, desktop);
        POINT cursor{};
        // Do not collect cursor or button state while another application is
        // active; the controller only needs the change of foreground state.
        if (foreground) GetCursorPos(&cursor);
        const bool down = foreground && (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0;
        const bool background = foreground && down && !pressed && isBackground(desktop.icons, cursor);
        // Dragging can continue across a desktop icon only if it began on the background.
        if (!foreground) forwarding = false;
        if (down && !pressed) forwarding = background;
        if (!sentState || foreground != lastForeground || down != lastDown || forwarding != lastForwarding ||
            (forwarding && (cursor.x != lastCursor.x || cursor.y != lastCursor.y))) {
            printf("state %d %ld %ld %d %d\n", foreground ? 1 : 0, cursor.x, cursor.y,
                down ? 1 : 0, forwarding ? 1 : 0);
            fflush(stdout);
            sentState = true; lastForeground = foreground; lastDown = down;
            lastForwarding = forwarding; lastCursor = cursor;
        }
        pressed = down;
        if (!down) forwarding = false;
        Sleep(foreground ? 16 : 60);
    }
    return 0;
}
