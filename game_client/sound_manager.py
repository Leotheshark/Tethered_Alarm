"""
SoundManager
封裝遊戲音效載入、頻道分配、音量控制與淡入效果。

按照 context 規則，音效資源應該從遊戲邏輯中解耦出來，並提供明確的播放介面。
"""

import os
import pygame


class SoundManager:
    """管理音效資源與專屬播放頻道的工具類。"""

    DEFAULT_CHANNEL_MAP = {
        "alarm": 0,
        "bgm": 1,
        "sfx": 2,
        "voice": 3,
    }

    def __init__(self, sound_dir=None, master_volume=0.5):
        """初始化 mixer、頻道與預設音量。

        sound_dir: 指向音效資源目錄的路徑。
        master_volume: 全域音量控制，範圍 0.0 ~ 1.0。
        """
        pygame.mixer.init()
        self.sound_dir = sound_dir or os.path.join(os.path.dirname(__file__), "assets", "sounds")
        self.sounds = {}
        self.channel_map = dict(self.DEFAULT_CHANNEL_MAP)
        self.channels = {}
        self.master_volume = 0.0

        # 確保 Pygame mixer 有足夠的頻道數量
        pygame.mixer.set_num_channels(max(self.channel_map.values()) + 1)
        for name, index in self.channel_map.items():
            channel = pygame.mixer.Channel(index)
            channel.set_volume(master_volume)
            self.channels[name] = channel

        self.set_master_volume(master_volume)

    def load_sound(self, key, filename, volume=0.5):
        """載入一個音效檔案，並以鍵值保存，供遊戲邏輯呼叫。"""
        file_path = os.path.join(self.sound_dir, filename)
        if not os.path.isfile(file_path):
            print(f"[SoundManager] 無法找到音效檔案：{file_path}")
            return None

        sound = pygame.mixer.Sound(file_path)
        sound.set_volume(max(0.0, min(1.0, volume)))
        self.sounds[key] = sound
        return sound

    def get_sound(self, key):
        """取得已載入音效物件。"""
        return self.sounds.get(key)

    def get_channel(self, channel_name):
        """取得指定名稱的播放頻道。"""
        return self.channels.get(channel_name)

    def play(self, key, loops=0, fade_ms=0, channel_name="sfx"):
        """在指定頻道播放已載入音效，支援循環與淡入效果。"""
        sound = self.get_sound(key)
        if sound is None:
            print(f"[SoundManager] 音效未載入：{key}")
            return

        channel = self.get_channel(channel_name)
        if channel is None:
            print(f"[SoundManager] 找不到頻道：{channel_name}")
            return

        channel.play(sound, loops=loops, fade_ms=fade_ms)

    def fade_in(self, key, duration_ms=1000, loops=-1, channel_name="alarm"):
        """以漸入方式播放音效，適合鬧鐘響起或背景音樂。"""
        self.play(key, loops=loops, fade_ms=duration_ms, channel_name=channel_name)

    def stop(self, channel_name="alarm", fade_ms=0):
        """停止指定頻道的播放，支援淡出。"""
        channel = self.get_channel(channel_name)
        if channel is None:
            return
        if fade_ms > 0:
            channel.fadeout(fade_ms)
        else:
            channel.stop()

    def set_channel_volume(self, channel_name, volume):
        """設定單一頻道的音量。"""
        channel = self.get_channel(channel_name)
        if channel is None:
            return
        channel.set_volume(max(0.0, min(1.0, volume)))

    def set_master_volume(self, volume):
        """設定整個音效系統的主音量，並同步所有頻道。"""
        self.master_volume = max(0.0, min(1.0, volume))
        for channel in self.channels.values():
            channel.set_volume(self.master_volume)

    def play_alarm(self, fade_ms=2000):
        """播放鬧鐘音效，使用專屬 alarm 頻道並採用漸入效果。"""
        self.fade_in("alarm", duration_ms=fade_ms, loops=-1, channel_name="alarm")

    def add_channel(self, channel_name, channel_index):
        """動態新增專屬頻道，用於未來擴充更多音效類別。"""
        if channel_name in self.channels:
            return

        max_channel = max(self.channel_map.values())
        if channel_index > max_channel:
            pygame.mixer.set_num_channels(channel_index + 1)

        self.channel_map[channel_name] = channel_index
        channel = pygame.mixer.Channel(channel_index)
        channel.set_volume(self.master_volume)
        self.channels[channel_name] = channel
