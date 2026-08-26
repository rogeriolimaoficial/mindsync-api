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

    # 1. Agrupar Teclado primeiro ao MINUTO
    minute_kb = {}
    for ts, total, corr in kb_rows:
        try:
            dt = datetime.fromisoformat(ts)
            min_key = dt.strftime("%Y-%m-%d %H:%M")
            if min_key not in minute_kb:
                minute_kb[min_key] = {"keys": 0, "corr": 0, "active_5s_blocks": 0}
            minute_kb[min_key]["keys"] += total
            minute_kb[min_key]["corr"] += corr
            if total > 0:
                minute_kb[min_key]["active_5s_blocks"] += 1
        except:
            pass

    # Calcular a velocidade normalizada por minuto (Teclas/Minuto)
    normalized_minutes = {}
    for min_key, data in minute_kb.items():
        n = data["active_5s_blocks"]
        if n > 0:
            # Extrapolação baseada nos blocos de 5s ativos (fator 12 / N)
            keys_per_min = data["keys"] * (12.0 / n)
            error_rate = (data["corr"] / data["keys"]) * 100.0 if data["keys"] > 0 else 0.0
            normalized_minutes[min_key] = {
                "keys_per_min": keys_per_min,
                "error_rate": error_rate
            }

    # 2. Agrupar em Blocos de 15 Minutos
    def get_15m_block(ts_str):
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
            b_min = (dt.minute // 15) * 15
            return dt.strftime(f"%H:{b_min:02d}")
        except:
            return "N/A"

    kb_15m_buckets = {}
    for min_key, norm_data in normalized_minutes.items():
        b = get_15m_block(min_key)
        if b not in kb_15m_buckets:
            kb_15m_buckets[b] = {"speeds": [], "error_rates": []}
        kb_15m_buckets[b]["speeds"].append(norm_data["keys_per_min"])
        kb_15m_buckets[b]["error_rates"].append(norm_data["error_rate"])

    # Agregação Rato em blocos de 15m
    def round_to_15m_mouse(ts_str):
        try:
            dt = datetime.fromisoformat(ts_str)
            minute = (dt.minute // 15) * 15
            return dt.strftime(f"%H:{minute:02d}")
        except:
            return "N/A"

    mouse_buckets = {}
    for ts, speed, ratio in mouse_rows:
        b = round_to_15m_mouse(ts)
        if b not in mouse_buckets:
            mouse_buckets[b] = {"speed_sum": 0.0, "ratio_sum": 0.0, "count": 0}
        mouse_buckets[b]["speed_sum"] += speed
        mouse_buckets[b]["ratio_sum"] += ratio
        mouse_buckets[b]["count"] += 1

    all_buckets = sorted(list(set(list(kb_15m_buckets.keys()) + list(mouse_buckets.keys()))))
    
    # Médias Finais por Bloco de 15 Minutos
    kb_speed_data = [
        round(sum(kb_15m_buckets[b]["speeds"]) / len(kb_15m_buckets[b]["speeds"]), 1)
        if b in kb_15m_buckets and kb_15m_buckets[b]["speeds"] else 0
        for b in all_buckets
    ]
    
    kb_error_rate_data = [
        round(sum(kb_15m_buckets[b]["error_rates"]) / len(kb_15m_buckets[b]["error_rates"]), 1)
        if b in kb_15m_buckets and kb_15m_buckets[b]["error_rates"] else 0
        for b in all_buckets
    ]

    mouse_speed_data = [
        round(mouse_buckets[b]["speed_sum"] / mouse_buckets[b]["count"], 1)
        if b in mouse_buckets and mouse_buckets[b]["count"] > 0 else 0
        for b in all_buckets
    ]
    
    mouse_ratio_data = [
        round((mouse_buckets[b]["ratio_sum"] / mouse_buckets[b]["count"]) * 100, 1)
        if b in mouse_buckets and mouse_buckets[b]["count"] > 0 else 0
        for b in all_buckets
    ]

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
                <p>Médias Normalizadas em Intervalos de 15 Minutos</p>
            </div>
            
            <div class="grid">
                <!-- Gráfico 1: Velocidade de Escrita (Média Teclas/Min) -->
                <div class="card">
                    <h3>Velocidade Média de Digitação (Teclas / Min)</h3>
                    <canvas id="keysChart" height="130"></canvas>
                </div>

                <!-- Gráfico 2: Taxa de Erro Média -->
                <div class="card">
                    <h3>Taxa de Erro Média (%)</h3>
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
            const barConfig = {{ maxBarThickness: 22, borderRadius: 4 }};

            // 1. Teclas / Minuto
            new Chart(document.getElementById('keysChart'), {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [{{ label: 'Teclas/Min', data: {kb_speed_data}, backgroundColor: '#0ea5e9', ...barConfig }}]
                }},
                options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
            }});

            // 2. Taxa de Erro
            new Chart(document.getElementById('errorChart'), {{
                type: 'bar',
                data: {{
                    labels: labels,
                    datasets: [{{ label: 'Taxa Erro (%)', data: {kb_error_rate_data}, backgroundColor: '#ef4444', ...barConfig }}]
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