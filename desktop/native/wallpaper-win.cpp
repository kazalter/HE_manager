// Explorer wallpaper host. Runs in its own process; the Electron window belongs
// to HE Manager. Stdout is a small line protocol, never arbitrary shell input.
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <commctrl.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

struct DesktopWindows { HWND icons = nullptr; HWND layer = nullptr; };

static BOOL CALLBACK findDesktop(HWND top, LPARAM parameter) {
    auto* result = reinterpret_cast<DesktopWindows*>(parameter);
    HWND view = FindWindowExW(top, nullptr, L"SHELLDLL_DefView", nullptr);
    if (!view) return TRUE;
    result->icons = FindWindowExW(view, nullptr, L"SysListView32", nullptr);
    result->layer = FindWindowExW(nullptr, top, L"WorkerW", nullptr);
    return FALSE;
}

static bool desktopForeground(HWND foreground, HWND progman, const DesktopWindows& desktop) {
    if (!foreground) return false;
    const HWND root = GetAncestor(foreground, GA_ROOT);
    return root == progman || root == desktop.layer ||
        (desktop.icons && root == GetAncestor(desktop.icons, GA_ROOT));
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
    if (argc != 3) return 2;
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    const HWND target = reinterpret_cast<HWND>(static_cast<uintptr_t>(_wcstoui64(argv[1], nullptr, 10)));
    const DWORD ownerPid = wcstoul(argv[2], nullptr, 10);
    DWORD actualPid = 0; GetWindowThreadProcessId(target, &actualPid);
    if (!IsWindow(target) || !ownerPid || actualPid != ownerPid) return 3;
    const HWND progman = FindWindowW(L"Progman", nullptr);
    if (!progman) return 4;
    DWORD_PTR ignored = 0;
    SendMessageTimeoutW(progman, 0x052c, 0x0d, 0x01, SMTO_ABORTIFHUNG, 1000, &ignored);
    DesktopWindows desktop; EnumWindows(findDesktop, reinterpret_cast<LPARAM>(&desktop));
    if (!desktop.layer) desktop.layer = FindWindowExW(progman, nullptr, L"WorkerW", nullptr);
    if (!desktop.layer || !desktop.icons) return 5;
    HMONITOR monitor = MonitorFromWindow(target, MONITOR_DEFAULTTOPRIMARY);
    MONITORINFO monitorInfo{}; monitorInfo.cbSize = sizeof(monitorInfo);
    if (!GetMonitorInfoW(monitor, &monitorInfo)) return 7;
    POINT origin{monitorInfo.rcMonitor.left, monitorInfo.rcMonitor.top};
    ScreenToClient(desktop.layer, &origin);
    const LONG_PTR oldStyle = GetWindowLongPtrW(target, GWL_STYLE);
    SetWindowLongPtrW(target, GWL_STYLE, (oldStyle & ~WS_POPUP) | WS_CHILD);
    SetLastError(0);
    if (!SetParent(target, desktop.layer) && GetLastError()) {
        SetWindowLongPtrW(target, GWL_STYLE, oldStyle); return 6;
    }
    if (!SetWindowPos(target, HWND_BOTTOM, origin.x, origin.y,
        monitorInfo.rcMonitor.right - monitorInfo.rcMonitor.left,
        monitorInfo.rcMonitor.bottom - monitorInfo.rcMonitor.top,
        SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW)) return 8;
    printf("ready\n"); fflush(stdout);
    bool pressed = false;
    bool lastForeground = false, lastDown = false, lastForwarding = false, sentState = false;
    POINT lastCursor{};
    unsigned int ticks = 0;
    while (IsWindow(target) && IsWindow(desktop.layer) && IsWindow(desktop.icons)) {
        if (++ticks % 60 == 0) {
            // Resolution, DPI, or primary monitor may change while running.
            POINT primaryPoint{0, 0};
            monitor = MonitorFromPoint(primaryPoint, MONITOR_DEFAULTTOPRIMARY);
            MONITORINFO updated{}; updated.cbSize = sizeof(updated);
            if (GetMonitorInfoW(monitor, &updated) &&
                !EqualRect(&updated.rcMonitor, &monitorInfo.rcMonitor)) {
                monitorInfo = updated;
                POINT nextOrigin{updated.rcMonitor.left, updated.rcMonitor.top};
                ScreenToClient(desktop.layer, &nextOrigin);
                SetWindowPos(target, HWND_BOTTOM, nextOrigin.x, nextOrigin.y,
                    updated.rcMonitor.right - updated.rcMonitor.left,
                    updated.rcMonitor.bottom - updated.rcMonitor.top,
                    SWP_NOACTIVATE);
            }
        }
        const bool foreground = desktopForeground(GetForegroundWindow(), progman, desktop);
        POINT cursor{};
        // Do not collect cursor or button state while another application is
        // active; the controller only needs the change of foreground state.
        if (foreground) GetCursorPos(&cursor);
        const bool down = foreground && (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0;
        const bool background = foreground && down && !pressed && isBackground(desktop.icons, cursor);
        // Dragging can continue across a desktop icon only if it began on the background.
        static bool forwarding = false;
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
        Sleep(16);
    }
    return 0;
}
