#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <delayimp.h>
#include <cstring>
// node.lib names node.exe; Electron may have been renamed for distribution.
// Resolve Node-API from the current host instead of loading another executable.
static FARPROC WINAPI currentHost(unsigned event, PDelayLoadInfo info) {
    if (event == dliNotePreLoadLibrary && _stricmp(info->szDll, "node.exe") == 0)
        return reinterpret_cast<FARPROC>(GetModuleHandleW(nullptr));
    return nullptr;
}
extern "C" const PfnDliHook __pfnDliNotifyHook2 = currentHost;
#endif
