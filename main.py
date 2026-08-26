from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from datetime import datetime, timezone, timedelta

app = FastAPI(title="MindSync Central Multi-User API")

DB_FILE = "mindsync.db"
SECRET_API_TOKEN = "mindsync_biometrics_master_key_2026"
PORTUGAL_OFFSET = timedelta(hours=1)

# --- MODELOS ---
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

class TelemetryPayload(BaseModel):
    user_id: str
    keyboard_events: List[KeyboardEvent]
    mouse_events: List[MouseEvent]

class UniversalBiometricsPayload(BaseModel):
    user_id: str
    source: str
    recorded_date: str
    recovery_score: Optional[float] = None
    sleep_score: Optional[float] = None
    hrv_rmssd_ms: Optional[float] = None
    resting_heart_rate_bpm: Optional[int] = None
    total_sleep_seconds: Optional[int] = None
    deep_sleep_seconds: Optional[int] = None
    rem_sleep_seconds: Optional[int] = None
    sleep_efficiency_pct: Optional[float] = None
    daily_strain_score: Optional[float] = None
    temp_deviation_celsius: Optional[float] = None

class BulkBiometricsPayload(BaseModel):
    user_id: str
    items: List[UniversalBiometricsPayload]

# --- DB INIT ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyboard_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
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
            source TEXT,
            recovery_score REAL,
            sleep_score REAL,
            hrv_rmssd_ms REAL,
            resting_heart_rate_bpm INTEGER,
            total_sleep_seconds INTEGER,
            deep_sleep_seconds INTEGER,
            rem_sleep_seconds INTEGER,
            sleep_efficiency_pct REAL,
            daily_strain_score REAL,
            temp_deviation_celsius REAL,
            created_at TEXT,
            UNIQUE(user_id, recorded_date)
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/")
def read_root():
    return {"status": "online", "service": "MindSync Multi-User Engine", "dashboard": "/dashboard"}

