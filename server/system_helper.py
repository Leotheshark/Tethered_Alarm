import ctypes
import sys
import webview
from pycaw.pycaw import AudioUtilities

# Windows API 常數
if sys.platform == "win32":
    # 載入必要的 DLLs
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    # 定義函數的參數類型和回傳類型，以確保 ctypes 正確呼叫
    # SetThreadExecutionState
    kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint]
    kernel32.SetThreadExecutionState.restype = ctypes.c_uint

    # SetWindowPos
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = ctypes.c_bool

    # SetForegroundWindow
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_bool

    # SetThreadExecutionState 旗標
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    # SetWindowPos 旗標 (HWND_TOPMOST 是一個特殊的 HWND 值)
    HWND_TOPMOST = -1
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040

class SystemHelper:
    """
    提供系統層級的輔助功能，例如防止系統睡眠、將視窗置頂等。
    """

    @staticmethod
    def get_is_speaker() -> bool:
        """偵測當前預設輸出裝置是否為喇叭"""
        if sys.platform == "win32":
            try:
                # 在背景執行緒中使用 pycaw (COM) 前必須先初始化
                ctypes.windll.ole32.CoInitialize(None)
            except:
                pass

        if sys.platform == "win32":
            try:
                devices = AudioUtilities.GetSpeakers()
                if not devices:
                    return True

                # 修正：pycaw 的 AudioDevice 物件名稱儲存在 .friendly_name 屬性中
                if hasattr(devices, 'friendly_name'):
                    friendly_name = devices.friendly_name
                else:
                    friendly_name = str(devices)

                friendly_name = friendly_name.lower()
                # 判斷是否為耳機的關鍵字
                headset_keywords = ["headphone", "headset", "耳機", "耳麥"]
                return not any(k in friendly_name for k in headset_keywords)
            except Exception as e:
                print(f"[SystemHelper] Device detection failed: {e}")
        return True

    @staticmethod
    def prevent_sleep():
        """防止系統進入睡眠狀態。"""
        if sys.platform == "win32":
            kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
            print("[SystemHelper] Prevented system sleep.")

    @staticmethod
    def restore_sleep():
        """恢復系統的正常睡眠行為。"""
        if sys.platform == "win32":
            kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            print("[SystemHelper] Restored system sleep behavior.")

    @staticmethod
    def set_webview_topmost():
        """將 pywebview 視窗設定為最上層視窗並帶到前景。"""
        if sys.platform == "win32" and webview.windows:
            try:
                # 在 WinForms 平台下，window.native 是 Form 物件，其 Handle 屬性即為 HWND
                window = webview.windows[0]
                # IntPtr 需要先轉為 64 位元整數才能由 ctypes 使用
                hwnd = int(window.native.Handle.ToInt64())
                
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                user32.SetForegroundWindow(hwnd) # 確保視窗被帶到前景
                print("[SystemHelper] Webview window set to topmost and brought to foreground.")
            except Exception as e:
                print(f"[SystemHelper] Failed to set topmost: {e}")
        elif not webview.windows:
            print("[SystemHelper] No webview window found to set topmost.")
