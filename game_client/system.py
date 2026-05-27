# --- 引入工具箱 ---
import os
import platform    # 檢查電腦系統 (Windows, Mac, Linux)
import logging     # 記錄程式執行過程中的資訊 (日誌)

# 設定日誌的基本配置
logger = logging.getLogger(__name__)

def prevent_sleep():
    """防止系統進入休眠"""
    system = platform.system()
    
    # TODO: 根據不同作業系統實作防休眠機制，目前僅支援 Windows
    if system == "Windows":
        try:
            import ctypes  # 呼叫底層 C 語言函式庫
            # 定義 Windows API 常數
            ES_CONTINUOUS       = 0x80000000  # 設定持續有效
            ES_SYSTEM_REQUIRED  = 0x00000001  # 要求系統保持運作
            # 執行 API 呼叫
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
            # 僅傳入 ES_CONTINUOUS 代表重設之前的要求
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except:
            pass

# --- 測試區域：單獨執行此檔案時會執行以下代碼 ---
if __name__ == "__main__":
    prevent_sleep()
    print("✅ 防休眠啟用，等待 5 秒...")
    import time
    time.sleep(5)
    allow_sleep()
    print("✅ 已恢復正常休眠設定")