import html
import json
import logging
import secrets
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from features import build_blocks
from pages import CHECKIN_HTML, EXPLORE_HTML

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mindsync")

app = FastAPI(title="MindSync Simple Hub")

DB_FILE = "mindsync.db"
XLSX_FILE = "mindsync_dataset.xlsx"
LISBON_TZ = ZoneInfo("Europe/Lisbon")

# O token TEM de vir de uma env var no Render.
# O valor por omissão só existe para não partir em dev local; nunca o uses em produção.
SECRET_API_TOKEN = os.environ.get("MINDSYNC_API_TOKEN", "changeme-local-dev-only")
if SECRET_API_TOKEN == "changeme-local-dev-only":
    logger.warning(
        "MINDSYNC_API_TOKEN não definido, a usar token de desenvolvimento. "
        "Define a env var no Render antes de ir para produção."
    )

# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class Window5s(BaseModel):
    """Totais de uma janela de 5s (ver tracker.py)."""
    window_start: str
    keys: int = 0
    backspaces: int = 0
    corr_episodes: int = 0
    n_iki: int = 0
    sum_iki: float = 0.0
    sumsq_iki: float = 0.0
    micro_pauses: int = 0
    kb_active: int = 0
    path_px: float = 0.0
    disp_px: float = 0.0
    gesture_s: float = 0.0
    gestures: int = 0
    dir_changes: int = 0
    clicks: int = 0

class TelemetryBatchPayload(BaseModel):
    user_id: str
    os_type: str = Field(default="windows")
    windows: List[Window5s] = Field(max_length=2000)

class AppleWatchPayload(BaseModel):
    user_id: str
    date: str
    hrv_sdnn_ms: float
    resting_heart_rate_bpm: int
    deep_sleep_minutes: float
    rem_sleep_minutes: float
    core_sleep_minutes: float
    temp_wrist_celsius: Optional[float] = None

class WhoopPayload(BaseModel):
    user_id: str
    date: str
    recovery_score_pct: float
    sleep_performance_pct: float
    hrv_rmssd_ms: float
    resting_heart_rate_bpm: int
    total_sleep_minutes: float
    deep_slow_wave_sleep_minutes: float
    rem_sleep_minutes: float

class GarminPayload(BaseModel):
    user_id: str
    date: str
    body_battery_max: int
    sleep_score: int
    hrv_weekly_avg_ms: float
    resting_heart_rate_bpm: int
    total_sleep_seconds: int
    deep_sleep_seconds: int
    rem_sleep_seconds: int

class AmazfitPayload(BaseModel):
    user_id: str
    date: str
    sleep_score: int
    resting_heart_rate_bpm: int
    total_sleep_minutes: float
    deep_sleep_minutes: float
    rem_sleep_minutes: float
    readiness_score: Optional[int] = None
    hrv_score_ms: Optional[float] = None

class GroundTruthPlaceholder(BaseModel):
    # Perguntas do questionário ainda não fechadas -> slots genéricos por agora.
    # Quando decidires as perguntas finais, troca slot_1/slot_2 por campos nomeados.
    user_id: str
    timestamp: Optional[str] = None
    # slot_1 = energia (1 a 5), slot_2 = foco (1 a 5)
    slot_1: Optional[int] = Field(default=None, ge=1, le=5)
    slot_2: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=300)


