import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mindsync")

app = FastAPI(title="MindSync Simple Hub")

DB_FILE = "mindsync.db"
CSV_FILE = "mindsync_live.csv"
XLSX_FILE = "mindsync_dataset.xlsx"
LISBON_TZ = ZoneInfo("Europe/Lisbon")

# O token TEM de vir de uma env var no Render (ver requirements/instruções).
# O valor por omissão só existe para não partir em dev local; nunca o uses em produção.
SECRET_API_TOKEN = os.environ.get("MINDSYNC_API_TOKEN", "changeme-local-dev-only")
if SECRET_API_TOKEN == "changeme-local-dev-only":
    logger.warning(
        "MINDSYNC_API_TOKEN não definido — a usar token de desenvolvimento. "
        "Define a env var no Render antes de ir para produção."
    )

# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class KeyboardEvent(BaseModel):
    timestamp: str
    duration_s: int
    total_keys: int
    correction_keys: int

class MouseEvent(BaseModel):
    timestamp: str
    duration_s: float
    distance_px: float
    straight_distance_px: float
    straightness_ratio: float
    speed_px_s: float

class TelemetryBatchPayload(BaseModel):
    user_id: str
    os_type: str = Field(default="windows")
    keyboard_events: List[KeyboardEvent]
    mouse_events: List[MouseEvent]

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
    slot_1: Optional[int] = None
    slot_2: Optional[int] = None
    notes: Optional[str] = None

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_15m (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            os_type TEXT,
            timestamp_block TEXT,
            active_minutes INTEGER,
            typing_speed_kpm REAL,
            error_rate_pct REAL,
            mouse_speed_px_s REAL,
            straightness_pct REAL,
            created_at TEXT
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_user_block ON telemetry_15m(user_id, timestamp_block)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bio_user_date ON daily_biometrics(user_id, recorded_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_labels_user_ts ON ground_truth_labels(user_id, timestamp)")
    conn.commit()
    conn.close()

init_db()

def export_live_csv():
    try:
        conn = get_conn()
        t_df = pd.read_sql_query("SELECT * FROM telemetry_15m", conn)
        b_df = pd.read_sql_query("SELECT * FROM daily_biometrics", conn)
        conn.close()

        if not t_df.empty:
            t_df["date_key"] = t_df["timestamp_block"].str.slice(0, 10)
            merged = pd.merge(
                t_df, b_df, left_on=["user_id", "date_key"], right_on=["user_id", "recorded_date"], how="left"
            )
            merged.to_csv(CSV_FILE, index=False)
    except Exception:
        logger.exception("Falha ao exportar CSV")

def parse_event_timestamp(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.split("+")[0].replace("Z", "")).replace(tzinfo=timezone.utc)
    except Exception:
        return None

# ==========================================
# MOTOR DE INGESTÃO E AGREGAÇÃO (5s -> 1m -> 15m)
# ==========================================
@app.post("/api/telemetry")
def receive_telemetry(payload: TelemetryBatchPayload, _: None = Depends(verify_token)):
    event_times = []

    # 1. Agrupamento por minuto e cálculo de cadência ativa
    minute_samples = {}
    for kb in payload.keyboard_events:
        if kb.total_keys > 0:  # Ignora 5s com zero dados
            dt = parse_event_timestamp(kb.timestamp)
            if dt is None:
                logger.warning("Timestamp de teclado inválido, a ignorar evento: %s", kb.timestamp)
                continue
            event_times.append(dt)
            min_key = dt.strftime("%Y-%m-%d %H:%M")
            if min_key not in minute_samples:
                minute_samples[min_key] = {"keys": 0, "corr": 0, "active_5s": 0}
            minute_samples[min_key]["keys"] += kb.total_keys
            minute_samples[min_key]["corr"] += kb.correction_keys
            minute_samples[min_key]["active_5s"] += 1

    for m in payload.mouse_events:
        dt = parse_event_timestamp(m.timestamp)
        if dt is not None:
            event_times.append(dt)

    if not minute_samples and not payload.mouse_events:
        return {"status": "ignored_idle"}

    # Transpor para 1 minuto
    min_speeds = []
    min_errors = []
    for m_k, d in minute_samples.items():
        if d["active_5s"] > 0:
            kpm = d["keys"] * (12.0 / d["active_5s"])
            err = (d["corr"] / d["keys"]) * 100.0 if d["keys"] > 0 else 0.0
            min_speeds.append(kpm)
            min_errors.append(err)

    # Métricas de rato
    mouse_speeds = [m.speed_px_s for m in payload.mouse_events if m.speed_px_s > 0]
    mouse_ratios = [m.straightness_ratio * 100.0 for m in payload.mouse_events if m.straightness_ratio > 0]

    # Consolidação do bloco: usa a hora dos EVENTOS (não a hora de chegada do request)
    # e arredonda para o início do bloco de 15 min a que pertence.
    reference_dt = max(event_times) if event_times else datetime.now(timezone.utc)
    block_minute = (reference_dt.minute // 15) * 15
    block_dt = reference_dt.replace(minute=block_minute, second=0, microsecond=0)
    block_time = block_dt.strftime("%Y-%m-%d %H:%M:00")

    active_mins = len(min_speeds)
    avg_kpm = round(sum(min_speeds) / active_mins, 1) if active_mins > 0 else 0.0
    avg_err = round(sum(min_errors) / active_mins, 1) if active_mins > 0 else 0.0
    avg_mouse_spd = round(sum(mouse_speeds) / len(mouse_speeds), 1) if mouse_speeds else 0.0
    avg_straight = round(sum(mouse_ratios) / len(mouse_ratios), 1) if mouse_ratios else 100.0

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO telemetry_15m (
            user_id, os_type, timestamp_block, active_minutes,
            typing_speed_kpm, error_rate_pct, mouse_speed_px_s, straightness_pct, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.user_id,
            payload.os_type.lower(),
            block_time,
            active_mins,
            avg_kpm,
            avg_err,
            avg_mouse_spd,
            avg_straight,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    export_live_csv()
    return {"status": "success"}

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
    export_live_csv()

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
# DASHBOARD: LISTA DE UTILIZADORES & LIVE STATUS
# ==========================================
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_status(token: Optional[str] = None):
    if token != SECRET_API_TOKEN:
        raise HTTPException(status_code=401, detail="Acesso negado. Usa /dashboard?token=O_TEU_TOKEN")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM telemetry_15m UNION SELECT DISTINCT user_id FROM daily_biometrics")
    all_users = [r[0] for r in cursor.fetchall() if r[0]]

    now_utc = datetime.now(timezone.utc)
    user_rows = []

    for u in all_users:
        cursor.execute(
            "SELECT timestamp_block, os_type, count(id) FROM telemetry_15m WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (u,),
        )
        t_row = cursor.fetchone()
        last_t = t_row[0] if t_row else None
        os_type = t_row[1].upper() if (t_row and t_row[1]) else "--"
        total_blocks = t_row[2] if t_row else 0

        cursor.execute(
            "SELECT recorded_date, device_brand, recovery_score, hrv_rmssd_ms FROM daily_biometrics WHERE user_id = ? ORDER BY recorded_date DESC LIMIT 1",
            (u,),
        )
        b_row = cursor.fetchone()
        bio_info = f"{b_row[1]} ({b_row[0]} | Rec: {b_row[2]}% | HRV: {b_row[3]}ms)" if b_row else "Sem Wearable"

        status_html = '<span style="color:#ef4444; font-weight:bold;">● Sem dados recentes</span>'
        last_seen = "Sem dados"
        if last_t:
            try:
                dt_last = datetime.strptime(last_t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                diff_min = (now_utc - dt_last).total_seconds() / 60.0
                dt_last_local = dt_last.astimezone(LISBON_TZ)
                last_seen = f"há {int(diff_min)}m" if diff_min < 120 else dt_last_local.strftime("%d/%m %H:%M")
                if diff_min <= 16:
                    status_html = '<span style="color:#10b981; font-weight:bold;">● A Receber Dados (Online)</span>'
                elif diff_min <= 60:
                    status_html = '<span style="color:#f59e0b; font-weight:bold;">● Ausente (Pausa Recente)</span>'
            except Exception:
                logger.exception("Falha ao processar last_seen para user %s", u)

        user_rows.append(f"""
            <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 12px 16px; font-weight: 600; color: #38bdf8;">{u}</td>
                <td style="padding: 12px 16px;"><span style="background: #1e293b; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{os_type}</span></td>
                <td style="padding: 12px 16px;">{status_html}</td>
                <td style="padding: 12px 16px; color: #94a3b8;">{last_seen}</td>
                <td style="padding: 12px 16px;">{total_blocks} blocos (15m)</td>
                <td style="padding: 12px 16px; font-size: 12px; color: #94a3b8;">{bio_info}</td>
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
                    <a href="/api/dataset/download-csv?token={token}" class="btn">⬇ CSV</a>
                    <a href="/api/dataset/download-xlsx?token={token}" class="btn">⬇ XLSX</a>
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
    if os.path.exists(CSV_FILE):
        return FileResponse(CSV_FILE, media_type="text/csv", filename="mindsync_live.csv")
    return {"status": "empty", "message": "Ficheiro CSV ainda não criado."}

@app.get("/api/dataset/download-xlsx")
def download_xlsx(token: Optional[str] = None):
    if token != SECRET_API_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido.")

    conn = get_conn()
    t_df = pd.read_sql_query("SELECT * FROM telemetry_15m", conn)
    b_df = pd.read_sql_query("SELECT * FROM daily_biometrics", conn)
    l_df = pd.read_sql_query("SELECT * FROM ground_truth_labels", conn)
    conn.close()

    # Gerado on-demand (não a cada POST) para não penalisar a ingestão.
    # Inclui as 3 tabelas em folhas separadas — para ML normalmente vais querer
    # trabalhar a partir destas tabelas "cruas" (ou do CSV já unido), não só o XLSX.
    with pd.ExcelWriter(XLSX_FILE, engine="openpyxl") as writer:
        t_df.to_excel(writer, sheet_name="telemetry_15m", index=False)
        b_df.to_excel(writer, sheet_name="daily_biometrics", index=False)
        l_df.to_excel(writer, sheet_name="ground_truth_labels", index=False)

    return FileResponse(
        XLSX_FILE,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="mindsync_dataset.xlsx",
    )

@app.get("/")
def health():
    return {"status": "ok"}