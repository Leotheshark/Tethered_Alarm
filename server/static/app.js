// ------------------------------------------------------------------
// Lobby 大廳前端邏輯
// 這個檔案負責：
//  1. 與 server/main.py 的 Socket.IO 伺服器建立連線
//  2. 更新房間狀態畫面、玩家準備標記與房長控制
//  3. 顯示/隱藏倒數、睡眠、房間已滿與時間選擇器全局 UI
// ------------------------------------------------------------------

// --- 語系設定 (i18n) ---
const translations = {
    zh: {
        room_id_label: '房間 ID',
        invite_btn: '複製邀請連結',
        invite_success: '邀請連結已複製到剪貼簿！',
        room_prompt: '請輸入房間 ID 以建立或加入房間：',
        host_prompt: '你是房長，請輸入鬧鐘設定時間 (例如 08:30):',
        game_starting: '遊戲即將開始',
        ready: '準備！',
        set_time: '設定',
        cancel_time: '取消',
        sleeping: '睡眠中...',
        room_full_message: '此房間人數已滿',
        try_another_room: '嘗試其他房間',
        alarm_hint: '全員到齊！房長可以點擊時鐘設定鬧鐘了',
        time_until: '鬧鐘將在 $t 後響起',
        alarm_time_prefix: '訂下的起床時間：',
        speaker_warning: '⚠️ 偵測到耳機輸出，請切換至喇叭以免睡過頭！',
        you: '你',
        test_volume: '測試音量',
        playing: '播放中...'
    },
    en: {
        room_id_label: 'ROOM ID',
        invite_btn: 'Copy Invite Link',
        invite_success: 'Invite link copied to clipboard!',
        room_prompt: 'Enter Room ID to create or join:',
        host_prompt: 'You are Host, enter alarm time (e.g., 08:30):',
        game_starting: 'GAME STARTING IN',
        ready: 'READY!',
        set_time: 'Set',
        cancel_time: 'Cancel',
        sleeping: 'SLEEPING...',
        room_full_message: 'This room is full',
        try_another_room: 'Try another room',
        alarm_hint: 'All players here! Host can set the alarm.',
        time_until: 'Alarm in: $t',
        alarm_time_prefix: 'Set Alarm Time: ',
        speaker_warning: '⚠️ Headset detected! Switch to speakers to avoid oversleeping.',
        you: 'You',
        test_volume: 'Test Volume',
        playing: 'Playing...'
    }
};

// --- DOM 元素參考 ---
let currentLang = 'en';
const alarmClock = document.getElementById('alarmTimeDisplay');
const readyButton = document.querySelector('.ready-button');
const timePickerModal = document.getElementById('time-picker-modal');
const pickerHourSpan = document.getElementById('picker-hour');
const pickerMinuteSpan = document.getElementById('picker-minute');
const setTimeBtn = document.getElementById('set-time-btn');
const cancelTimeBtn = document.getElementById('cancel-time-btn');
const roomIdLabel = document.getElementById('text-room-id-label');
const inviteButton = document.getElementById('btn-invite');
const textStarting = document.getElementById('text-starting');
const textSleeping = document.getElementById('text-sleeping');
const roomFullText = document.getElementById('text-room-full');
const tryAnotherRoomButton = document.getElementById('btn-try-another-room');
const testVolButton = document.getElementById('btn-test-volume');
const urlParams = new URLSearchParams(window.location.search);
let ROOM_ID = urlParams.get('room');
let socketManager = null;
let lastIsSpeaker = true; // 紀錄最後一次收到的硬體狀態
let isTestingVolume = false; // 紀錄是否正在測試音量

function updateLanguage() {
    // 根據 currentLang 更新頁面文字，支援中文和英文
    const t = translations[currentLang];
    roomIdLabel.textContent = t.room_id_label;
    inviteButton.textContent = t.invite_btn;
    textStarting.textContent = t.game_starting;
    document.querySelectorAll('.ready-label').forEach(el => el.textContent = t.ready);
    textSleeping.textContent = t.sleeping;
    setTimeBtn.textContent = t.set_time;
    cancelTimeBtn.textContent = t.cancel_time;
    roomFullText.textContent = t.room_full_message;
    tryAnotherRoomButton.textContent = t.try_another_room;
    document.getElementById('alarm-hint').textContent = t.alarm_hint;
    if (testVolButton) testVolButton.textContent = isTestingVolume ? t.playing : t.test_volume;
    
    // 更新「你」的標籤
    document.querySelectorAll('.me-arrow span').forEach(el => el.textContent = t.you);
    
    // 更新硬體警告文字
    updateHardwareWarningUI();
}

