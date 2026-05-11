import platform
import logging

logger = logging.getLogger(__name__)

def prevent_sleep():
    """防止系統進入休眠"""
    system = platform.system()
    
    if system == "Windows":
        try:
            import ctypes
            ES_CONTINUOUS       = 0x80000000
            ES_SYSTEM_REQUIRED  = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            )
            logger.info("Windows 防休眠：已啟用")
        except Exception as e:
            logger.warning(f"防休眠失敗：{e}")
    else:
        logger.warning(f"{system} 不支援硬體喚醒，略過防休眠設定")

def allow_sleep():
    """恢復正常休眠（程式結束時呼叫）"""
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except:
            pass

if __name__ == "__main__":
    prevent_sleep()
    print("✅ 防休眠啟用，等待 5 秒...")
    import time
    time.sleep(5)
    allow_sleep()
    print("✅ 已恢復正常休眠設定")