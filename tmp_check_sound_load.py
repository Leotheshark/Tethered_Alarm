import os
from game_client.sound_manager import SoundManager
root = os.path.abspath('game_client')
print('root', root)
print('exists', os.path.exists(os.path.join(root, 'assets', 'sounds', 'Alarm_1.ogg')))
sm = SoundManager()
print('sound_dir', sm.sound_dir)
loaded = sm.load_sound('alarm', 'Alarm_1.ogg') is not None
print('loaded', loaded)
