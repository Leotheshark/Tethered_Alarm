import platform
import ctypes

class SystemHelper:
    """封裝所有 Win32 與系統層級的工具函數"""
    
    @staticmethod
    def prevent_sleep():
        """
        透過 Win32 API 防止系統進入睡眠模式。
        ES_CONTINUOUS (0x80000000): 使設定持續有效。
        ES_SYSTEM_REQUIRED (0x00000001): 防止系統進入睡眠。
        ES_DISPLAY_REQUIRED (0x00000002): 防止螢幕關閉。
        """
        if platform.system() == "Windows":
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
                print("[系統] Win32：防休眠模式已啟用")
            except Exception as e:
                print(f"[系統] 啟用防休眠失敗：{e}")

    @staticmethod
    def restore_sleep():
        """恢復系統預設的睡眠行為"""
        if platform.system() == "Windows":
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                print("[系統] Win32：已恢復系統預設休眠設定")
            except:
                pass
