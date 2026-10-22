"""The few Windows calls Lorekeeper needs: the window in front, its exe and title, and the monitors."""
import ctypes, sys

if sys.platform == 'win32':
    from ctypes import wintypes as W
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = W.HWND
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [W.HWND]
    kernel32.OpenProcess.restype = W.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    kernel32.CloseHandle.argtypes = [W.HANDLE]


def exe_of(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION: works on most elevated games too
    if not h:
        return ''
    try:
        buf, n = ctypes.create_unicode_buffer(1024), W.DWORD(1024)
        return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ''
    finally:
        kernel32.CloseHandle(h)


def front():
    """(exe path, window title) of the window in front, ('', '') if none."""
    if sys.platform != 'win32':
        return '', ''
    h = user32.GetForegroundWindow()
    if not h:
        return '', ''
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(h) + 1)
    user32.GetWindowTextW(h, buf, len(buf))
    return exe_of(pid.value), buf.value


def monitors():
    """[(x, y, w, h, primary)] for each display."""
    out = []
    if sys.platform != 'win32':
        return out

    class MI(ctypes.Structure):
        _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('dwFlags', W.DWORD)]

    def each(hmon, _hdc, _rect, _data):
        mi = MI()
        mi.cbSize = ctypes.sizeof(MI)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = mi.rcWork
        out.append((r.left, r.top, r.right - r.left, r.bottom - r.top, bool(mi.dwFlags & 1)))
        return True
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, W.HMONITOR, W.HDC, ctypes.POINTER(W.RECT), W.LPARAM)(each)
    user32.EnumDisplayMonitors(None, None, proc, 0)
    return out


def per_monitor_dpi():
    """Make windows made by this thread from now on per-monitor DPI aware (v2): drawn at the screen's real pixels instead of
    being drawn small and stretched by Windows, which is what made the box large and soft on a scaled or upscaled screen.
    Only this thread: the hotkey, capture and tray threads keep the coordinates they have always had."""
    if sys.platform != 'win32':
        return
    try:
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))   # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    except Exception:
        pass


def scale_at(x, y, override=0):
    """Windows' scale for the monitor at (x, y) as a factor (200% -> 2.0), or `override` if that is set (> 0). 1.0 if unknown."""
    try:
        if float(override) > 0:
            return min(float(override), 8.0)
    except (TypeError, ValueError):
        pass
    if sys.platform != 'win32':
        return 1.0
    try:
        user32.MonitorFromPoint.restype, user32.MonitorFromPoint.argtypes = ctypes.c_void_p, [W.POINT, W.DWORD]
        shcore = ctypes.windll.shcore
        shcore.GetDpiForMonitor.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        mon = user32.MonitorFromPoint(W.POINT(int(x), int(y)), 2)   # MONITOR_DEFAULTTONEAREST
        dx, dy = ctypes.c_uint(), ctypes.c_uint()
        shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy))   # MDT_EFFECTIVE_DPI
        return dx.value / 96 if dx.value else 1.0
    except Exception:
        return 1.0
