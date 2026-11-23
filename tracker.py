"""Tracker de comportamento (teclado + rato) do MindSync.

Só regista timing e contagens, nunca o conteúdo do que se escreve.
Gera uma linha por janela de 5s com TOTAIS (somas), para que o servidor possa
agregar de forma exata (soma dos totais, divisão no fim).
"""
import math
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

import requests
from pynput import keyboard, mouse

# Prioridade baixa (só tem efeito no Windows; noutros sistemas é ignorado)
try:
    import psutil
    psutil.Process(os.getpid()).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    pass

# ---------------- CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.txt")
RAW_DIR = os.path.join(BASE_DIR, "raw")

WINDOW_S = 5              # tamanho da janela
SEND_INTERVAL = 60        # envio em lotes
MAX_BUFFER = 5000         # ~7h de janelas ativas guardadas se o servidor estiver em baixo
PAUSE_MIN, PAUSE_MAX = 2.0, 10.0   # micro-pausa: intervalo entre teclas nesta gama
BACKSPACE_EPISODE_GAP = 1.0        # backspaces com menos de 1s entre si = 1 episódio
GESTURE_GAP = 1.0                  # gesto de rato fecha após 1s parado
MIN_SEG_PX = 3                     # ignora micro-tremores ao medir mudanças de direção
DIR_CHANGE_RAD = math.radians(45)  # curva "brusca"
RAW_DAYS = 7                       # dias de timestamps em bruto guardados localmente


def load_config():
    cfg = {
        "USER_ID": "",
        "API_URL": "http://localhost:8000/api/telemetry",
        "API_TOKEN": "",
        "RAW_LOG": "1",
    }
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(
                "USER_ID=muda_isto\n"
                "API_URL=http://localhost:8000/api/telemetry\n"
                "API_TOKEN=\n"
                "RAW_LOG=1\n"
            )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    for k in cfg:  # variáveis de ambiente MINDSYNC_<CHAVE> têm prioridade
        cfg[k] = os.environ.get("MINDSYNC_" + k, cfg[k])
    return cfg


cfg = load_config()
if cfg["USER_ID"] in ("", "muda_isto"):
    sys.exit("Define USER_ID em config.txt antes de arrancar o tracker.")

OS_TYPE = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")

# ---------------- ESTADO ----------------
lock = threading.Lock()
outbox = deque(maxlen=MAX_BUFFER)


def new_window():
    return {
        "keys": 0, "backspaces": 0, "corr_episodes": 0,
        "n_iki": 0, "sum_iki": 0.0, "sumsq_iki": 0.0, "micro_pauses": 0,
        "path_px": 0.0, "disp_px": 0.0, "gesture_s": 0.0, "gestures": 0,
        "dir_changes": 0, "clicks": 0,
    }


win = new_window()
raw_keys = []          # (timestamp, 'k' | 'b') -> só timing, nunca a tecla
last_key_t = None
last_bs_t = None
mouse_traj = []        # (x, y, t) do gesto em curso
last_move_t = 0.0
last_sample_t = 0.0

IGNORED_KEYS = {
    getattr(keyboard.Key, n)
    for n in (
        "shift", "shift_l", "shift_r", "ctrl", "ctrl_l", "ctrl_r",
        "alt", "alt_l", "alt_r", "alt_gr", "cmd", "cmd_l", "cmd_r", "caps_lock",
        "up", "down", "left", "right", "home", "end", "page_up", "page_down",
    )
    if hasattr(keyboard.Key, n)
}
BACKSPACE_KEYS = {keyboard.Key.backspace, keyboard.Key.delete}


# ---------------- LISTENERS ----------------
def on_press(key):
    global last_key_t, last_bs_t
    try:
        if key in IGNORED_KEYS:
            return
        now = time.time()
        is_bs = key in BACKSPACE_KEYS
        with lock:
            win["keys"] += 1
            if is_bs:
                win["backspaces"] += 1
                if last_bs_t is None or now - last_bs_t > BACKSPACE_EPISODE_GAP:
                    win["corr_episodes"] += 1
                last_bs_t = now
            if last_key_t is not None:
                gap = now - last_key_t
                if gap < PAUSE_MIN:
                    win["n_iki"] += 1
                    win["sum_iki"] += gap
                    win["sumsq_iki"] += gap * gap
                elif gap <= PAUSE_MAX:
                    win["micro_pauses"] += 1
            last_key_t = now
            raw_keys.append((now, "b" if is_bs else "k"))
    except Exception:
        pass