function updateHardwareWarningUI() {
    const warning = document.getElementById('speaker-warning');
    if (warning) {
        warning.textContent = translations[currentLang].speaker_warning;
        warning.style.display = lastIsSpeaker ? 'none' : 'block';
    }
}

function toggleLanguage() {
    currentLang = currentLang === 'zh' ? 'en' : 'zh';
    updateLanguage();
}

function updateClock() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    alarmClock.textContent = `${hours}:${minutes}`;
}

// 負責與伺服器建立 Socket.IO 連線並管理事件
class SocketManager {
    constructor(serverUrl, roomId, uiCallbacks) {
        this.socket = io(serverUrl);
        this.ROOM_ID = roomId;
        this.currentHostSid = null;
        this.uiCallbacks = uiCallbacks;
        this._setupEventListeners();
    }

    _setupEventListeners() {
        this.socket.on('connect', () => {
            console.log('連線成功，身分證 ID:', this.socket.id);
            this.joinRoom(this.ROOM_ID);

            if (this.uiCallbacks.onConnect) {
                this.uiCallbacks.onConnect(this.socket.id);
            }
        });

        this.socket.on('hardware_status', data => {
            if (this.uiCallbacks.onHardwareStatus) {
                this.uiCallbacks.onHardwareStatus(data);
            }
        });

        this.socket.on('test_alarm_status', data => {
            if (this.uiCallbacks.onTestAlarmStatus) {
                this.uiCallbacks.onTestAlarmStatus(data);
            }
        });

        this.socket.on('room_state', state => {
            this.currentHostSid = state.host_sid;
            if (this.uiCallbacks.onRoomStateUpdate) {
                this.uiCallbacks.onRoomStateUpdate(state, this.socket.id);
            }
        });

        this.socket.on('all_ready', data => {
            if (this.uiCallbacks.onAllReady) {
                this.uiCallbacks.onAllReady(data);
            }
        });

        this.socket.on('alarm_set', data => {
            if (this.uiCallbacks.onAlarmSet) {
                this.uiCallbacks.onAlarmSet(data);
            }
        });

        this.socket.on('alarm_triggered', data => {
            if (this.uiCallbacks.onAlarmTriggered) {
                this.uiCallbacks.onAlarmTriggered(data);
            }
        });

        this.socket.on('join_failed', data => {
            if (this.uiCallbacks.onJoinFailed) {
                this.uiCallbacks.onJoinFailed(data);
            }
        });

        this.socket.on('game_started', () => {
            if (this.uiCallbacks.onGameStarted) {
                this.uiCallbacks.onGameStarted();
            }
        });
    }

    // 加入房間：建立 socket 連線後立刻送出 join_room 請求
    joinRoom(roomId) {
        if (roomId) {
            this.socket.emit('join_room', { room_id: roomId });
        }
    }

    // READY / UNREADY 狀態切換，傳給後端更新房間狀態
    sendReadyStatus(isReady) {
        if (isReady) {
            this.socket.emit('player_ready', { room_id: this.ROOM_ID });
        } else {
            this.socket.emit('player_unready', { room_id: this.ROOM_ID });
        }
    }

    sendAlarmTime(time) {
        this.socket.emit('set_alarm', { room_id: this.ROOM_ID, time: time });
    }

    sendTestAlarm() {
        this.socket.emit('test_alarm_sound');
    }

    sendStartGame() {
        this.socket.emit('start_game', { room_id: this.ROOM_ID });
    }

    isHost() {
        return this.socket.id === this.currentHostSid;
    }
}

