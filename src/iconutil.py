# -*- coding: utf-8 -*-
"""
Windows 程序图标提取器（纯 ctypes，无第三方依赖）
================================================
优先用 Shell 的图像列表（SHGetImageList + SHIL_JUMBO），拿到与资源管理器
完全一致的高清图标（最大 256x256）；失败时退回 PrivateExtractIconsW；
再失败退回 SHGetFileInfoW。

拿到 HICON 后通过 GetIconInfo + GetDIBits 转成 RGBA 像素，交给 pngutil 编码。
"""
import ctypes
import ctypes.wintypes as wt
import os

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32

# ---------------------------------------------------------------- 结构体
class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wt.BOOL),
        ("xHotspot", wt.DWORD),
        ("yHotspot", wt.DWORD),
        ("hbmMask", wt.HBITMAP),
        ("hbmColor", wt.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", ctypes.c_long),
        ("bmWidth", ctypes.c_long),
        ("bmHeight", ctypes.c_long),
        ("bmWidthBytes", ctypes.c_long),
        ("bmPlanes", ctypes.c_ushort),
        ("bmBitsPixel", ctypes.c_ushort),
        ("bmBits", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wt.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wt.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# IID_IImageList {46EB5926-582E-4017-9FDF-E8998DAA0950}
_IID_IImageList = GUID(0x46EB5926, 0x582E, 0x4017,
                       (ctypes.c_ubyte * 8)(0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))

# ---------------------------------------------------------------- API 签名
# 必须显式声明参数类型：64 位下句柄是 8 字节指针，不声明会被当成 C int，
# 指针值一超过 2^31 就抛 "OverflowError: int too long to convert"。
user32.GetIconInfo.argtypes = [wt.HICON, ctypes.POINTER(ICONINFO)]
user32.GetIconInfo.restype = wt.BOOL
user32.DestroyIcon.argtypes = [wt.HICON]
user32.DestroyIcon.restype = wt.BOOL
user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.PrivateExtractIconsW.argtypes = [
    ctypes.c_wchar_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(wt.HICON), ctypes.POINTER(wt.UINT), wt.UINT, wt.UINT]
user32.PrivateExtractIconsW.restype = wt.UINT

gdi32.GetObjectW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT,
                            ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wt.UINT]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wt.HANDLE]
gdi32.DeleteObject.restype = wt.BOOL

shell32.SHGetFileInfoW.argtypes = [ctypes.c_wchar_p, wt.DWORD,
                                   ctypes.POINTER(SHFILEINFOW), wt.UINT, wt.UINT]
shell32.SHGetFileInfoW.restype = ctypes.c_size_t
shell32.SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(GUID),
                                   ctypes.POINTER(ctypes.c_void_p)]
shell32.SHGetImageList.restype = ctypes.c_long

# ---- 设置窗口图标用（任务栏 / Alt+Tab / 标题栏）----
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_SHARED = 0x00008000
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
GCLP_HICON = -14
GCLP_HICONSM = -34

user32.LoadImageW.argtypes = [wt.HINSTANCE, ctypes.c_wchar_p, wt.UINT,
                             ctypes.c_int, ctypes.c_int, wt.UINT]
user32.LoadImageW.restype = wt.HANDLE
user32.SetClassLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetClassLongPtrW.restype = ctypes.c_ssize_t
user32.SetClassLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
user32.SetClassLongW.restype = ctypes.c_long
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.SendMessageW.restype = ctypes.c_ssize_t


SHIL_LARGE, SHIL_SMALL, SHIL_EXTRALARGE, SHIL_SYSSMALL, SHIL_JUMBO = 0, 1, 2, 3, 4
SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
SHGFI_SMALLICON = 0x000000001
SHGFI_SYSICONINDEX = 0x000004000
SHGFI_USEFILEATTRIBUTES = 0x000000010
ILD_TRANSPARENT = 0x00000001