def close_gesture():
    """Fecha o gesto em curso e soma-o à janela atual. Chamar com o lock tomado."""
    global mouse_traj
    pts, mouse_traj = mouse_traj, []
    if len(pts) < 2:
        return
    dur = pts[-1][2] - pts[0][2]
    if dur <= 0:
        return
    path, changes, prev_ang = 0.0, 0, None
    for i in range(1, len(pts)):
        dx, dy = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        seg = math.hypot(dx, dy)
        path += seg
        if seg >= MIN_SEG_PX:
            ang = math.atan2(dy, dx)
            if prev_ang is not None:
                d = abs(ang - prev_ang)
                if min(d, 2 * math.pi - d) >= DIR_CHANGE_RAD:
                    changes += 1
            prev_ang = ang
    disp = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    win["path_px"] += path
    win["disp_px"] += disp
    win["gesture_s"] += dur
    win["gestures"] += 1
    win["dir_changes"] += changes


def on_move(x, y):
    global last_move_t, last_sample_t
    try:
        now = time.time()
        if now - last_sample_t < 0.020:
            return
        with lock:
            if mouse_traj and now - last_move_t > GESTURE_GAP:
                close_gesture()
            mouse_traj.append((x, y, now))
            last_move_t = now
            last_sample_t = now
    except Exception:
        pass


def on_click(x, y, button, pressed):
    if pressed:
        try:
            with lock:
                win["clicks"] += 1
        except Exception:
            pass


# ---------------- WORKERS ----------------
def write_raw(items):
    """Timestamps das teclas (sem a tecla) para recalcular features mais tarde."""
    if not items or cfg["RAW_LOG"] != "1":
        return
    try:
        os.makedirs(RAW_DIR, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(os.path.join(RAW_DIR, f"keys_{day}.csv"), "a", encoding="utf-8") as f:
            f.writelines(f"{int(t * 1000)},{kind}\n" for t, kind in items)
    except Exception:
        pass


def purge_raw():
    try:
        limit = time.time() - RAW_DAYS * 86400
        for name in os.listdir(RAW_DIR):
            p = os.path.join(RAW_DIR, name)
            if name.startswith("keys_") and os.path.getmtime(p) < limit:
                os.remove(p)
    except Exception:
        pass


def flush_window(start):
    global win, raw_keys
    with lock:
        w, win = win, new_window()
        raw, raw_keys = raw_keys, []
        if w["keys"] > 0 or w["gestures"] > 0 or w["clicks"] > 0:
            w["window_start"] = datetime.fromtimestamp(start, timezone.utc).isoformat()
            w["kb_active"] = 1 if w["keys"] > 0 else 0
            outbox.append(w)
    write_raw(raw)


def window_worker():
    while True:
        try:
            now = time.time()
            start = math.floor(now / WINDOW_S) * WINDOW_S
            time.sleep(start + WINDOW_S - now + 0.01)
            flush_window(start)
            if start % 3600 < WINDOW_S:
                purge_raw()
        except Exception:
            time.sleep(1)


def mouse_worker():
    while True:
        try:
            time.sleep(0.5)
            with lock:
                if mouse_traj and time.time() - last_move_t > GESTURE_GAP:
                    close_gesture()
        except Exception:
            pass


def network_worker():
    headers = {"Authorization": f"Bearer {cfg['API_TOKEN']}"}
    while True:
        time.sleep(SEND_INTERVAL)
        try:
            with lock:
                batch = list(outbox)[:1000]
            if not batch:
                continue
            r = requests.post(
                cfg["API_URL"],
                json={"user_id": cfg["USER_ID"], "os_type": OS_TYPE, "windows": batch},
                headers=headers,
                timeout=10,
            )
            if r.status_code == 200:  # só apaga depois de o servidor aceitar
                with lock:
                    for _ in range(min(len(batch), len(outbox))):
                        outbox.popleft()
        except Exception:
            pass  # fica no buffer e reenvia no próximo ciclo (o servidor ignora duplicados)


if __name__ == "__main__":
    purge_raw()
    for fn in (window_worker, mouse_worker, network_worker):
        threading.Thread(target=fn, daemon=True).start()
    k = keyboard.Listener(on_press=on_press)
    m = mouse.Listener(on_move=on_move, on_click=on_click)
    k.start()
    m.start()
    k.join()