// UI 回呼函式：當伺服器推送狀態時，對應更新畫面元素
// --- UI 回呼函式 ---
// server 推送事件時由這裡負責將資料映射到 DOM 元素與互動狀態
const uiCallbacks = {
    onHardwareStatus: data => {
        lastIsSpeaker = data.is_speaker;
        updateHardwareWarningUI();
    },
    onTestAlarmStatus: data => {
        const t = translations[currentLang];
        if (data.status === 'started') {
            isTestingVolume = true;
            testVolButton.disabled = true;
            testVolButton.textContent = t.playing;
            testVolButton.style.opacity = '0.6';
            testVolButton.style.cursor = 'not-allowed';
        } else if (data.status === 'finished') {
            isTestingVolume = false;
            testVolButton.disabled = false;
            testVolButton.textContent = t.test_volume;
            testVolButton.style.opacity = '1.0';
            testVolButton.style.cursor = 'pointer';
        }
    },
    onConnect: () => {},
    onRoomStateUpdate: (state, currentSocketId) => {
        const colors = ["blue", "green", "pink", "red"];

        document.querySelectorAll('.character-circle').forEach(el => {
            el.style.opacity = '0.2';
        });
        document.querySelectorAll('.ready-label').forEach(el => {
            el.style.visibility = 'hidden';
        });
        document.querySelectorAll('.me-arrow').forEach(el => {
            el.style.visibility = 'hidden';
        });
        document.querySelectorAll('.host-crown').forEach(el => {
            el.style.visibility = 'hidden';
        });

        const sids = Object.keys(state.players);
        sids.forEach((sid, index) => {
            const player = state.players[sid];
            const color = colors[index];
            const slot = document.getElementById(`slot-${color}`);
            if (slot) {
                slot.querySelector('.character-circle').style.opacity = '1.0';
                if (player.ready) {
                    slot.querySelector('.ready-label').style.visibility = 'visible';
                }
                if (sid === currentSocketId) {
                    slot.querySelector('.me-arrow').style.visibility = 'visible';
                }
                if (sid === state.host_sid) {
                    slot.querySelector('.host-crown').style.visibility = 'visible';
                }
            }
        });

        if (state.players[currentSocketId] && state.players[currentSocketId].ready) {
            readyButton.classList.add('active');
        } else {
            readyButton.classList.remove('active');
        }

        const isHost = currentSocketId === state.host_sid;
        const isFull = state.count === 4;
        const alarmHint = document.getElementById('alarm-hint');
        const hasTriggered = alarmHint.dataset.triggered === 'true';
        const isBusy = !!state.alarm_time || hasTriggered;
        alarmClock.style.cursor = isHost && isFull && !isBusy ? 'pointer' : 'default';
        alarmHint.style.visibility = isFull && !isBusy ? 'visible' : 'hidden';
        if (!isFull) alarmHint.dataset.triggered = 'false';
    },
    onAllReady: data => {
        readyButton.disabled = true;
        readyButton.style.cursor = 'not-allowed';
        readyButton.style.opacity = '0.6';
        const overlay = document.getElementById('countdown-overlay');
        const num = document.getElementById('countdown-number');
        overlay.style.display = 'flex';
        let count = data.countdown;
        num.textContent = count;
        const timer = setInterval(() => {
            count--;
            if (count <= 0) {
                clearInterval(timer);
                num.textContent = 'GO!';
                socketManager.sendStartGame();
            } else {
                num.textContent = count;
            }
        }, 1000);
    },
    onAlarmSet: data => {
        document.getElementById('sleep-overlay').style.display = 'flex';
        const t = translations[currentLang];
        document.getElementById('display-set-alarm-time').textContent = `${t.alarm_time_prefix}${data.time}`;
        console.log('鬧鐘已設定，進入睡眠模式...');
    },
    onAlarmTriggered: (data) => {
        document.getElementById('sleep-overlay').style.display = 'none';
        console.log('時間到！喚醒玩家！');
        readyButton.style.display = 'block';
        const alarmHint = document.getElementById('alarm-hint');
        alarmHint.style.visibility = 'hidden';
        alarmHint.dataset.triggered = 'true';
    },
    onJoinFailed: data => {
        if (data.reason === 'full') {
            document.getElementById('room-full-overlay').style.display = 'flex';
        }
    },
    onGameStarted: () => {
        document.getElementById('countdown-overlay').style.display = 'none';
        console.log('伺服器確認：遊戲正式開始！');
        // 透過 pywebview JS API 關閉 lobby 視窗（window.close() 在 pywebview 無效）
        setTimeout(() => {
            if (window.pywebview) {
                window.pywebview.api.close_lobby();
            }
        }, 300);
    }
};

let selectedHour = 8;
let selectedMinute = 30;

// 時間選擇器：計算並顯示目前選擇的鬧鐘時間與倒數提示
function updatePickerDisplay() {
    pickerHourSpan.textContent = String(selectedHour).padStart(2, '0');
    pickerMinuteSpan.textContent = String(selectedMinute).padStart(2, '0');
    const now = new Date();
    let alarmDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), selectedHour, selectedMinute, 0);
    if (alarmDate <= now) {
        alarmDate.setDate(alarmDate.getDate() + 1);
    }
    const diffMs = alarmDate - now;
    const diffHrs = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    const t = translations[currentLang];
    const timeStr = currentLang === 'zh'
        ? `${diffHrs} 小時 ${diffMins} 分鐘`
        : `${diffHrs}h ${diffMins}m`;
    document.getElementById('time-remaining-hint').textContent = t.time_until.replace('$t', timeStr);
}

