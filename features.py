"""Agregação das janelas de 5s em blocos de 15 min.

Regra: somar totais e dividir uma só vez no fim (nunca médias de médias).
"""
import pandas as pd

WINDOW_S = 5
BLOCK = "15min"
MIN_KB_ACTIVE_S = 120  # blocos com menos de 2 min de escrita ativa ficam marcados como pouco fiáveis

SUM_COLS = [
    "keys", "backspaces", "corr_episodes", "n_iki", "sum_iki", "sumsq_iki",
    "micro_pauses", "kb_active", "path_px", "disp_px", "gesture_s",
    "gestures", "dir_changes", "clicks",
]

BLOCK_COLS = [
    "user_id", "os_type", "timestamp_block", "local_date",
    "active_s", "kb_active_s", "active_pct", "reliable",
    "typing_kpm", "backspace_ratio_pct", "corr_eps_per_min", "pauses_per_min",
    "iki_mean_ms", "iki_std_ms",
    "mouse_speed_px_s", "straightness_pct", "dir_changes_per_1000px", "clicks",
]


def build_blocks(conn, tz="Europe/Lisbon") -> pd.DataFrame:
    w = pd.read_sql_query("SELECT * FROM windows_5s", conn)
    if w.empty:
        return pd.DataFrame(columns=BLOCK_COLS)

    w["block"] = pd.to_datetime(w["window_start"], utc=True).dt.floor(BLOCK)
    g = w.groupby(["user_id", "block"], as_index=False).agg(
        os_type=("os_type", "last"),
        active_windows=("window_start", "count"),
        **{c: (c, "sum") for c in SUM_COLS},
    )

    def safe(s):  # evita divisões por zero (fica NaN)
        return s.where(s > 0)

    g["active_s"] = g["active_windows"] * WINDOW_S
    g["kb_active_s"] = g["kb_active"] * WINDOW_S
    g["active_pct"] = 100 * g["active_s"] / (15 * 60)
    g["reliable"] = (g["kb_active_s"] >= MIN_KB_ACTIVE_S).astype(int)

    kb_min = safe(g["kb_active_s"] / 60)
    g["typing_kpm"] = g["keys"] / kb_min
    g["backspace_ratio_pct"] = 100 * g["backspaces"] / safe(g["keys"])
    g["corr_eps_per_min"] = g["corr_episodes"] / kb_min
    g["pauses_per_min"] = g["micro_pauses"] / kb_min

    n = safe(g["n_iki"])
    mean = g["sum_iki"] / n
    var = (g["sumsq_iki"] / n - mean ** 2).clip(lower=0)
    g["iki_mean_ms"] = mean * 1000
    g["iki_std_ms"] = (var ** 0.5) * 1000

    path = safe(g["path_px"])
    g["mouse_speed_px_s"] = g["path_px"] / safe(g["gesture_s"])
    g["straightness_pct"] = 100 * g["disp_px"] / path
    g["dir_changes_per_1000px"] = 1000 * g["dir_changes"] / path

    g["timestamp_block"] = g["block"].dt.strftime("%Y-%m-%d %H:%M:00")
    g["local_date"] = g["block"].dt.tz_convert(tz).dt.strftime("%Y-%m-%d")
    return g[BLOCK_COLS].sort_values(["user_id", "timestamp_block"]).reset_index(drop=True)
