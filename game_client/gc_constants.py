from enum import Enum

class GameState(Enum):
    SETUP   = "setup"
    WAITING = "waiting"
    ALARM   = "alarm"
    GAME    = "game"
    RESULT  = "result"

COLORS = {
    "blue":  (84, 160, 255),  # 來自 #54a0ff
    "green": (95, 207, 128),  # 來自 #5fcf80
    "pink":  (255, 128, 191), # 來自 #ff80bf
    "red":   (255, 77, 77),   # 來自 #ff4d4d
}