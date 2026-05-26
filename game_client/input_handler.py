# --- 輸入處理模組 ---
import pygame
import sys
import os
import ctypes

# Windows 虛擬鍵碼 (Virtual-Key Codes)
VK_W = 0x57
VK_A = 0x41
VK_S = 0x53
VK_D = 0x44

def is_key_pressed(vk_code):
    """
    使用 Win32 API 檢查按鍵是否被按下。
    GetAsyncKeyState 會檢查物理按鍵狀態，無視輸入法(IME)攔截。
    回傳值的最高位元 (0x8000) 代表按鍵目前正被按下。
    """
    return ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000

# DEBUG 多視窗模式：GetAsyncKeyState 是全域狀態，4 個 client 同時讀會一起動。
# 只在自己的視窗為最上層時才接受輸入。
_REQUIRE_FOREGROUND = os.environ.get('DEBUG_WINDOWED') == '1'


def _is_my_window_foreground():
    """檢查目前 pygame 視窗是否為作業系統的最上層視窗 (Windows only)。"""
    try:
        hwnd = pygame.display.get_wm_info().get('window')
        if not hwnd:
            return True  # 視窗還沒建立，先當作 true
        return ctypes.windll.user32.GetForegroundWindow() == hwnd
    except Exception:
        return True


class InputHandler:
    def handle_events(self):
        """監聽系統事件 (如關閉視窗)"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

    def get_movement_input(self):
        """偵測 WASD 按鍵並回傳移動向量 (dx, dy)"""
        # DEBUG 多視窗模式：焦點不在自己視窗時不接受輸入
        if _REQUIRE_FOREGROUND and not _is_my_window_foreground():
            return 0, 0

        dx, dy = 0, 0

        # 直接偵測物理按鍵，不受輸入法影響
        if is_key_pressed(VK_W): dy -= 1
        if is_key_pressed(VK_S): dy += 1
        if is_key_pressed(VK_A): dx -= 1
        if is_key_pressed(VK_D): dx += 1

        return dx, dy
