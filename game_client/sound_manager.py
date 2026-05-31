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
        # 僅在尚未初始化時才呼叫 init()，避免覆蓋 engine.py 中的 pre_init 設定
        if not pygame.mixer.get_init():
            pygame.mixer.init()
            
        self.sound_dir = sound_dir or os.path.join(os.path.dirname(__file__), "assets", "sounds")
        self.sounds = {}
        self.sound_volumes = {}  # 紀錄每個音效的原始音量設定
        self.channel_map = dict(self.DEFAULT_CHANNEL_MAP)
        self.channels = {}
        self.music_base_volume = 1.0
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
        self.sound_volumes[key] = volume
        sound.set_volume(volume * self.master_volume)
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
            
        # 針對一般 SFX (非 alarm/bgm)，不指定頻道，讓 Pygame 自動找空位播放
        # 這樣多個音效（如 blind 與按鈕聲）就能重疊播放而不會互相掐斷
        if channel_name == "sfx":
            sound.play(loops=loops, fade_ms=fade_ms)
        else:
            channel = self.get_channel(channel_name)
            if channel: channel.play(sound, loops=loops, fade_ms=fade_ms)

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

    def set_master_volume(self, volume, muffled=False):
        """設定整個音效系統的主音量，並同步所有頻道、獨立音效物件與音樂。
        muffled: 是否處於致盲狀態（除 blind 音效外其餘音量 * 0.5）。"""
        self.master_volume = max(0.0, min(1.0, volume))
        muffle_factor = 0.3 if muffled else 1.0

        # 頻道統一設為 1.0，將音量主控權完全交給 Sound 物件與 Music，
        # 避免 Sound 與 Channel 同時乘以 muffle_factor 導致音量過低（或致盲音效被誤殺）。
        for channel in self.channels.values():
            channel.set_volume(1.0)
        
        # 更新所有已載入音效物件的音量 (解決 sfx 頻道播放時無視 master_volume 的問題)
        for key, sound in self.sounds.items():
            orig_vol = self.sound_volumes.get(key, 1.0)
            # 致盲期間，除了 "blind" 本身音效，其餘音效強度乘以 muffle_factor
            current_factor = 1.0 if (muffled and key == "blind") else muffle_factor
            sound.set_volume(orig_vol * self.master_volume * current_factor)
            
        pygame.mixer.music.set_volume(self.music_base_volume * self.master_volume * muffle_factor)

    def play_music(self, filename, volume=1.0, loops=-1):
        """使用 music 頻道播放背景音樂（串流模式）。"""
        self.music_base_volume = volume
        path = os.path.join(self.sound_dir, filename)
        if os.path.exists(path):
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.music_base_volume * self.master_volume)
            pygame.mixer.music.play(loops)

    def stop_music(self):
        """停止背景音樂。"""
        pygame.mixer.music.stop()

    def fadeout_music(self, ms):
        """淡出背景音樂。"""
        pygame.mixer.music.fadeout(ms)

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
