from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import os
from datetime import datetime, timezone

app = FastAPI(title="MindSync Central Ingestion API")

DB_FILE = "mindsync.db"
SECRET_API_TOKEN = "mindsync_biometrics_master_key_2026"

# --- MODELOS DE DADOS TELEMETRIA PC ---
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

# --- MODELO UNIVERSAL DE BIOMETRIA ---
class UniversalBiometricsPayload(BaseModel):
    user_id: str
    source: str  # "oura" | "whoop" | "garmin" | "apple_watch" | "amazfit" | "manual"
    recorded_date: str  # "YYYY-MM-DD"
    recovery_score: Optional[float] = None        # 0 a 100
    sleep_score: Optional[float] = None           # 0 a 100
    hrv_rmssd_ms: Optional[float] = None          # ms
    resting_heart_rate_bpm: Optional[int] = None  # bpm
    total_sleep_seconds: Optional[int] = None     # seg
    deep_sleep_seconds: Optional[int] = None      # seg
    rem_sleep_seconds: Optional[int] = None       # seg
    sleep_efficiency_pct: Optional[float] = None  # %
    daily_strain_score: Optional[float] = None    # 0 a 21
    temp_deviation_celsius: Optional[float] = None

# --- INICIALIZAÇÃO DA BASE DE DADOS ---
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
            recorded_date TEXT UNIQUE,
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
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/")
def read_root():
    return {"status": "online", "service": "MindSync Central Universal Engine v4"}

