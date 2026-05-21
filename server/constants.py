"""
Server-side constants for Socket.IO event names.
集中管理伺服器端 Socket.IO 事件名稱，避免硬編碼字串，提高可讀性與可維護性。
"""

class ServerEvent:
    # Lobby & Room Management
    ROOM_STATE = "room_state"
    JOIN_FAILED = "join_failed"
    ALL_READY = "all_ready"
    ASSIGN_ROOM = "assign_room"
    ERROR_MSG = "error_msg"

    # Alarm Flow
    ALARM_SET = "alarm_set"
    ALARM_TRIGGERED = "alarm_triggered"

    # System & Hardware Feedback
    HARDWARE_STATUS = "hardware_status"
    TEST_ALARM_STATUS = "test_alarm_status"

    # Game Start
    GAME_STARTED = "game_started"

    # Game Client Subscription
    GAME_ROOM_SUBSCRIBED = "game_room_subscribed"