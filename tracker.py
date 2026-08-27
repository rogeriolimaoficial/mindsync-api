import time
import threading
import requests
import math
import os
from pynput import keyboard, mouse
from datetime import datetime, timezone

# --- PRIORIDADE BAIXA (Consumo Residual de Recursos) ---
try:
    import psutil
    p = psutil.Process(os.getpid())
    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass

# --- CONFIGURAÇÕES DO SERVIDOR LOCAL ---
API_URL = "http://localhost:8000/api/telemetry"
SEND_INTERVAL = 60  # Envia lotes a cada 1 minuto[cite: 2]
MAX_BUFFER_ITEMS = 500

# --- CONFIGURAÇÃO DE UTILIZADOR ---
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.txt")[cite: 2]

def load_user_id():
    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w") as f:
                f.write("USER_ID=miguel_user\n")
        except Exception:
            pass
        return "miguel_user"
    try:
        with open(CONFIG_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("USER_ID="):
                    val = line.split("=", 1)[1].strip()
                    if val and val != "muda_isto":
                        return val
    except Exception:
        pass
    return "miguel_user"

USER_ID = load_user_id()

# --- ESTADO TECLADO ---
kb_lock = threading.Lock()[cite: 2]
kb_total = 0[cite: 2]
kb_corrections = 0[cite: 2]
kb_events = [][cite: 2]

# --- ESTADO RATO ---
mouse_lock = threading.Lock()[cite: 2]
mouse_traj = [][cite: 2]
last_mouse_time = time.time()[cite: 2]
last_sample_time = 0[cite: 2]
mouse_events = [][cite: 2]

# --- LISTENERS ---
def on_press(key):
    global kb_total, kb_corrections
    try:
        with kb_lock:[cite: 2]
            kb_total += 1[cite: 2]
            if key in [keyboard.Key.backspace, keyboard.Key.delete]:[cite: 2]
                kb_corrections += 1[cite: 2]
    except Exception:
        pass

def on_move(x, y):
    global mouse_traj, last_mouse_time, last_sample_time
    try:
        now = time.time()[cite: 2]
        if now - last_sample_time < 0.020:[cite: 2]
            return
        last_sample_time = now[cite: 2]
        with mouse_lock:[cite: 2]
            mouse_traj.append((x, y, now))[cite: 2]
            last_mouse_time = now[cite: 2]
    except Exception:
        pass

# --- WORKER TECLADO (Blocos de 5s) ---
def keyboard_worker():
    global kb_total, kb_corrections, kb_events
    while True:
        time.sleep(5)[cite: 2]
        with kb_lock:[cite: 2]
            if kb_total > 0:[cite: 2]
                kb_events.append({[cite: 2]
                    "timestamp": datetime.now(timezone.utc).isoformat(),[cite: 2]
                    "duration_s": 5,[cite: 2]
                    "total_keys": kb_total,[cite: 2]
                    "correction_keys": kb_corrections[cite: 2]
                })
                if len(kb_events) > MAX_BUFFER_ITEMS:
                    kb_events = kb_events[-MAX_BUFFER_ITEMS:]
            kb_total = 0[cite: 2]
            kb_corrections = 0[cite: 2]

# --- WORKER RATO (Gesto fecha após 1s de paragem) ---
def mouse_worker():
    global mouse_traj, last_mouse_time, mouse_events
    while True:
        time.sleep(0.5)[cite: 2]
        with mouse_lock:[cite: 2]
            if time.time() - last_mouse_time > 1.0 and len(mouse_traj) > 1:[cite: 2]
                t_start = mouse_traj[0][2][cite: 2]
                t_end = mouse_traj[-1][2][cite: 2]
                dur_s = t_end - t_start[cite: 2]

                if dur_s > 0:[cite: 2]
                    dist = sum([cite: 2]
                        math.hypot(mouse_traj[i][0] - mouse_traj[i-1][0], mouse_traj[i][1] - mouse_traj[i-1][1])[cite: 2]
                        for i in range(1, len(mouse_traj))[cite: 2]
                    )
                    straight_dist = math.hypot(mouse_traj[-1][0] - mouse_traj[0][0], mouse_traj[-1][1] - mouse_traj[0][1])[cite: 2]
                    ratio = straight_dist / dist if dist > 0 else 1.0[cite: 2]
                    speed = dist / dur_s[cite: 2]

                    mouse_events.append({[cite: 2]
                        "timestamp": datetime.fromtimestamp(t_end, timezone.utc).isoformat(),[cite: 2]
                        "duration_s": round(dur_s, 3),[cite: 2]
                        "distance_px": round(dist, 2),[cite: 2]
                        "straight_distance_px": round(straight_dist, 2),[cite: 2]
                        "straightness_ratio": round(ratio, 3),[cite: 2]
                        "speed_px_s": round(speed, 2)[cite: 2]
                    })
                    if len(mouse_events) > MAX_BUFFER_ITEMS:
                        mouse_events = mouse_events[-MAX_BUFFER_ITEMS:]
                mouse_traj = [][cite: 2]

# --- WORKER REDE (Envio em lotes a cada 60s) ---
def network_worker():
    global kb_events, mouse_events
    while True:
        time.sleep(SEND_INTERVAL)[cite: 2]
        with kb_lock:[cite: 2]
            kb_batch = list(kb_events)[cite: 2]
            kb_events.clear()[cite: 2]
        with mouse_lock:[cite: 2]
            mouse_batch = list(mouse_events)[cite: 2]
            mouse_events.clear()[cite: 2]

        if not kb_batch and not mouse_batch:[cite: 2]
            continue[cite: 2]

        payload = {[cite: 2]
            "user_id": USER_ID,[cite: 2]
            "os_type": "windows",
            "keyboard_events": kb_batch,[cite: 2]
            "mouse_events": mouse_batch[cite: 2]
        }

        try:
            res = requests.post(API_URL, json=payload, timeout=5)
            if res.status_code != 200:
                with kb_lock: kb_events = kb_batch + kb_events[cite: 2]
                with mouse_lock: mouse_events = mouse_batch + mouse_events[cite: 2]
        except Exception:
            with kb_lock: kb_events = kb_batch + kb_events[cite: 2]
            with mouse_lock: mouse_events = mouse_batch + mouse_events[cite: 2]

# --- ARRANQUE ---
if __name__ == "__main__":
    threading.Thread(target=keyboard_worker, daemon=True).start()[cite: 2]
    threading.Thread(target=mouse_worker, daemon=True).start()[cite: 2]
    threading.Thread(target=network_worker, daemon=True).start()[cite: 2]

    k_listener = keyboard.Listener(on_press=on_press)[cite: 2]
    m_listener = mouse.Listener(on_move=on_move)[cite: 2]

    k_listener.start()[cite: 2]
    m_listener.start()[cite: 2]
    k_listener.join()[cite: 2]