// 顯示時間選擇器：房長點擊鬧鐘時間後開啟設定介面
function showTimePicker() {
    timePickerModal.style.display = 'flex';
    const now = new Date();
    selectedHour = now.getHours();
    selectedMinute = now.getMinutes();
    updatePickerDisplay();
}

function hideTimePicker() {
    timePickerModal.style.display = 'none';
}

function handleTimeChange(unit, isUp) {
    if (unit === 'hour') {
        selectedHour = isUp ? (selectedHour + 1) % 24 : (selectedHour - 1 + 24) % 24;
    } else {
        selectedMinute = isUp ? (selectedMinute + 1) % 60 : (selectedMinute - 1 + 60) % 60;
    }
    updatePickerDisplay();
}

function stopPress() {
    clearTimeout(pressTimer);
    clearInterval(repeatInterval);
}

let pressTimer = null;
let repeatInterval = null;

document.querySelectorAll('.time-btn').forEach(button => {
    const unit = button.dataset.unit;
    const isUp = button.classList.contains('up');
    button.onmousedown = e => {
        e.preventDefault();
        handleTimeChange(unit, isUp);
        pressTimer = setTimeout(() => {
            repeatInterval = setInterval(() => {
                handleTimeChange(unit, isUp);
            }, 100);
        }, 500);
    };
    button.onmouseup = stopPress;
    button.onmouseleave = stopPress;
    button.ontouchstart = button.onmousedown;
    button.ontouchend = stopPress;
});

setTimeBtn.onclick = () => {
    const time = `${String(selectedHour).padStart(2, '0')}:${String(selectedMinute).padStart(2, '0')}`;
    socketManager.sendAlarmTime(time);
    hideTimePicker();
};

cancelTimeBtn.onclick = hideTimePicker;

// 綁定大廳主要按鈕事件
if (readyButton) readyButton.onclick = sendReady;
if (inviteButton) inviteButton.onclick = copyInviteLink;
const langBtn = document.getElementById('btn-toggle-language');
if (langBtn) langBtn.onclick = toggleLanguage;

if (testVolButton) {
    testVolButton.onclick = () => {
        if (socketManager) socketManager.sendTestAlarm();
    };
}

// 程式啟動入口：要求房間 ID，顯示房間資訊，並建立 SocketManager
// 程式啟動入口：如果沒有 room 參數，提示使用者輸入；然後建立 socket 連線
function startApp() {
    // 避免使用 while 導致 prompt 被阻擋時進入死迴圈
    if (!ROOM_ID || !ROOM_ID.trim()) {
        try {
            ROOM_ID = prompt(translations[currentLang].room_prompt, 'room-' + Math.floor(Math.random() * 1000));
        } catch (e) {
            console.warn("Prompt is not supported in this environment or was cancelled.");
        }
        // 如果 prompt 失敗或被取消，給予預設 ID
        if (!ROOM_ID || !ROOM_ID.trim()) {
            ROOM_ID = 'room-' + Math.floor(Math.random() * 1000);
            console.log("Using default room ID:", ROOM_ID);
        }
    }

    document.getElementById('displayRoomId').textContent = ROOM_ID;
    socketManager = new SocketManager(window.location.origin, ROOM_ID, uiCallbacks);
    if (alarmClock) { // 增加檢查，避免 alarmClock 為 null
        alarmClock.onclick = () => {
            if (socketManager?.isHost() && alarmClock.style.cursor === 'pointer') {
                showTimePicker();
            }
        };
    }
}

// 使用者按 READY 時觸發，將準備狀態送到後端
function sendReady() {
    if (!socketManager) return;
    const isReady = !readyButton.classList.contains('active');
    socketManager.sendReadyStatus(isReady);
}

function copyInviteLink() {
    const url = `${window.location.origin}${window.location.pathname}?room=${ROOM_ID}`;
    navigator.clipboard.writeText(url).then(() => alert(translations[currentLang].invite_success));
}

function hideRoomFullOverlay() {
    document.getElementById('room-full-overlay').style.display = 'none';
}

tryAnotherRoomButton.onclick = () => {
    hideRoomFullOverlay();
    window.location.href = window.location.pathname;
};

updateLanguage();
updateClock();
setInterval(updateClock, 1000);
startApp();
