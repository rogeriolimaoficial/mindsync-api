from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
import sqlite3
import os
from datetime import datetime

app = FastAPI(title="MindSync Central API")

DB_FILE = "mindsync.db"

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
    conn.commit()
    conn.close()

init_db()

@app.get("/")
def read_root():
    return {"status": "online", "service": "MindSync Central API v2"}

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

@app.get("/api/debug-status")
def debug_status():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM keyboard_logs")
    kb_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM mouse_logs")
    mouse_count = cursor.fetchone()[0]
    conn.close()
    return {"status": "ok", "teclado_guardado": kb_count, "rato_guardado": mouse_count}

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, total_keys, correction_keys FROM keyboard_logs ORDER BY id ASC")
    kb_rows = cursor.fetchall()
    cursor.execute("SELECT timestamp, speed_px_s, straightness_ratio FROM mouse_logs ORDER BY id ASC")
    mouse_rows = cursor.fetchall()
    conn.close()

    def round_to_15m(ts_str):
        try:
            dt = datetime.fromisoformat(ts_str)
            minute = (dt.minute // 15) * 15
            return dt.strftime(f"%H:{minute:02d}")
        except:
            return "N/A"

    kb_buckets = {}
    for ts, total, corr in kb_rows:
        b = round_to_15m(ts)
        if b not in kb_buckets:
            kb_buckets[b] = {"keys": 0, "corr": 0, "active_samples": 0}
        kb_buckets[b]["keys"] += total
        kb_buckets[b]["corr"] += corr
        if total > 0:
            kb_buckets[b]["active_samples"] += 1

    mouse_buckets = {}
    for ts, speed, ratio in mouse_rows:
        b = round_to_15m(ts)
        if b not in mouse_buckets:
            mouse_buckets[b] = {"speed_sum": 0.0, "ratio_sum": 0.0, "count": 0}
        mouse_buckets[b]["speed_sum"] += speed
        mouse_buckets[b]["ratio_sum"] += ratio
        mouse_buckets[b]["count"] += 1

    all_buckets = sorted(list(set(list(kb_buckets.keys()) + list(mouse_buckets.keys()))))
    
    # Métricas Teclado
    kb_keys_data = [kb_buckets.get(b, {}).get("keys", 0) for b in all_buckets]
    kb_error_rate = []
    for b in all_buckets:
        tot = kb_buckets.get(b, {}).get("keys", 0)
        corr = kb_buckets.get(b, {}).get("corr", 0)
        rate = round((corr / tot) * 100, 1) if tot > 0 else 0.0
        kb_error_rate.append(rate)

    # Métricas Rato
    mouse_speed_data = [round(mouse_buckets[b]["speed_sum"] / mouse_buckets[b]["count"], 1) if b in mouse_buckets and mouse_buckets[b]["count"] > 0 else 0 for b in all_buckets]
    mouse_ratio_data = [round((mouse_buckets[b]["ratio_sum"] / mouse_buckets[b]["count"]) * 100, 1) if b in mouse_buckets and mouse_buckets[b]["count"] > 0 else 0 for b in all_buckets]

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>MindSync Analytics</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 30px 20px; }}
            .container {{ max-width: 1100px; margin: 0 auto; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .header h1 {{ color: #38bdf8; font-size: 28px; margin-bottom: 6px; }}
            .header p {{ color: #94a3b8; font-size: 14px; margin: 0; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            .card {{ background: #161f30; padding: 20px; border-radius: 12px; border: 1px solid #1e293b; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }}
            .card h3 {{ margin-top: 0; font-size: 15px; font-weight: 600; color: #e2e8f0; }}
            @media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MindSync - Painel de Telemetria de Foco</h1>
                <p>Métricas agregadas em intervalos de 15 minutos</p>
            </div>
            
            <div class="grid">
                <!-- Gráfico 1: Volume de Teclas -->
                <div class="card">
                    <h3>Volume de Digitação (Total Teclas)</h3>
                    <canvas id="keysChart" height="130"></canvas>
                </div>

                <!-- Gráfico 2: Taxa de Erro -->
                <div class="card">
                    <h3>Taxa de Erro / Correções (%)</h3>
                    <canvas id="errorChart" height="130"></canvas>
                </div>

                <!-- Gráfico 3: Velocidade do Rato -->
                <div class="card">
                    <h3>Velocidade Média do Rato (px/s)</h3>
                    <canvas id="speedChart" height="130"></canvas>
                </div>

                <!-- Gráfico 4: Retidão e Decisão -->
                <div class="card">
                    <h3>Índice de Decisão / Retidão do Rato (%)</h3>
                    <canvas id="decisionChart" height="130"></canvas>
                </div>
            </div>
        </div>

        <script>
            const labels = {all_buckets};
            const barConfig = {{ maxBarThickness: 18, borderRadius: 4 }};

            // 1. Teclas
            new Chart(document.getElementById('keysChart'), {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [{{ label: 'Teclas', data: {kb_keys_data}, backgroundColor: '#0284c7', ...barConfig }}]
                }},
                options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
            }});

            // 2. Taxa de Erro
            new Chart(document.getElementById('errorChart'), {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [{{ label: 'Taxa Erro (%)', data: {kb_error_rate}, backgroundColor: '#ef4444', ...barConfig }}]
                }},
                options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, max: 100 }} }} }}
            }});

            // 3. Velocidade Rato
            new Chart(document.getElementById('speedChart'), {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{ label: 'px/s', data: {mouse_speed_data}, borderColor: '#8b5cf6', backgroundColor: 'rgba(139, 92, 246, 0.15)', fill: true, tension: 0.3 }}]
                }},
                options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
            }});

            // 4. Retidão Rato
            new Chart(document.getElementById('decisionChart'), {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{ label: 'Retidão (%)', data: {mouse_ratio_data}, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.15)', fill: true, tension: 0.3 }}]
                }},
                options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, max: 100 }} }} }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content