# ---------------------------------------------------------------- HICON -> RGBA
def _hicon_to_rgba(hicon):
    """把 HICON 转成 (w, h, bytes) 的 RGBA 数据；失败返回 None。"""
    ii = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(ii)):
        return None
    hbm_color, hbm_mask = ii.hbmColor, ii.hbmMask
    try:
        bm = BITMAP()
        if hbm_color:
            gdi32.GetObjectW(hbm_color, ctypes.sizeof(BITMAP), ctypes.byref(bm))
        else:
            # 单色图标没有彩色位图，用 mask 的尺寸（高度是显示高度的两倍）
            gdi32.GetObjectW(hbm_mask, ctypes.sizeof(BITMAP), ctypes.byref(bm))
            bm.bmHeight = bm.bmHeight // 2
        w, h = int(bm.bmWidth), int(bm.bmHeight)
        if w <= 0 or h <= 0:
            return None

        hdc = user32.GetDC(None)
        memdc = gdi32.CreateCompatibleDC(hdc)
        try:
            bi = BITMAPINFO()
            bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bi.bmiHeader.biWidth = w
            bi.bmiHeader.biHeight = -h          # 负数 = 自上而下
            bi.bmiHeader.biPlanes = 1
            bi.bmiHeader.biBitCount = 32
            bi.bmiHeader.biCompression = 0      # BI_RGB
            buf = ctypes.create_string_buffer(w * h * 4)
            if hbm_color:
                gdi32.GetDIBits(memdc, hbm_color, 0, h, buf, ctypes.byref(bi), 0)
            data = bytearray(buf.raw)

            mask_bits = None
            if hbm_mask:
                bi2 = BITMAPINFO()
                bi2.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bi2.bmiHeader.biWidth = w
                bi2.bmiHeader.biHeight = -h
                bi2.bmiHeader.biPlanes = 1
                bi2.bmiHeader.biBitCount = 32
                bi2.bmiHeader.biCompression = 0
                mbuf = ctypes.create_string_buffer(w * h * 4)
                gdi32.GetDIBits(memdc, hbm_mask, 0, h, mbuf, ctypes.byref(bi2), 0)
                mask_bits = mbuf.raw
        finally:
            gdi32.DeleteDC(memdc)
            user32.ReleaseDC(None, hdc)

        has_alpha = any(data[i] for i in range(3, len(data), 4))
        rgba = bytearray(w * h * 4)
        if has_alpha:
            for i in range(0, len(data), 4):
                b, g, r, a = data[i], data[i + 1], data[i + 2], data[i + 3]
                rgba[i] = r
                rgba[i + 1] = g
                rgba[i + 2] = b
                rgba[i + 3] = a
        else:
            # 没有 alpha 通道：用 mask 反推透明度（mask 为白=透明）
            for p in range(w * h):
                i = p * 4
                b, g, r = data[i], data[i + 1], data[i + 2]
                a = 255
                if mask_bits is not None:
                    mi = p * 4
                    if mi + 1 < len(mask_bits):
                        a = 0 if mask_bits[mi] > 127 else 255
                rgba[i] = r
                rgba[i + 1] = g
                rgba[i + 2] = b
                rgba[i + 3] = a
        return w, h, bytes(rgba)
    finally:
        if hbm_color:
            gdi32.DeleteObject(hbm_color)
        if hbm_mask:
            gdi32.DeleteObject(hbm_mask)


# ---------------------------------------------------------------- 三种取图标方式
def _icon_from_image_list(path, shil=SHIL_JUMBO):
    """走 Shell 系统图像列表，拿到资源管理器同款高清图标。"""
    info = SHFILEINFOW()
    flags = SHGFI_SYSICONINDEX | SHGFI_LARGEICON
    res = shell32.SHGetFileInfoW(ctypes.c_wchar_p(path), 0, ctypes.byref(info),
                                 ctypes.sizeof(info), flags)
    if not res:
        return None
    piml = ctypes.c_void_p()
    hr = shell32.SHGetImageList(shil, ctypes.byref(_IID_IImageList), ctypes.byref(piml))
    if hr != 0 or not piml:
        return None
    try:
        vt = ctypes.cast(piml, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_icon = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int,
                                      wt.DWORD, ctypes.POINTER(wt.HICON))(vt[10])
        hicon = wt.HICON()
        if get_icon(piml, info.iIcon, ILD_TRANSPARENT, ctypes.byref(hicon)) != 0:
            return None
        if not hicon:
            return None
        try:
            return _hicon_to_rgba(hicon)
        finally:
            user32.DestroyIcon(hicon)
    finally:
        vt = ctypes.cast(piml, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])
        release(piml)


def _icon_private_extract(path, size):
    """PrivateExtractIconsW：直接从 exe 资源里按指定尺寸抠图标。"""
    phicon = (wt.HICON * 1)()
    piconid = (wt.UINT * 1)()
    n = user32.PrivateExtractIconsW(ctypes.c_wchar_p(path), 0, size, size,
                                    ctypes.byref(phicon), ctypes.byref(piconid), 1, 0)
    if not n or not phicon[0]:
        return None
    try:
        return _hicon_to_rgba(phicon[0])
    finally:
        user32.DestroyIcon(phicon[0])


