# --- 輸入處理模組 ---
import pygame
import sys
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

class InputHandler:
    def handle_events(self):
        """監聽系統事件 (如關閉視窗)"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

    def get_movement_input(self):
        """偵測 WASD 按鍵並回傳移動向量 (dx, dy)"""
        dx, dy = 0, 0
        
        # 直接偵測物理按鍵，不受輸入法影響
        if is_key_pressed(VK_W): dy -= 1
        if is_key_pressed(VK_S): dy += 1
        if is_key_pressed(VK_A): dx -= 1
        if is_key_pressed(VK_D): dx += 1
        
        return dx, dy
