/*
 * cefwrap: stand-in for a CEF helper executable.
 *
 * Installed as <name>.exe next to the original renamed to <name>_real.exe.
 * Re-launches the original with extra Chromium switches prepended, then
 * waits and propagates its exit code. Child processes (--type=...) are
 * passed through unchanged.
 *
 * The switches default to software rendering (works everywhere). Set the
 * environment variable CROSSBOTTLE_CEF_FLAGS to replace them, e.g. with
 * "--no-sandbox" to keep GPU rendering when DXVK is available.
 *
 * Build: x86_64-w64-mingw32-gcc -municode -O2 -s -o steamwebhelper.exe cefwrap.c
 */
#include <windows.h>
#include <wchar.h>

static const wchar_t EXTRA_FLAGS[] =
    L" --disable-gpu --disable-gpu-compositing --single-process --no-sandbox";

/* Lets crossbottle recognise any version of this wrapper. Do not remove. */
volatile const char CROSSBOTTLE_MARKER[] = "CROSSBOTTLE_CEFWRAP_V2";

/* Return pointer to the arguments after argv[0] in a raw command line. */
static const wchar_t *skip_argv0(const wchar_t *cmd)
{
    if (*cmd == L'"') {
        cmd++;
        while (*cmd && *cmd != L'"') cmd++;
        if (*cmd) cmd++;
    } else {
        while (*cmd && *cmd != L' ' && *cmd != L'\t') cmd++;
    }
    return cmd;
}

int wmain(void)
{
    wchar_t self[MAX_PATH], real[MAX_PATH + 16];
    DWORD n = GetModuleFileNameW(NULL, self, MAX_PATH);
    if (!n || n >= MAX_PATH) return 1;

    wchar_t *dot = wcsrchr(self, L'.');
    if (!dot) return 1;
    *dot = 0;
    _snwprintf(real, MAX_PATH + 16, L"%ls_real.exe", self);
    real[MAX_PATH + 15] = 0;

    const wchar_t *args = skip_argv0(GetCommandLineW());
    int is_child = wcsstr(args, L"--type=") != NULL;
    static wchar_t custom[4096];
    const wchar_t *extra = EXTRA_FLAGS;
    DWORD clen = GetEnvironmentVariableW(L"CROSSBOTTLE_CEF_FLAGS", custom + 1, 4094);
    if (clen > 0 && clen < 4094) {
        custom[0] = L' ';
        extra = custom;
    }
    if (is_child) extra = L"";

    size_t len = wcslen(real) + wcslen(extra) + wcslen(args) + 8;
    wchar_t *cmd = HeapAlloc(GetProcessHeap(), 0, len * sizeof(wchar_t));
    if (!cmd) return 1;
    _snwprintf(cmd, len, L"\"%ls\"%ls%ls", real, extra, args);
    cmd[len - 1] = 0;

    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(real, cmd, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi))
        return (int)GetLastError();

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}
