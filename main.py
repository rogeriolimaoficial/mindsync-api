from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, Response, FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import sqlite3
import os
from datetime import datetime, timezone, timedelta
import pandas as pd
import io

app = FastAPI(title="MindSync Central Engine - Local Full History")

DB_FILE = "mindsync.db"
SECRET_API_TOKEN = "mindsync_biometrics_master_key_2026"
PORTUGAL_OFFSET = timedelta(hours=1)

# ==========================================
# MODELOS DE DADOS
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

class UniversalTelemetryPayload(BaseModel):
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
    day_strain: Optional[float] = None
    skin_temp_deviation: Optional[float] = None

class GarminPayload(BaseModel):
    user_id: str
    date: str
    body_battery_max: int
    sleep_score: int
    hrv_weekly_avg_ms: float
    resting_heart_rate_bpm: int
    deep_sleep_seconds: int
    rem_sleep_seconds: int
    total_sleep_seconds: int
    stress_level_avg: Optional[int] = None

class AmazfitPayload(BaseModel):
    user_id: str
    date: str
    readiness_score: Optional[int] = None
    sleep_score: int
    hrv_score_ms: Optional[float] = None
    resting_heart_rate_bpm: int
    deep_sleep_minutes: float
    rem_sleep_minutes: float
    total_sleep_minutes: float

class CognitiveLabelPayload(BaseModel):
    user_id: str
    timestamp: Optional[str] = None
    focus_score: int
    mental_fatigue: int
    task_type: Optional[str] = "deep_work"
    notes: Optional[str] = None

# ==========================================
# INICIALIZAÇÃO DA BASE DE DADOS
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyboard_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            os_type TEXT,
            timestamp TEXT,
            duration_s INTEGER,
            total_keys INTEGER,
            correction_keys INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mouse_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            os_type TEXT,
            timestamp TEXT,
            duration_s REAL,
            distance_px REAL,
            straight_distance_px REAL,
            straightness_ratio REAL,
            speed_px_s REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS biometrics_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            recorded_date TEXT,
            device_brand TEXT,
            recovery_score REAL,
            sleep_score REAL,
            hrv_rmssd_ms REAL,
            resting_heart_rate_bpm INTEGER,
            total_sleep_seconds INTEGER,
            deep_sleep_seconds INTEGER,
            rem_sleep_seconds INTEGER,
            daily_strain_score REAL,
            temp_deviation_celsius REAL,
            created_at TEXT,
            UNIQUE(user_id, recorded_date)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cognitive_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT,
            focus_score INTEGER,
            mental_fatigue INTEGER,
            task_type TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/")
def read_root():
    return {"status": "online", "service": "MindSync Local Engine", "dashboard": "/dashboard"}

# ==========================================
# ENDPOINTS DE TELEMETRIA & WEARABLES
# ==========================================
@app.post("/api/telemetry")
def receive_telemetry(payload: UniversalTelemetryPayload):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for kb in payload.keyboard_events:
        cursor.execute("""
            INSERT INTO keyboard_logs (user_id, os_type, timestamp, duration_s, total_keys, correction_keys)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (payload.user_id, payload.os_type.lower(), kb.timestamp, kb.duration_s, kb.total_keys, kb.correction_keys))
        
    for mouse in payload.mouse_events:
        cursor.execute("""
            INSERT INTO mouse_logs (user_id, os_type, timestamp, duration_s, distance_px, straight_distance_px, straightness_ratio, speed_px_s)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (payload.user_id, payload.os_type.lower(), mouse.timestamp, mouse.duration_s, mouse.distance_px, mouse.straight_distance_px, mouse.straightness_ratio, mouse.speed_px_s))
        
    conn.commit()
    conn.close()
    return {"status": "success"}