# ==========================================
# LIGAÇÃO À BASE DE DADOS
# ==========================================
def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def verify_token(authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {SECRET_API_TOKEN}":
        raise HTTPException(status_code=401, detail="Token inválido.")

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    # Uma linha por janela de 5s ativa, com TOTAIS (não médias).
    # UNIQUE evita duplicados quando o tracker reenvia um lote.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS windows_5s (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            os_type TEXT,
            window_start TEXT NOT NULL,
            keys INTEGER, backspaces INTEGER, corr_episodes INTEGER,
            n_iki INTEGER, sum_iki REAL, sumsq_iki REAL, micro_pauses INTEGER,
            kb_active INTEGER,
            path_px REAL, disp_px REAL, gesture_s REAL, gestures INTEGER,
            dir_changes INTEGER, clicks INTEGER,
            created_at TEXT,
            UNIQUE(user_id, window_start)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_biometrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            recorded_date TEXT,
            device_brand TEXT,
            rhr_bpm INTEGER,
            hrv_rmssd_ms REAL,
            total_sleep_min REAL,
            deep_sleep_min REAL,
            rem_sleep_min REAL,
            recovery_score REAL,
            created_at TEXT,
            UNIQUE(user_id, recorded_date)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ground_truth_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT,
            slot_1 INTEGER,
            slot_2 INTEGER,
            notes TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_windows_user_ts ON windows_5s(user_id, window_start)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bio_user_date ON daily_biometrics(user_id, recorded_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_labels_user_ts ON ground_truth_labels(user_id, timestamp)")
    conn.commit()
    conn.close()

init_db()

def build_dataset(conn) -> pd.DataFrame:
    """Blocos de 15 min (calculados a partir das janelas) + biometria do dia."""
    blocks = build_blocks(conn)
    bio = pd.read_sql_query("SELECT * FROM daily_biometrics", conn)
    if blocks.empty or bio.empty:
        return blocks
    return blocks.merge(
        bio.drop(columns=["id", "created_at"]),
        left_on=["user_id", "local_date"], right_on=["user_id", "recorded_date"], how="left",
    )

def parse_event_timestamp(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.split("+")[0].replace("Z", "")).replace(tzinfo=timezone.utc)
    except Exception:
        return None

# ==========================================
# INGESTÃO DE TELEMETRIA (janelas de 5s; a agregação a 15 min é feita em features.py)
# ==========================================
@app.post("/api/telemetry")
def receive_telemetry(payload: TelemetryBatchPayload, _: None = Depends(verify_token)):
    now_iso = datetime.now(timezone.utc).isoformat()
    os_type = payload.os_type.lower()
    rows = []
    for w in payload.windows:
        dt = parse_event_timestamp(w.window_start)
        if dt is None:
            logger.warning("Timestamp inválido, a ignorar janela: %s", w.window_start)
            continue
        rows.append((
            payload.user_id, os_type, dt.strftime("%Y-%m-%d %H:%M:%S"),
            w.keys, w.backspaces, w.corr_episodes,
            w.n_iki, w.sum_iki, w.sumsq_iki, w.micro_pauses,
            w.kb_active,
            w.path_px, w.disp_px, w.gesture_s, w.gestures,
            w.dir_changes, w.clicks,
            now_iso,
        ))
    if not rows:
        return {"status": "ignored_idle"}

    conn = get_conn()
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO windows_5s (
            user_id, os_type, window_start,
            keys, backspaces, corr_episodes,
            n_iki, sum_iki, sumsq_iki, micro_pauses,
            kb_active,
            path_px, disp_px, gesture_s, gestures,
            dir_changes, clicks,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.commit()
    inserted = conn.total_changes - before
    conn.close()
    return {"status": "success", "received": len(rows), "inserted": inserted}

# ==========================================
# INGESTÃO DE WEARABLES
# ==========================================
def save_bio(user_id, date_str, brand, rhr, hrv, total_s, deep_s, rem_s, rec):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO daily_biometrics (
            user_id, recorded_date, device_brand, rhr_bpm, hrv_rmssd_ms,
            total_sleep_min, deep_sleep_min, rem_sleep_min, recovery_score, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, recorded_date) DO UPDATE SET
            device_brand=excluded.device_brand,
            rhr_bpm=excluded.rhr_bpm,
            hrv_rmssd_ms=excluded.hrv_rmssd_ms,
            total_sleep_min=excluded.total_sleep_min,
            deep_sleep_min=excluded.deep_sleep_min,
            rem_sleep_min=excluded.rem_sleep_min,
            recovery_score=excluded.recovery_score,
            created_at=excluded.created_at
        """,
        (
            user_id,
            date_str,
            brand,
            rhr,
            hrv,
            round(total_s / 60, 1),
            round(deep_s / 60, 1),
            round(rem_s / 60, 1),
            rec,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

@app.post("/api/biometrics/apple-watch")
def ingest_aw(p: AppleWatchPayload, _: None = Depends(verify_token)):
    # Aproximação SDNN -> RMSSD (~1.15x). É uma heurística, não uma conversão validada
    # clinicamente — revê este fator quando tiveres dados reais para comparar entre wearables.
    norm_hrv = round(p.hrv_sdnn_ms * 1.15, 1)
    tot_s = int((p.deep_sleep_minutes + p.rem_sleep_minutes + p.core_sleep_minutes) * 60)
    rec = round(min(100.0, (min(1.2, norm_hrv / 60.0) * 50.0) + (min(1.0, tot_s / 28800.0) * 50.0)), 1)
    save_bio(
        p.user_id, p.date, "Apple Watch", p.resting_heart_rate_bpm, norm_hrv,
        tot_s, int(p.deep_sleep_minutes * 60), int(p.rem_sleep_minutes * 60), rec,
    )
    return {"status": "success"}

# ---- Apple Watch via Atalhos (iOS): o atalho envia linhas de texto, o servidor faz as contas ----
class AppleWatchRawPayload(BaseModel):
    user_id: str
    sleep_lines: str = Field(default="", max_length=200_000)   # "Fase|início|fim", uma por linha
    hrv_values: str = Field(default="", max_length=50_000)     # um valor (ms) por linha
    resting_hr: str = Field(default="", max_length=5_000)      # um valor (bpm) por linha
    date: Optional[str] = None                                 # AAAA-MM-DD; por omissão, dia em que acordaste

_STAGES = [  # por ordem de prioridade quando há sobreposição
    ("deep", ("deep", "profund")),
    ("rem", ("rem",)),
    ("core", ("core", "núcleo", "nucleo", "principal", "central")),
    ("asleep", ("asleep", "adorm", "unspecified", "não especificad", "nao especificad")),
]
_IGNORED = ("awake", "acordad", "desperto", "in bed", "inbed", "na cama", "cama")

def _classify_stage(raw: str) -> Optional[str]:
    s = raw.strip().lower()
    if any(k in s for k in _IGNORED):
        return "ignore"
    for name, keys in _STAGES:
        if any(s == k or s.startswith(k) for k in keys):
            return name
    return None

def _parse_dt(txt: str) -> Optional[pd.Timestamp]:
    txt = txt.strip()
    try:
        ts = pd.Timestamp(datetime.fromisoformat(txt.replace("Z", "+00:00")))
    except Exception:
        try:
            ts = pd.to_datetime(txt, dayfirst=True)
        except Exception:
            return None
    if pd.isna(ts):
        return None
    return ts.tz_localize(LISBON_TZ) if ts.tzinfo is None else ts.tz_convert(LISBON_TZ)

def _merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out

def _subtract(iv, cut):
    out = []
    for a, b in iv:
        cur = a
        for c, d in cut:
            if d <= cur or c >= b:
                continue
            if c > cur:
                out.append((cur, c))
            cur = max(cur, d)
        if cur < b:
            out.append((cur, b))
    return out

def _minutes(iv) -> float:
    return sum((b - a).total_seconds() for a, b in iv) / 60.0

def _numbers(txt: str) -> list:
    import re
    return [float(x.replace(",", ".")) for x in re.findall(r"-?\d+(?:[.,]\d+)?", txt or "")]

@app.post("/api/biometrics/apple-watch-raw")
def ingest_aw_raw(p: AppleWatchRawPayload, _: None = Depends(verify_token)):
    by_stage = {k: [] for k, _ in _STAGES}
    unknown, parsed, last_end = set(), 0, None
    for line in p.sleep_lines.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 3 or not parts[0]:
            continue
        stage = _classify_stage(parts[0])
        a, b = _parse_dt(parts[1]), _parse_dt(parts[2])
        if a is None or b is None or b <= a:
            continue
        if stage is None:
            unknown.add(parts[0])
            continue
        if stage == "ignore":
            continue
        by_stage[stage].append((a, b))
        parsed += 1
        last_end = b if last_end is None or b > last_end else last_end
    if parsed == 0:
        raise HTTPException(status_code=422, detail={
            "erro": "Nenhuma linha de sono reconhecida", "fases_desconhecidas": sorted(unknown),
            "exemplo_esperado": "Core|2026-11-23T01:10:00+00:00|2026-11-23T02:00:00+00:00"})

    # prioridade deep > rem > core > asleep: o que já foi contado numa fase não conta noutra
    merged, taken = {}, []
    for name, _k in _STAGES:
        mine = _subtract(_merge(by_stage[name]), taken)
        merged[name] = mine
        taken = _merge(taken + mine)
    mins = {k: round(_minutes(v), 1) for k, v in merged.items()}
    total = round(sum(mins.values()), 1)

    hrv_list, rhr_list = _numbers(p.hrv_values), _numbers(p.resting_hr)
    hrv = round(sum(hrv_list) / len(hrv_list), 1) if hrv_list else None       # SDNN (ms), média das leituras
    rhr = int(round(rhr_list[-1])) if rhr_list else None
    date_str = p.date or last_end.strftime("%Y-%m-%d")
    # mesma aproximação SDNN -> RMSSD (~1.15x) do endpoint antigo: heurística, não conversão validada
    norm_hrv = round(hrv * 1.15, 1) if hrv is not None else None
    save_bio(p.user_id, date_str, "Apple Watch", rhr, norm_hrv, int(total * 60),
             int(mins["deep"] * 60), int(mins["rem"] * 60), None)
    return {"status": "success", "date": date_str, "sleep_min": {**mins, "total": total},
            "hrv_sdnn_ms": hrv, "hrv_leituras": len(hrv_list), "resting_hr": rhr,
            "linhas_sono_lidas": parsed, "fases_desconhecidas": sorted(unknown)}

@app.post("/api/biometrics/whoop")
def ingest_whoop(p: WhoopPayload, _: None = Depends(verify_token)):
    save_bio(
        p.user_id, p.date, "Whoop", p.resting_heart_rate_bpm, p.hrv_rmssd_ms,
        int(p.total_sleep_minutes * 60), int(p.deep_slow_wave_sleep_minutes * 60),
        int(p.rem_sleep_minutes * 60), p.recovery_score_pct,
    )
    return {"status": "success"}

@app.post("/api/biometrics/garmin")
def ingest_garmin(p: GarminPayload, _: None = Depends(verify_token)):
    save_bio(
        p.user_id, p.date, "Garmin", p.resting_heart_rate_bpm, p.hrv_weekly_avg_ms,
        p.total_sleep_seconds, p.deep_sleep_seconds, p.rem_sleep_seconds, float(p.body_battery_max),
    )
    return {"status": "success"}

@app.post("/api/biometrics/amazfit")
def ingest_amazfit(p: AmazfitPayload, _: None = Depends(verify_token)):
    rec = float(p.readiness_score) if p.readiness_score else float(p.sleep_score)
    save_bio(
        p.user_id, p.date, "Amazfit", p.resting_heart_rate_bpm, p.hrv_score_ms or 0.0,
        int(p.total_sleep_minutes * 60), int(p.deep_sleep_minutes * 60), int(p.rem_sleep_minutes * 60), rec,
    )
    return {"status": "success"}

@app.post("/api/labels")
def ingest_label(p: GroundTruthPlaceholder, _: None = Depends(verify_token)):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ground_truth_labels (user_id, timestamp, slot_1, slot_2, notes) VALUES (?, ?, ?, ?, ?)",
        (p.user_id, p.timestamp or datetime.now(timezone.utc).isoformat(), p.slot_1, p.slot_2, p.notes),
    )
    conn.commit()
    conn.close()
    return {"status": "success"}


# ==========================================
# DASHBOARD & DOWNLOADS
# ==========================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_status(token: Optional[str] = None):
    if token != SECRET_API_TOKEN:
        raise HTTPException(status_code=401, detail="Acesso negado. Usa /dashboard?token=O_TEU_TOKEN")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM windows_5s UNION SELECT DISTINCT user_id FROM daily_biometrics")
    all_users = [r[0] for r in cursor.fetchall() if r[0]]

    now_utc = datetime.now(timezone.utc)
    user_rows = []

    for u in all_users:
        cursor.execute(
            "SELECT MAX(window_start), MAX(os_type), COUNT(*) FROM windows_5s WHERE user_id = ?", (u,)
        )
        last_t, os_raw, n_windows = cursor.fetchone()
        os_type = os_raw.upper() if os_raw else "--"
        active_min = round((n_windows or 0) * 5 / 60.0, 1)

        cursor.execute(
            "SELECT recorded_date, device_brand, recovery_score, hrv_rmssd_ms FROM daily_biometrics WHERE user_id = ? ORDER BY recorded_date DESC LIMIT 1",
            (u,),
        )
        b_row = cursor.fetchone()
        bio_info = (f"{b_row[1]} ({b_row[0]}" + (f" | Rec: {b_row[2]}%" if b_row[2] is not None else "") + (f" | HRV: {b_row[3]}ms" if b_row[3] is not None else "") + ")") if b_row else "Sem Wearable"

        status_html = '<span style="color:#ef4444; font-weight:bold;">● Sem dados recentes</span>'
        last_seen = "Sem dados"
        if last_t:
            try:
                dt_last = datetime.strptime(last_t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                diff_min = (now_utc - dt_last).total_seconds() / 60.0
                dt_last_local = dt_last.astimezone(LISBON_TZ)
                last_seen = f"há {int(diff_min)}m" if diff_min < 120 else dt_last_local.strftime("%d/%m %H:%M")
                if diff_min <= 3:
                    status_html = '<span style="color:#10b981; font-weight:bold;">● A Receber Dados (Online)</span>'
                elif diff_min <= 60:
                    status_html = '<span style="color:#f59e0b; font-weight:bold;">● Ausente (Pausa Recente)</span>'
            except Exception:
                logger.exception("Falha ao processar last_seen para user %s", u)

        user_rows.append(f"""
            <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 12px 16px; font-weight: 600; color: #38bdf8;">{html.escape(u)}</td>
                <td style="padding: 12px 16px;"><span style="background: #1e293b; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{html.escape(os_type)}</span></td>
                <td style="padding: 12px 16px;">{status_html}</td>
                <td style="padding: 12px 16px; color: #94a3b8;">{last_seen}</td>
                <td style="padding: 12px 16px;">{active_min} min ativos</td>
                <td style="padding: 12px 16px; font-size: 12px; color: #94a3b8;">{html.escape(bio_info)}</td>
            </tr>
        """)
    conn.close()

    return f"""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="15">
        <title>MindSync Monitor</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #f8fafc; padding: 30px; }}
            .container {{ max-width: 1050px; margin: 0 auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 20px; margin-bottom: 25px; }}
            .header h1 {{ color: #38bdf8; font-size: 22px; margin: 0; }}
            .btn {{ background: #0284c7; color: white; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 600; margin-left: 8px; }}
            table {{ width: 100%; border-collapse: collapse; background: #161f30; border-radius: 8px; overflow: hidden; border: 1px solid #1e293b; }}
            th {{ background: #0f172a; text-align: left; padding: 12px 16px; font-size: 11px; text-transform: uppercase; color: #94a3b8; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h1>MindSync - Monitor de Estado dos Utilizadores</h1>
                    <p style="color: #94a3b8; font-size: 13px; margin: 4px 0 0 0;">Feed de Telemetria e Conexão de Participantes</p>
                </div>
                <div>
                    <a href="/explore?token={html.escape(token)}" class="btn">Gráficos</a>
                    <a href="/checkin?token={html.escape(token)}" class="btn">Check-in</a>
                    <a href="/api/dataset/download-csv?token={html.escape(token)}" class="btn">⬇ CSV</a>
                    <a href="/api/dataset/download-xlsx?token={html.escape(token)}" class="btn">⬇ XLSX</a>
                </div>
            </div>
            <table>
                <thead>
                    <tr><th>Utilizador</th><th>OS</th><th>Estado da Ligação</th><th>Última Atividade</th><th>Volume Acumulado</th><th>Wearable / Biometria</th></tr>
                </thead>
                <tbody>
                    {''.join(user_rows) if user_rows else "<tr><td colspan='6' style='text-align:center; padding:20px; color:#64748b;'>A aguardar primeiros sinais de telemetria...</td></tr>"}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """

@app.get("/api/dataset/download-csv")
def download_live_csv(token: Optional[str] = None):
    if token != SECRET_API_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido.")
    conn = get_conn()
    df = build_dataset(conn)
    conn.close()
    return Response(
        content=df.to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mindsync_live.csv"'},
    )

@app.get("/api/dataset/download-xlsx")
def download_xlsx(token: Optional[str] = None):
    if token != SECRET_API_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido.")

    conn = get_conn()
    blocks = build_dataset(conn)
    windows = pd.read_sql_query("SELECT * FROM windows_5s", conn)
    bio = pd.read_sql_query("SELECT * FROM daily_biometrics", conn)
    labels = pd.read_sql_query("SELECT * FROM ground_truth_labels", conn)
    conn.close()

    with pd.ExcelWriter(XLSX_FILE, engine="openpyxl") as writer:
        blocks.to_excel(writer, sheet_name="blocks_15m", index=False)
        windows.to_excel(writer, sheet_name="windows_5s", index=False)
        bio.to_excel(writer, sheet_name="daily_biometrics", index=False)
        labels.to_excel(writer, sheet_name="ground_truth_labels", index=False)

    return FileResponse(
        XLSX_FILE,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="mindsync_dataset.xlsx",
    )

# ==========================================
# GRÁFICOS (/explore) E CHECK-IN (/checkin)
# ==========================================
def _check_token(token: Optional[str]):
    if not token or not secrets.compare_digest(token, SECRET_API_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido. Usa ?token=O_TEU_TOKEN")

def _labels_local(conn, user_id: Optional[str] = None) -> pd.DataFrame:
    q, params = "SELECT * FROM ground_truth_labels", ()
    if user_id:
        q, params = q + " WHERE user_id = ?", (user_id,)
    df = pd.read_sql_query(q, conn, params=params)
    if df.empty:
        return df.assign(local_date=[], local_min=[], local_time=[])
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="ISO8601")
    df = df.dropna(subset=["ts"]).copy()
    loc = df["ts"].dt.tz_convert(LISBON_TZ)
    df["local_date"] = loc.dt.strftime("%Y-%m-%d")
    df["local_min"] = loc.dt.hour * 60 + loc.dt.minute
    df["local_time"] = loc.dt.strftime("%H:%M")
    return df

def _records(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records"))

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

@app.get("/explore", response_class=HTMLResponse)
def explore_page(token: Optional[str] = None):
    _check_token(token)
    return EXPLORE_HTML

@app.get("/checkin", response_class=HTMLResponse)
def checkin_page(token: Optional[str] = None):
    _check_token(token)
    return CHECKIN_HTML

@app.get("/api/explore/meta")
def explore_meta(token: Optional[str] = None):
    _check_token(token)
    conn = get_conn()
    blocks = build_blocks(conn)
    labels = _labels_local(conn)
    conn.close()
    users: dict = {}
    for u, d in blocks[["user_id", "local_date"]].drop_duplicates().itertuples(index=False):
        users.setdefault(u, set()).add(d)
    for u, d in labels[["user_id", "local_date"]].drop_duplicates().itertuples(index=False):
        users.setdefault(u, set()).add(d)
    return {"users": [{"user_id": u, "dates": sorted(ds, reverse=True)} for u, ds in sorted(users.items())]}

@app.get("/api/explore/day")
def explore_day(user_id: str, date: str, token: Optional[str] = None):
    _check_token(token)
    conn = get_conn()
    blocks = build_blocks(conn)
    blocks = blocks[(blocks["user_id"] == user_id) & (blocks["local_date"] == date)]
    labels = _labels_local(conn, user_id)
    labels = labels[labels["local_date"] == date].sort_values("local_min")
    bio = pd.read_sql_query(
        "SELECT * FROM daily_biometrics WHERE user_id = ? AND recorded_date = ?", conn, params=(user_id, date)
    )
    conn.close()
    return {
        "blocks": _records(blocks.sort_values("local_min")),
        "labels": _records(labels[["local_min", "local_time", "slot_1", "slot_2", "notes"]]),
        "bio": _records(bio)[0] if not bio.empty else None,
    }

@app.get("/")
def health():
    return {"status": "ok"}