# --- ROTAS TELEMETRIA DO PC ---
@app.post("/api/telemetry")
def receive_telemetry(payload: TelemetryPayload):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for kb in payload.keyboard_events:
        cursor.execute("""
            INSERT INTO keyboard_logs (user_id, timestamp, duration_s, total_keys, correction_keys)
            VALUES (?, ?, ?, ?, ?)
        """, (payload.user_id, kb.timestamp, kb.duration_s, kb.total_keys, kb.correction_keys))
        
    for mouse in payload.mouse_events:
        cursor.execute("""
            INSERT INTO mouse_logs (user_id, timestamp, duration_s, distance_px, straight_distance_px, straightness_ratio, speed_px_s)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (payload.user_id, mouse.timestamp, mouse.duration_s, mouse.distance_px, mouse.straight_distance_px, mouse.straightness_ratio, mouse.speed_px_s))
        
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- ENDPOINT UNIVERSAL DE BIOMETRIA ---
@app.post("/api/biometrics/ingest")
def ingest_biometrics(payload: UniversalBiometricsPayload, authorization: Optional[str] = Header(None)):
    if authorization != f"Bearer {SECRET_API_TOKEN}":
        raise HTTPException(status_code=401, detail="Token de autorização inválido.")
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO biometrics_logs (
            user_id, recorded_date, source, recovery_score, sleep_score, 
            hrv_rmssd_ms, resting_heart_rate_bpm, total_sleep_seconds, 
            deep_sleep_seconds, rem_sleep_seconds, sleep_efficiency_pct, 
            daily_strain_score, temp_deviation_celsius, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(recorded_date) DO UPDATE SET
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
        payload.user_id, payload.recorded_date, payload.source, payload.recovery_score,
        payload.sleep_score, payload.hrv_rmssd_ms, payload.resting_heart_rate_bpm,
        payload.total_sleep_seconds, payload.deep_sleep_seconds, payload.rem_sleep_seconds,
        payload.sleep_efficiency_pct, payload.daily_strain_score, payload.temp_deviation_celsius,
        datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Biometria [{payload.source.upper()}] registada com sucesso para {payload.recorded_date}."}

# --- ENDPOINTS MOCK PARA TESTES RÁPIDOS ---
@app.get("/api/biometrics/mock/{brand}")
def mock_biometric_data(brand: str, user_id: str = "miguel_user"):
    today = datetime.now().strftime("%Y-%m-%d")
    brand = brand.lower()
    
    if brand == "oura":
        data = UniversalBiometricsPayload(
            user_id=user_id, source="oura", recorded_date=today,
            recovery_score=87.0, sleep_score=84.0, hrv_rmssd_ms=72.0,
            resting_heart_rate_bpm=48, total_sleep_seconds=28200,
            deep_sleep_seconds=5400, rem_sleep_seconds=6900,
            sleep_efficiency_pct=93.0, temp_deviation_celsius=-0.1, daily_strain_score=11.2
        )
    elif brand == "whoop":
        data = UniversalBiometricsPayload(
            user_id=user_id, source="whoop", recorded_date=today,
            recovery_score=91.0, sleep_score=88.0, hrv_rmssd_ms=78.5,
            resting_heart_rate_bpm=46, total_sleep_seconds=29100,
            deep_sleep_seconds=6000, rem_sleep_seconds=7200,
            sleep_efficiency_pct=95.0, daily_strain_score=16.8
        )
    elif brand == "garmin":
        data = UniversalBiometricsPayload(
            user_id=user_id, source="garmin", recorded_date=today,
            recovery_score=82.0, sleep_score=79.0, hrv_rmssd_ms=64.0,
            resting_heart_rate_bpm=50, total_sleep_seconds=26400,
            deep_sleep_seconds=4800, rem_sleep_seconds=5800,
            sleep_efficiency_pct=89.0, daily_strain_score=13.5
        )
    else:
        raise HTTPException(status_code=400, detail="Brand inválida. Usa: oura, whoop ou garmin.")
        
    return ingest_biometrics(data, authorization=f"Bearer {SECRET_API_TOKEN}")

@app.get("/api/debug-status")
def debug_status():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM keyboard_logs")
    kb_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM mouse_logs")
    mouse_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM biometrics_logs")
    bio_count = cursor.fetchone()[0]
    conn.close()
    return {"status": "ok", "teclado_guardado": kb_count, "rato_guardado": mouse_count, "dias_biometria": bio_count}

# --- DASHBOARD CENTRAL ---
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Biometria mais recente
    cursor.execute("SELECT source, recovery_score, sleep_score, hrv_rmssd_ms, resting_heart_rate_bpm, daily_strain_score FROM biometrics_logs ORDER BY recorded_date DESC LIMIT 1")
    bio_row = cursor.fetchone()
    source = bio_row[0].upper() if bio_row else "NENHUMA"
    recovery = bio_row[1] if bio_row else "--"
    sleep = bio_row[2] if bio_row else "--"
    hrv = bio_row[3] if bio_row else "--"
    rhr = bio_row[4] if bio_row else "--"
    strain = bio_row[5] if bio_row else "--"

    # Telemetria do PC
    cursor.execute("SELECT timestamp, total_keys, correction_keys FROM keyboard_logs ORDER BY id ASC")
    kb_rows = cursor.fetchall()
    cursor.execute("SELECT timestamp, speed_px_s, straightness_ratio FROM mouse_logs ORDER BY id ASC")
    mouse_rows = cursor.fetchall()
    conn.close()

    # Normalização ao minuto
    minute_kb = {}
    for ts, total, corr in kb_rows:
        try:
            dt = datetime.fromisoformat(ts)
            min_key = dt.strftime("%Y-%m-%d %H:%M")
            if min_key not in minute_kb:
                minute_kb[min_key] = {"keys": 0, "corr": 0, "active_5s": 0}
            minute_kb[min_key]["keys"] += total
            minute_kb[min_key]["corr"] += corr
            if total > 0:
                minute_kb[min_key]["active_5s"] += 1
        except:
            pass

    normalized_minutes = {}
    for min_key, data in minute_kb.items():
        n = data["active_5s"]
        if n > 0:
            keys_per_min = data["keys"] * (12.0 / n)
            error_rate = (data["corr"] / data["keys"]) * 100.0 if data["keys"] > 0 else 0.0
            normalized_minutes[min_key] = {"keys_per_min": keys_per_min, "error_rate": error_rate}

    def get_15m_block(ts_str):
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
            b_min = (dt.minute // 15) * 15
            return dt.strftime(f"%H:{b_min:02d}")
        except:
            return "N/A"

    kb_15m = {}
    for min_key, norm in normalized_minutes.items():
        b = get_15m_block(min_key)
        if b not in kb_15m:
            kb_15m[b] = {"speeds": [], "error_rates": []}
        kb_15m[b]["speeds"].append(norm["keys_per_min"])
        kb_15m[b]["error_rates"].append(norm["error_rate"])

    def round_to_15m_mouse(ts_str):
        try:
            dt = datetime.fromisoformat(ts_str)
            minute = (dt.minute // 15) * 15
            return dt.strftime(f"%H:{minute:02d}")
        except:
            return "N/A"

    mouse_15m = {}
    for ts, speed, ratio in mouse_rows:
        b = round_to_15m_mouse(ts)
        if b not in mouse_15m:
            mouse_15m[b] = {"speed_sum": 0.0, "ratio_sum": 0.0, "count": 0}
        mouse_15m[b]["speed_sum"] += speed
        mouse_15m[b]["ratio_sum"] += ratio
        mouse_15m[b]["count"] += 1

    all_buckets = sorted(list(set(list(kb_15m.keys()) + list(mouse_15m.keys()))))
    
    kb_speed_data = [round(sum(kb_15m[b]["speeds"]) / len(kb_15m[b]["speeds"]), 1) if b in kb_15m and kb_15m[b]["speeds"] else 0 for b in all_buckets]
    kb_error_rate_data = [round(sum(kb_15m[b]["error_rates"]) / len(kb_15m[b]["error_rates"]), 1) if b in kb_15m and kb_15m[b]["error_rates"] else 0 for b in all_buckets]
    mouse_speed_data = [round(mouse_15m[b]["speed_sum"] / mouse_15m[b]["count"], 1) if b in mouse_15m and mouse_15m[b]["count"] > 0 else 0 for b in all_buckets]
    mouse_ratio_data = [round((mouse_15m[b]["ratio_sum"] / mouse_15m[b]["count"]) * 100, 1) if b in mouse_15m and mouse_15m[b]["count"] > 0 else 0 for b in all_buckets]

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>MindSync Universal Engine</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 25px; }}
            .container {{ max-width: 1100px; margin: 0 auto; }}
            .header {{ text-align: center; margin-bottom: 25px; }}
            .header h1 {{ color: #38bdf8; font-size: 28px; margin-bottom: 4px; }}
            .header p {{ color: #94a3b8; font-size: 14px; margin: 0; }}
            
            .bio-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 25px; }}
            .bio-card {{ background: linear-gradient(145deg, #161f30, #0f172a); border: 1px solid #1e293b; border-radius: 10px; padding: 14px 10px; text-align: center; }}
            .bio-title {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 4px; }}
            .bio-val {{ font-size: 22px; font-weight: 700; color: #38bdf8; }}
            .source-tag {{ display: inline-block; background: #0284c7; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; margin-bottom: 15px; }}
            
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            .card {{ background: #161f30; padding: 20px; border-radius: 12px; border: 1px solid #1e293b; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
            .card h3 {{ margin-top: 0; font-size: 14px; font-weight: 600; color: #e2e8f0; }}
            @media (max-width: 850px) {{ .grid {{ grid-template-columns: 1fr; }} .bio-grid {{ grid-template-columns: 1fr 1fr 1fr; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MindSync - Motor Central de Foco & Biometria</h1>
                <p>Funil Agnóstico de Telemetria e Wearables</p>
                <div style="margin-top: 10px;"><span class="source-tag">Fonte Ativa: {source}</span></div>
            </div>
            
            <!-- Linha de Biometria Universal -->
            <div class="bio-grid">
                <div class="bio-card">
                    <div class="bio-title">Recuperação / Readiness</div>
                    <div class="bio-val">{recovery}</div>
                </div>
                <div class="bio-card">
                    <div class="bio-title">Qualidade Sono</div>
                    <div class="bio-val">{sleep}</div>
                </div>
                <div class="bio-card">
                    <div class="bio-title">HRV Noturno</div>
                    <div class="bio-val">{hrv} <small style="font-size:12px">ms</small></div>
                </div>
                <div class="bio-card">
                    <div class="bio-title">RHR (Repouso)</div>
                    <div class="bio-val">{rhr} <small style="font-size:12px">bpm</small></div>
                </div>
                <div class="bio-card">
                    <div class="bio-title">Carga / Strain</div>
                    <div class="bio-val">{strain}</div>
                </div>
            </div>

            <!-- Gráficos de Telemetria -->
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
            const labels = {all_buckets};
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