# --- INGESTÃO TELEMETRIA ---
@app.post("/api/telemetry")
def receive_telemetry(payload: TelemetryPayload):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for kb in payload.keyboard_events:
        cursor.execute("INSERT INTO keyboard_logs (user_id, timestamp, duration_s, total_keys, correction_keys) VALUES (?, ?, ?, ?, ?)",
                       (payload.user_id, kb.timestamp, kb.duration_s, kb.total_keys, kb.correction_keys))
    for mouse in payload.mouse_events:
        cursor.execute("INSERT INTO mouse_logs (user_id, timestamp, duration_s, distance_px, straight_distance_px, straightness_ratio, speed_px_s) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (payload.user_id, mouse.timestamp, mouse.duration_s, mouse.distance_px, mouse.straight_distance_px, mouse.straightness_ratio, mouse.speed_px_s))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- INGESTÃO BIOMETRIA ---
@app.post("/api/biometrics/bulk")
def ingest_bulk_biometrics(payload: BulkBiometricsPayload, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {SECRET_API_TOKEN}":
        raise HTTPException(status_code=401, detail="Token de autorização inválido.")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for item in payload.items:
        cursor.execute("""
            INSERT INTO biometrics_logs (
                user_id, recorded_date, source, recovery_score, sleep_score, 
                hrv_rmssd_ms, resting_heart_rate_bpm, total_sleep_seconds, 
                deep_sleep_seconds, rem_sleep_seconds, sleep_efficiency_pct, 
                daily_strain_score, temp_deviation_celsius, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, recorded_date) DO UPDATE SET
                source=excluded.source,
                recovery_score=excluded.recovery_score,
                sleep_score=excluded.sleep_score,
                hrv_rmssd_ms=excluded.hrv_rmssd_ms,
                resting_heart_rate_bpm=excluded.resting_heart_rate_bpm,
                total_sleep_seconds=excluded.total_sleep_seconds,
                deep_sleep_seconds=excluded.deep_sleep_seconds,
                rem_sleep_seconds=excluded.rem_sleep_seconds,
                sleep_efficiency_pct=excluded.sleep_efficiency_pct,
                daily_strain_score=excluded.daily_strain_score,
                temp_deviation_celsius=excluded.temp_deviation_celsius,
                created_at=excluded.created_at
        """, (
            item.user_id, item.recorded_date, item.source, item.recovery_score,
            item.sleep_score, item.hrv_rmssd_ms, item.resting_heart_rate_bpm,
            item.total_sleep_seconds, item.deep_sleep_seconds, item.rem_sleep_seconds,
            item.sleep_efficiency_pct, item.daily_strain_score, item.temp_deviation_celsius,
            datetime.now(timezone.utc).isoformat()
        ))
    conn.commit()
    conn.close()
    return {"status": "success", "registos_inseridos": len(payload.items)}

# --- DASHBOARD MULTI-UTILIZADOR ---
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(user_id: Optional[str] = Query(None)):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 1. Obter lista de todos os utilizadores na base de dados
        cursor.execute("SELECT DISTINCT user_id FROM keyboard_logs UNION SELECT DISTINCT user_id FROM biometrics_logs")
        all_users = [row[0] for row in cursor.fetchall() if row[0]]
        
        if not user_id:
            user_id = all_users[0] if all_users else "miguel_user"
            
        # 2. Biometria do utilizador selecionado
        cursor.execute("""
            SELECT recorded_date, source, recovery_score, sleep_score, hrv_rmssd_ms, 
                   resting_heart_rate_bpm, temp_deviation_celsius 
            FROM biometrics_logs 
            WHERE user_id = ?
            ORDER BY recorded_date ASC LIMIT 14
        """, (user_id,))
        bio_history = cursor.fetchall()
        
        source_label = "NENHUMA"
        recovery_val, sleep_val, hrv_val, rhr_val, temp_val = "--", "--", "--", "--", "--"
        bio_dates, bio_rec, bio_hrv, bio_rhr = [], [], [], []
        
        if bio_history:
            latest = bio_history[-1]
            source_label = str(latest[1]).upper() if latest[1] else "WHOOP"
            recovery_val = latest[2] if latest[2] is not None else "--"
            sleep_val = latest[3] if latest[3] is not None else "--"
            hrv_val = latest[4] if latest[4] is not None else "--"
            rhr_val = latest[5] if latest[5] is not None else "--"
            temp_val = latest[6] if latest[6] is not None else "--"
            
            for row in bio_history:
                d_str = str(row[0])
                bio_dates.append(d_str[5:] if len(d_str) >= 10 else d_str)
                bio_rec.append(row[2] if row[2] is not None else 0)
                bio_hrv.append(row[4] if row[4] is not None else 0)
                bio_rhr.append(row[5] if row[5] is not None else 0)

        # 3. Telemetria do utilizador selecionado
        cursor.execute("SELECT timestamp, total_keys, correction_keys FROM keyboard_logs WHERE user_id = ? ORDER BY id ASC", (user_id,))
        kb_rows = cursor.fetchall()
        cursor.execute("SELECT timestamp, speed_px_s, straightness_ratio FROM mouse_logs WHERE user_id = ? ORDER BY id ASC", (user_id,))
        mouse_rows = cursor.fetchall()
        conn.close()

        def parse_to_portugal(ts_str):
            try:
                clean_ts = ts_str.split("+")[0].replace("Z", "")
                dt = datetime.fromisoformat(clean_ts)
                return dt + PORTUGAL_OFFSET
            except:
                return None

        minute_kb = {}
        for ts, total, corr in kb_rows:
            dt_local = parse_to_portugal(ts)
            if dt_local:
                min_key = dt_local.strftime("%Y-%m-%d %H:%M")
                if min_key not in minute_kb:
                    minute_kb[min_key] = {"keys": 0, "corr": 0, "active_5s": 0}
                minute_kb[min_key]["keys"] += total
                minute_kb[min_key]["corr"] += corr
                if total > 0:
                    minute_kb[min_key]["active_5s"] += 1

        normalized_minutes = {}
        for min_key, data in minute_kb.items():
            n = data["active_5s"]
            if n > 0:
                normalized_minutes[min_key] = {
                    "keys_per_min": data["keys"] * (12.0 / n),
                    "error_rate": (data["corr"] / data["keys"]) * 100.0 if data["keys"] > 0 else 0.0
                }

        kb_15m = {}
        for min_key, norm in normalized_minutes.items():
            dt_min = datetime.strptime(min_key, "%Y-%m-%d %H:%M")
            b_min = (dt_min.minute // 15) * 15
            block_dt = dt_min.replace(minute=b_min, second=0)
            if block_dt not in kb_15m:
                kb_15m[block_dt] = {"speeds": [], "error_rates": []}
            kb_15m[block_dt]["speeds"].append(norm["keys_per_min"])
            kb_15m[block_dt]["error_rates"].append(norm["error_rate"])

        mouse_15m = {}
        for ts, speed, ratio in mouse_rows:
            dt_local = parse_to_portugal(ts)
            if dt_local:
                b_min = (dt_local.minute // 15) * 15
                block_dt = dt_local.replace(minute=b_min, second=0, microsecond=0)
                if block_dt not in mouse_15m:
                    mouse_15m[block_dt] = {"speed_sum": 0.0, "ratio_sum": 0.0, "count": 0}
                mouse_15m[block_dt]["speed_sum"] += speed
                mouse_15m[block_dt]["ratio_sum"] += ratio
                mouse_15m[block_dt]["count"] += 1

        all_dates = list(kb_15m.keys()) + list(mouse_15m.keys())
        time_blocks = []
        if all_dates:
            min_dt = min(all_dates)
            max_dt = max(all_dates)
            curr = min_dt
            while curr <= max_dt:
                time_blocks.append(curr)
                curr += timedelta(minutes=15)

        labels = [b.strftime("%H:%M") for b in time_blocks]
        kb_speed_data = [round(sum(kb_15m[b]["speeds"]) / len(kb_15m[b]["speeds"]), 1) if b in kb_15m and kb_15m[b]["speeds"] else 0 for b in time_blocks]
        kb_error_rate_data = [round(sum(kb_15m[b]["error_rates"]) / len(kb_15m[b]["error_rates"]), 1) if b in kb_15m and kb_15m[b]["error_rates"] else 0 for b in time_blocks]
        mouse_speed_data = [round(mouse_15m[b]["speed_sum"] / mouse_15m[b]["count"], 1) if b in mouse_15m and mouse_15m[b]["count"] > 0 else 0 for b in time_blocks]
        mouse_ratio_data = [round((mouse_15m[b]["ratio_sum"] / mouse_15m[b]["count"]) * 100, 1) if b in mouse_15m and mouse_15m[b]["count"] > 0 else 0 for b in time_blocks]

        # Options HTML do select
        options_html = "".join([f'<option value="{u}" {"selected" if u == user_id else ""}>{u}</option>' for u in all_users])
        if not options_html:
            options_html = f'<option value="{user_id}" selected>{user_id}</option>'

        html_content = f"""
        <!DOCTYPE html>
        <html lang="pt">
        <head>
            <meta charset="UTF-8">
            <title>MindSync Multi-User Dashboard</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 25px; }}
                .container {{ max-width: 1100px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 25px; }}
                .header h1 {{ color: #38bdf8; font-size: 28px; margin-bottom: 4px; }}
                .header p {{ color: #94a3b8; font-size: 14px; margin: 0; }}
                
                .user-select-bar {{ margin-top: 15px; display: flex; justify-content: center; align-items: center; gap: 10px; }}
                .user-select-bar select {{ background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 6px 12px; border-radius: 8px; font-weight: bold; cursor: pointer; }}
                
                .bio-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }}
                .bio-card {{ background: linear-gradient(145deg, #161f30, #0f172a); border: 1px solid #1e293b; border-radius: 10px; padding: 12px 10px; text-align: center; }}
                .bio-title {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }}
                .bio-val {{ font-size: 22px; font-weight: 700; color: #38bdf8; }}
                .source-tag {{ display: inline-block; background: #0284c7; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; margin-bottom: 15px; }}
                
                .section-card {{ background: #161f30; padding: 20px; border-radius: 12px; border: 1px solid #1e293b; margin-bottom: 25px; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
                .card {{ background: #161f30; padding: 20px; border-radius: 12px; border: 1px solid #1e293b; }}
                .card h3, .section-card h3 {{ margin-top: 0; font-size: 14px; font-weight: 600; color: #e2e8f0; }}
                @media (max-width: 850px) {{ .grid {{ grid-template-columns: 1fr; }} .bio-grid {{ grid-template-columns: 1fr 1fr; }} }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>MindSync - Motor de Telemetria & Biometria</h1>
                    <p>Painel Multi-Utilizador • Hora Local (Portugal)</p>
                    
                    <div class="user-select-bar">
                        <label style="color:#94a3b8; font-size:13px;">Utilizador Ativo:</label>
                        <select onchange="window.location.href='/dashboard?user_id=' + this.value">
                            {options_html}
                        </select>
                        <span class="source-tag" style="margin-bottom:0;">Fonte: {source_label}</span>
                    </div>
                </div>
                
                <div class="bio-grid">
                    <div class="bio-card"><div class="bio-title">Recovery Score</div><div class="bio-val">{recovery_val}%</div></div>
                    <div class="bio-card"><div class="bio-title">Qualidade Sono</div><div class="bio-val">{sleep_val}%</div></div>
                    <div class="bio-card"><div class="bio-title">HRV Noturno</div><div class="bio-val">{hrv_val} <small style="font-size:11px">ms</small></div></div>
                    <div class="bio-card"><div class="bio-title">RHR (Repouso)</div><div class="bio-val">{rhr_val} <small style="font-size:11px">bpm</small></div></div>
                    <div class="bio-card"><div class="bio-title">Desvio Temp.</div><div class="bio-val">{temp_val} <small style="font-size:11px">°C</small></div></div>
                </div>

                <div class="section-card">
                    <h3>Tendência Fisiológica ({user_id} - Últimos 14 Dias)</h3>
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
        return HTMLResponse(content=f"<h2 style='color:red;'>Erro: {str(e)}</h2>", status_code=500)