def save_biometrics(user_id, date_str, brand, rec_score, sleep_score, hrv, rhr, total_s, deep_s, rem_s, strain, temp_dev):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO biometrics_logs (
            user_id, recorded_date, device_brand, recovery_score, sleep_score, 
            hrv_rmssd_ms, resting_heart_rate_bpm, total_sleep_seconds, 
            deep_sleep_seconds, rem_sleep_seconds, daily_strain_score, temp_deviation_celsius, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, recorded_date) DO UPDATE SET
            device_brand=excluded.device_brand,
            recovery_score=excluded.recovery_score,
            sleep_score=excluded.sleep_score,
            hrv_rmssd_ms=excluded.hrv_rmssd_ms,
            resting_heart_rate_bpm=excluded.resting_heart_rate_bpm,
            total_sleep_seconds=excluded.total_sleep_seconds,
            deep_sleep_seconds=excluded.deep_sleep_seconds,
            rem_sleep_seconds=excluded.rem_sleep_seconds,
            daily_strain_score=excluded.daily_strain_score,
            temp_deviation_celsius=excluded.temp_deviation_celsius,
            created_at=excluded.created_at
    """, (user_id, date_str, brand, rec_score, sleep_score, hrv, rhr, total_s, deep_s, rem_s, strain, temp_dev, datetime.now(timezone.utc).isoformat()))[cite: 1]
    conn.commit()
    conn.close()

@app.post("/api/biometrics/apple-watch")
def ingest_apple_watch(payload: AppleWatchPayload, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {SECRET_API_TOKEN}":
        raise HTTPException(status_code=401, detail="Token inválido.")
    norm_hrv = round(payload.hrv_sdnn_ms * 1.15, 1)[cite: 1]
    deep_sec = int(payload.deep_sleep_minutes * 60)[cite: 1]
    rem_sec = int(payload.rem_sleep_minutes * 60)[cite: 1]
    total_sec = deep_sec + rem_sec + int(payload.core_sleep_minutes * 60)[cite: 1]
    sleep_ratio = min(1.0, total_sec / (8.0 * 3600))[cite: 1]
    sleep_score = round(sleep_ratio * 100, 1)[cite: 1]
    hrv_factor = min(1.2, norm_hrv / 60.0)[cite: 1]
    rec_score = round(min(100.0, (hrv_factor * 50.0) + (sleep_ratio * 50.0)), 1)[cite: 1]
    temp_dev = round(payload.temp_wrist_celsius - 36.5, 2) if payload.temp_wrist_celsius else 0.0[cite: 1]
    save_biometrics(payload.user_id, payload.date, "Apple Watch", rec_score, sleep_score, norm_hrv, payload.resting_heart_rate_bpm, total_sec, deep_sec, rem_sec, 0.0, temp_dev)
    return {"status": "success", "calculated_recovery": rec_score}[cite: 1]

@app.post("/api/biometrics/whoop")
def ingest_whoop(payload: WhoopPayload, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {SECRET_API_TOKEN}": raise HTTPException(status_code=401, detail="Token inválido.")
    total_sec = int(payload.total_sleep_minutes * 60)
    save_biometrics(payload.user_id, payload.date, "Whoop", payload.recovery_score_pct, payload.sleep_performance_pct, payload.hrv_rmssd_ms, payload.resting_heart_rate_bpm, total_sec, int(payload.deep_slow_wave_sleep_minutes * 60), int(payload.rem_sleep_minutes * 60), payload.day_strain or 0.0, payload.skin_temp_deviation or 0.0)
    return {"status": "success", "device": "Whoop"}

@app.post("/api/biometrics/garmin")
def ingest_garmin(payload: GarminPayload, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {SECRET_API_TOKEN}": raise HTTPException(status_code=401, detail="Token inválido.")
    save_biometrics(payload.user_id, payload.date, "Garmin", float(payload.body_battery_max), float(payload.sleep_score), payload.hrv_weekly_avg_ms, payload.resting_heart_rate_bpm, payload.total_sleep_seconds, payload.deep_sleep_seconds, payload.rem_sleep_seconds, float(payload.stress_level_avg or 0), 0.0)
    return {"status": "success", "device": "Garmin"}

@app.post("/api/biometrics/amazfit")
def ingest_amazfit(payload: AmazfitPayload, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {SECRET_API_TOKEN}": raise HTTPException(status_code=401, detail="Token inválido.")
    rec = float(payload.readiness_score) if payload.readiness_score else float(payload.sleep_score)
    save_biometrics(payload.user_id, payload.date, "Amazfit", rec, float(payload.sleep_score), payload.hrv_score_ms or 0.0, payload.resting_heart_rate_bpm, int(payload.total_sleep_minutes * 60), int(payload.deep_sleep_minutes * 60), int(payload.rem_sleep_minutes * 60), 0.0, 0.0)
    return {"status": "success", "device": "Amazfit"}

@app.post("/api/labels")
def ingest_label(payload: CognitiveLabelPayload):
    ts = payload.timestamp if payload.timestamp else datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cognitive_labels (user_id, timestamp, focus_score, mental_fatigue, task_type, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (payload.user_id, ts, payload.focus_score, payload.mental_fatigue, payload.task_type, payload.notes))
    conn.commit()
    conn.close()
    return {"status": "success"}

# ==========================================
# DASHBOARD MULTI-UTILIZADOR COM HISTÓRICO TOTAL
# ==========================================
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(user_id: Optional[str] = Query(None)):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT user_id FROM keyboard_logs UNION SELECT DISTINCT user_id FROM biometrics_logs UNION SELECT DISTINCT user_id FROM cognitive_labels")[cite: 1]
        all_users = [row[0] for row in cursor.fetchall() if row[0]][cite: 1]
        
        if not user_id:
            user_id = all_users[0] if all_users else "miguel_user"[cite: 1]
            
        cursor.execute("""
            SELECT recorded_date, device_brand, recovery_score, sleep_score, hrv_rmssd_ms, 
                   resting_heart_rate_bpm, temp_deviation_celsius 
            FROM biometrics_logs 
            WHERE user_id = ?
            ORDER BY recorded_date ASC
        """, (user_id,))
        bio_history = cursor.fetchall()
        
        source_label = "NENHUMA"[cite: 1]
        recovery_val, sleep_val, hrv_val, rhr_val, temp_val = "--", "--", "--", "--", "--"[cite: 1]
        bio_dates, bio_rec, bio_hrv, bio_rhr = [], [], [], [][cite: 1]
        
        if bio_history:
            latest = bio_history[-1][cite: 1]
            source_label = str(latest[1]).upper() if latest[1] else "WEARABLE"
            recovery_val = latest[2] if latest[2] is not None else "--"[cite: 1]
            sleep_val = latest[3] if latest[3] is not None else "--"[cite: 1]
            hrv_val = latest[4] if latest[4] is not None else "--"[cite: 1]
            rhr_val = latest[5] if latest[5] is not None else "--"[cite: 1]
            temp_val = latest[6] if latest[6] is not None else "--"[cite: 1]
            
            for row in bio_history:
                d_str = str(row[0])[cite: 1]
                bio_dates.append(d_str[5:] if len(d_str) >= 10 else d_str)[cite: 1]
                bio_rec.append(row[2] if row[2] is not None else 0)[cite: 1]
                bio_hrv.append(row[4] if row[4] is not None else 0)[cite: 1]
                bio_rhr.append(row[5] if row[5] is not None else 0)[cite: 1]

        cursor.execute("SELECT timestamp, total_keys, correction_keys FROM keyboard_logs WHERE user_id = ? ORDER BY id ASC", (user_id,))[cite: 1]
        kb_rows = cursor.fetchall()[cite: 1]
        cursor.execute("SELECT timestamp, speed_px_s, straightness_ratio FROM mouse_logs WHERE user_id = ? ORDER BY id ASC", (user_id,))[cite: 1]
        mouse_rows = cursor.fetchall()[cite: 1]
        conn.close()[cite: 1]

        def parse_to_portugal(ts_str):
            try:
                clean_ts = ts_str.split("+")[0].replace("Z", "")[cite: 1]
                dt = datetime.fromisoformat(clean_ts)[cite: 1]
                return dt + PORTUGAL_OFFSET[cite: 1]
            except:
                return None[cite: 1]

        minute_kb = {}
        for ts, total, corr in kb_rows:
            dt_local = parse_to_portugal(ts)[cite: 1]
            if dt_local:
                min_key = dt_local.strftime("%Y-%m-%d %H:%M")[cite: 1]
                if min_key not in minute_kb:[cite: 1]
                    minute_kb[min_key] = {"keys": 0, "corr": 0, "active_5s": 0}[cite: 1]
                minute_kb[min_key]["keys"] += total[cite: 1]
                minute_kb[min_key]["corr"] += corr[cite: 1]
                if total > 0:[cite: 1]
                    minute_kb[min_key]["active_5s"] += 1[cite: 1]

        normalized_minutes = {}
        for min_key, data in minute_kb.items():
            n = data["active_5s"][cite: 1]
            if n > 0:[cite: 1]
                normalized_minutes[min_key] = {
                    "keys_per_min": data["keys"] * (12.0 / n),[cite: 1]
                    "error_rate": (data["corr"] / data["keys"]) * 100.0 if data["keys"] > 0 else 0.0[cite: 1]
                }

        kb_15m = {}
        for min_key, norm in normalized_minutes.items():
            dt_min = datetime.strptime(min_key, "%Y-%m-%d %H:%M")[cite: 1]
            b_min = (dt_min.minute // 15) * 15[cite: 1]
            block_dt = dt_min.replace(minute=b_min, second=0)[cite: 1]
            if block_dt not in kb_15m:[cite: 1]
                kb_15m[block_dt] = {"speeds": [], "error_rates": []}[cite: 1]
            kb_15m[block_dt]["speeds"].append(norm["keys_per_min"])[cite: 1]
            kb_15m[block_dt]["error_rates"].append(norm["error_rate"])[cite: 1]

        mouse_15m = {}
        for ts, speed, ratio in mouse_rows:
            dt_local = parse_to_portugal(ts)[cite: 1]
            if dt_local:
                b_min = (dt_local.minute // 15) * 15[cite: 1]
                block_dt = dt_local.replace(minute=b_min, second=0, microsecond=0)[cite: 1]
                if block_dt not in mouse_15m:[cite: 1]
                    mouse_15m[block_dt] = {"speed_sum": 0.0, "ratio_sum": 0.0, "count": 0}[cite: 1]
                mouse_15m[block_dt]["speed_sum"] += speed[cite: 1]
                mouse_15m[block_dt]["ratio_sum"] += ratio[cite: 1]
                mouse_15m[block_dt]["count"] += 1[cite: 1]

        all_dates = list(kb_15m.keys()) + list(mouse_15m.keys())[cite: 1]
        time_blocks = sorted(list(set(all_dates)))

        labels = [b.strftime("%d/%m %H:%M") if len(set([d.date() for d in time_blocks])) > 1 else b.strftime("%H:%M") for b in time_blocks]
        kb_speed_data = [round(sum(kb_15m[b]["speeds"]) / len(kb_15m[b]["speeds"]), 1) if b in kb_15m and kb_15m[b]["speeds"] else 0 for b in time_blocks][cite: 1]
        kb_error_rate_data = [round(sum(kb_15m[b]["error_rates"]) / len(kb_15m[b]["error_rates"]), 1) if b in kb_15m and kb_15m[b]["error_rates"] else 0 for b in time_blocks][cite: 1]
        mouse_speed_data = [round(mouse_15m[b]["speed_sum"] / mouse_15m[b]["count"], 1) if b in mouse_15m and mouse_15m[b]["count"] > 0 else 0 for b in time_blocks][cite: 1]
        mouse_ratio_data = [round((mouse_15m[b]["ratio_sum"] / mouse_15m[b]["count"]) * 100, 1) if b in mouse_15m and mouse_15m[b]["count"] > 0 else 0 for b in time_blocks][cite: 1]

        options_html = "".join([f'<option value="{u}" {"selected" if u == user_id else ""}>{u}</option>' for u in all_users])[cite: 1]
        if not options_html:[cite: 1]
            options_html = f'<option value="{user_id}" selected>{user_id}</option>'[cite: 1]

        html_content = f"""
        <!DOCTYPE html>
        <html lang="pt">
        <head>
            <meta charset="UTF-8">
            <title>MindSync Analytics Central</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 25px; }}
                .container {{ max-width: 1100px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 25px; }}
                .header h1 {{ color: #38bdf8; font-size: 28px; margin-bottom: 4px; }}
                .header p {{ color: #94a3b8; font-size: 14px; margin: 0; }}
                .user-select-bar {{ margin-top: 15px; display: flex; justify-content: center; align-items: center; gap: 12px; }}
                .user-select-bar select {{ background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 6px 14px; border-radius: 8px; font-weight: bold; cursor: pointer; }}
                .btn-export {{ background: #0284c7; color: white; text-decoration: none; padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; }}
                .bio-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }}
                .bio-card {{ background: linear-gradient(145deg, #161f30, #0f172a); border: 1px solid #1e293b; border-radius: 10px; padding: 12px 10px; text-align: center; }}
                .bio-title {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }}
                .bio-val {{ font-size: 22px; font-weight: 700; color: #38bdf8; }}
                .source-tag {{ display: inline-block; background: #0284c7; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
                .section-card {{ background: #161f30; padding: 20px; border-radius: 12px; border: 1px solid #1e293b; margin-bottom: 25px; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
                .card {{ background: #161f30; padding: 20px; border-radius: 12px; border: 1px solid #1e293b; }}
                .card h3, .section-card h3 {{ margin-top: 0; font-size: 14px; font-weight: 600; color: #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>MindSync - Painel & Histórico Completo</h1>
                    <p>Métricas Fisiológicas & Telemetria em Tempo Real</p>
                    
                    <div class="user-select-bar">
                        <label style="color:#94a3b8; font-size:13px;">Utilizador:</label>
                        <select onchange="window.location.href='/dashboard?user_id=' + this.value">
                            {options_html}
                        </select>
                        <span class="source-tag">Fonte: {source_label}</span>
                        <a href="/api/dataset/export" class="btn-export">⬇ Dataset ML (.csv)</a>
                    </div>
                </div>
                
                <div class="bio-grid">
                    <div class="bio-card"><div class="bio-title">Recovery</div><div class="bio-val">{recovery_val}%</div></div>
                    <div class="bio-card"><div class="bio-title">Sono</div><div class="bio-val">{sleep_val}%</div></div>
                    <div class="bio-card"><div class="bio-title">HRV</div><div class="bio-val">{hrv_val} <small style="font-size:11px">ms</small></div></div>
                    <div class="bio-card"><div class="bio-title">RHR</div><div class="bio-val">{rhr_val} <small style="font-size:11px">bpm</small></div></div>
                    <div class="bio-card"><div class="bio-title">Desvio Temp.</div><div class="bio-val">{temp_val} <small style="font-size:11px">°C</small></div></div>
                </div>

                <div class="section-card">
                    <h3>Tendência Fisiológica ({user_id} - Histórico Total)</h3>
                    <canvas id="bioTrendChart" height="90"></canvas>
                </div>

                <div class="grid">
                    <div class="card">
                        <h3>Velocidade Média de Digitação (Teclas / Min)</h3>
                        <canvas id="keysChart" height="130"></canvas>
                    </div>
                    <div class="card">
                        <h3>Taxa de Erro Média (%)</h3>
                        <canvas id="errorChart" height="130"></canvas>
                    </div>
                    <div class="card">
                        <h3>Velocidade Média do Rato (px/s)</h3>
                        <canvas id="speedChart" height="130"></canvas>
                    </div>
                    <div class="card">
                        <h3>Índice de Decisão / Retidão do Rato (%)</h3>
                        <canvas id="decisionChart" height="130"></canvas>
                    </div>
                </div>
            </div>

            <script>
                new Chart(document.getElementById('bioTrendChart'), {{
                    type: 'line',
                    data: {{
                        labels: {bio_dates},
                        datasets: [
                            {{ label: 'Recovery (%)', data: {bio_rec}, borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', tension: 0.3 }},
                            {{ label: 'HRV (ms)', data: {bio_hrv}, borderColor: '#38bdf8', tension: 0.3 }},
                            {{ label: 'RHR (bpm)', data: {bio_rhr}, borderColor: '#f43f5e', tension: 0.3 }}
                        ]
                    }},
                    options: {{ scales: {{ y: {{ beginAtZero: false }} }} }}
                }});

                const labels = {labels};
                const barConfig = {{ maxBarThickness: 20, borderRadius: 4 }};

                new Chart(document.getElementById('keysChart'), {{
                    type: 'bar',
                    data: {{ labels: labels, datasets: [{{ label: 'Teclas/Min', data: {kb_speed_data}, backgroundColor: '#0ea5e9', ...barConfig }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
                }});

                new Chart(document.getElementById('errorChart'), {{
                    type: 'bar',
                    data: {{ labels: labels, datasets: [{{ label: 'Taxa Erro (%)', data: {kb_error_rate_data}, backgroundColor: '#ef4444', ...barConfig }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, max: 100 }} }} }}
                }});

                new Chart(document.getElementById('speedChart'), {{
                    type: 'line',
                    data: {{ labels: labels, datasets: [{{ label: 'px/s', data: {mouse_speed_data}, borderColor: '#8b5cf6', backgroundColor: 'rgba(139, 92, 246, 0.15)', fill: true, tension: 0.3 }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
                }});

                new Chart(document.getElementById('decisionChart'), {{
                    type: 'line',
                    data: {{ labels: labels, datasets: [{{ label: 'Retidão (%)', data: {mouse_ratio_data}, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.15)', fill: true, tension: 0.3 }}] }},
                    options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, max: 100 }} }} }}
                }});
            </script>
        </body>
        </html>
        """
        return html_content
    except Exception as e:
        return HTMLResponse(content=f"<h2 style='color:red;'>Erro: {str(e)}</h2>", status_code=500)[cite: 1]

# ==========================================
# EXPORTAÇÃO DO DATASET MACHINE LEARNING
# ==========================================
@app.get("/api/dataset/export")
def export_training_dataset(lookback_minutes: int = Query(15)):
    conn = sqlite3.connect(DB_FILE)
    labels_df = pd.read_sql_query("SELECT * FROM cognitive_labels", conn)
    kb_df = pd.read_sql_query("SELECT * FROM keyboard_logs", conn)
    mouse_df = pd.read_sql_query("SELECT * FROM mouse_logs", conn)
    bio_df = pd.read_sql_query("SELECT * FROM biometrics_logs", conn)
    conn.close()

    if labels_df.empty:
        return Response(content="user_id,timestamp,os_type,device_brand,total_keys_15m,error_rate_pct,mouse_speed_px_s,mouse_straightness_ratio,recovery_score,hrv_rmssd_ms,resting_heart_rate_bpm,target_focus_score,target_mental_fatigue\n", media_type="text/csv")

    dataset_rows = []
    for _, row in labels_df.iterrows():
        u_id = row['user_id']
        try:
            clean_ts = row['timestamp'].split("+")[0].replace("Z", "")
            t_label = datetime.fromisoformat(clean_ts)
        except Exception:
            continue

        t_start = t_label - timedelta(minutes=lookback_minutes)
        date_str = t_label.strftime("%Y-%m-%d")

        kb_slice = kb_df[kb_df['user_id'] == u_id]
        kb_in = [k for _, k in kb_slice.iterrows() if t_start <= datetime.fromisoformat(k['timestamp'].split("+")[0].replace("Z", "")) <= t_label]
        kb_w_df = pd.DataFrame(kb_in)
        total_keys = kb_w_df['total_keys'].sum() if not kb_w_df.empty else 0
        corr_keys = kb_w_df['correction_keys'].sum() if not kb_w_df.empty else 0
        error_rate = (corr_keys / total_keys * 100.0) if total_keys > 0 else 0.0
        detected_os = kb_w_df['os_type'].values[0] if not kb_w_df.empty else "windows"

        m_slice = mouse_df[mouse_df['user_id'] == u_id]
        m_in = [m for _, m in m_slice.iterrows() if t_start <= datetime.fromisoformat(m['timestamp'].split("+")[0].replace("Z", "")) <= t_label]
        m_w_df = pd.DataFrame(m_in)
        avg_speed = m_w_df['speed_px_s'].mean() if not m_w_df.empty else 0.0
        avg_straightness = m_w_df['straightness_ratio'].mean() if not m_w_df.empty else 1.0

        bio_slice = bio_df[(bio_df['user_id'] == u_id) & (bio_df['recorded_date'] == date_str)]
        rec = bio_slice['recovery_score'].values[0] if not bio_slice.empty else None
        brand = bio_slice['device_brand'].values[0] if not bio_slice.empty else "None"
        hrv = bio_slice['hrv_rmssd_ms'].values[0] if not bio_slice.empty else None
        rhr = bio_slice['resting_heart_rate_bpm'].values[0] if not bio_slice.empty else None

        dataset_rows.append({
            "user_id": u_id,
            "timestamp": row['timestamp'],
            "os_type": detected_os,
            "device_brand": brand,
            "total_keys_15m": total_keys,
            "error_rate_pct": round(error_rate, 2),
            "mouse_speed_px_s": round(avg_speed, 2),
            "mouse_straightness_ratio": round(avg_straightness, 3),
            "recovery_score": rec,
            "hrv_rmssd_ms": hrv,
            "resting_heart_rate_bpm": rhr,
            "target_focus_score": row['focus_score'],
            "target_mental_fatigue": row['mental_fatigue']
        })

    csv_stream = io.StringIO()
    pd.DataFrame(dataset_rows).to_csv(csv_stream, index=False)
    return Response(content=csv_stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=mindsync_ml_dataset.csv"})