def _icon_shellinfo(path, large=True):
    info = SHFILEINFOW()
    flags = SHGFI_ICON | (SHGFI_LARGEICON if large else SHGFI_SMALLICON)
    res = shell32.SHGetFileInfoW(ctypes.c_wchar_p(path), 0, ctypes.byref(info),
                                 ctypes.sizeof(info), flags)
    if not res or not info.hIcon:
        return None
    try:
        return _hicon_to_rgba(info.hIcon)
    finally:
        user32.DestroyIcon(info.hIcon)


def extract_icon(path):
    """
    提取任意文件（exe / lnk / bat / dll / 文件夹…）的图标。
    返回 (w, h, rgba_bytes) 或 None。
    """
    if not path or not os.path.exists(path):
        return None
    for fn in (
        lambda: _icon_from_image_list(path, SHIL_JUMBO),
        lambda: _icon_from_image_list(path, SHIL_EXTRALARGE),
        lambda: _icon_private_extract(path, 256),
        lambda: _icon_private_extract(path, 128),
        lambda: _icon_private_extract(path, 48),
        lambda: _icon_shellinfo(path, True),
        lambda: _icon_private_extract(path, 32),
    ):
        try:
            got = fn()
        except Exception:
            got = None
        if got and got[0] > 0 and got[1] > 0:
            return got
    return None


def resolve_lnk_target(lnk_path):
    """
    解析 .lnk 快捷方式指向的真实目标（失败返回原路径）。
    通过 WScript.Shell 的 COM 接口，用 ctypes 调用，避免引入 pywin32。
    """
    try:
        import pythoncom  # noqa: F401  (有则用，无则走下面的兜底)
    except Exception:
        pass
    try:
        # 用 shell32 的 IShellLinkW 太重，这里用 WScript.Shell 更省事
        import subprocess
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
              "Write-Output $s.TargetPath" % lnk_path.replace("'", "''"))
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=6,
            creationflags=0x08000000,
        )
        t = (out.stdout or "").strip()
        if t and os.path.exists(t):
            return t
    except Exception:
        pass
    return lnk_path


# ================================================================ 设置窗口图标
def _load_icon_from_file(ico_path, size):
    """从 .ico 文件里按指定尺寸载入 HICON（用 LR_SHARED，由系统持有）。"""
    try:
        h = user32.LoadImageW(None, ico_path, IMAGE_ICON, size, size,
                              LR_LOADFROMFILE | LR_SHARED)
    except Exception:
        h = None
    return int(h) if h else 0


def _set_class_icon(hwnd, index, value):
    """SetClassLongPtr 的 32/64 位安全封装。"""
    try:
        if hasattr(user32, "SetClassLongPtrW"):
            return user32.SetClassLongPtrW(wt.HWND(hwnd), index,
                                           ctypes.c_ssize_t(value))
        return user32.SetClassLongW(wt.HWND(hwnd), index,
                                    ctypes.c_long(value & 0xFFFFFFFF))
    except Exception:
        return 0


def set_window_icon(hwnd, ico_path):
    """
    把指定窗口的图标设置成 ico_path（任务栏按钮、Alt+Tab、标题栏都会跟着变）。

    为什么要走 Win32 而不是 tkinter 的 iconbitmap/iconphoto：
      Tk 的 wm 图标命令作用在内部子窗口（类名 TkChild）上，而 Windows 的
      任务栏按钮由**外层** TkTopLevel 窗口决定。实测不手动设置时，
      外层窗口的类图标是 Tk 默认的黑蓝图标，只有 exe 文件本身的图标对。
      所以这里显式给外层窗口挂 ICON_BIG/ICON_SMALL + 类图标，四路齐下。
    """
    if not hwnd or not ico_path or not os.path.exists(ico_path):
        return False
    p = os.path.abspath(ico_path)

    h_big = _load_icon_from_file(p, 32)
    h_small = _load_icon_from_file(p, 16)
    if not h_small:
        h_small = h_big
    if not h_big:
        return False

    hwnd = int(hwnd)
    # 1) 窗口自身（WM_SETICON 优先于类图标，任务栏先问它）
    try:
        user32.SendMessageW(wt.HWND(hwnd), WM_SETICON, ICON_BIG, h_big)
        user32.SendMessageW(wt.HWND(hwnd), WM_SETICON, ICON_SMALL, h_small)
    except Exception:
        pass
    # 2) 类图标（Alt+Tab / 标题栏兜底，且窗口重建后依然有效）
    try:
        _set_class_icon(hwnd, GCLP_HICON, h_big)
        _set_class_icon(hwnd, GCLP_HICONSM, h_small)
    except Exception:
        pass
    return True


def set_app_window_icons(hwnds, ico_path):
    """给一批窗口逐个挂图标，返回成功数量。"""
    n = 0
    for h in hwnds or []:
        try:
            if set_window_icon(h, ico_path):
                n += 1
        except Exception:
            pass
    return n
