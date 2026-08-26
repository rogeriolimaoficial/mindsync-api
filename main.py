from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
import sqlite3
import os
from datetime import datetime, timezone

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
    return {"status": "success", "kb_events": len(payload.keyboard_events), "mouse_events": len(payload.mouse_events)}

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
    
    # Busca dados de teclado
    cursor.execute("SELECT timestamp, total_keys, correction_keys FROM keyboard_logs ORDER BY id ASC")
    kb_rows = cursor.fetchall()
    
    # Busca dados de rato
    cursor.execute("SELECT timestamp, speed_px_s, straightness_ratio FROM mouse_logs ORDER BY id ASC")
    mouse_rows = cursor.fetchall()
    conn.close()

    # Função auxiliar para arredondar timestamps para blocos de 15 minutos
    def round_to_15m(ts_str):
        try:
            dt = datetime.fromisoformat(ts_str)
            minute = (dt.minute // 15) * 15
            return dt.strftime(f"%H:{minute:02d}")
        except:
            return "N/A"

    # Agregação Teclado em blocos de 15m
    kb_buckets = {}
    for ts, total, corr in kb_rows:
        bucket = round_to_15m(ts)
        if bucket not in kb_buckets:
            kb_buckets[bucket] = {"keys": 0, "corr": 0, "samples": 0}
        kb_buckets[bucket]["keys"] += total
        kb_buckets[bucket]["corr"] += corr
        kb_buckets[bucket]["samples"] += 1

    # Agregação Rato em blocos de 15m
    mouse_buckets = {}
    for ts, speed, ratio in mouse_rows:
        bucket = round_to_15m(ts)
        if bucket not in mouse_buckets:
            mouse_buckets[bucket] = {"speed_sum": 0.0, "ratio_sum": 0.0, "count": 0}
        mouse_buckets[bucket]["speed_sum"] += speed
        mouse_buckets[bucket]["ratio_sum"] += ratio
        mouse_buckets[bucket]["count"] += 1

    all_buckets = sorted(list(set(list(kb_buckets.keys()) + list(mouse_buckets.keys()))))
    
    kb_labels = all_buckets
    kb_keys_data = [kb_buckets.get(b, {}).get("keys", 0) for b in all_buckets]
    kb_corr_data = [kb_buckets.get(b, {}).get("corr", 0) for b in all_buckets]
    
    mouse_speed_data = [round(mouse_buckets[b]["speed_sum"] / mouse_buckets[b]["count"], 2) if b in mouse_buckets and mouse_buckets[b]["count"] > 0 else 0 for b in all_buckets]
    mouse_ratio_data = [round((mouse_buckets[b]["ratio_sum"] / mouse_buckets[b]["count"]) * 100, 1) if b in mouse_buckets and mouse_buckets[b]["count"] > 0 else 0 for b in all_buckets]

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>MindSync Dashboard - Blocos de 15 Minutos</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0b0f19; color: #f8fafc; padding: 25px; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .card {{ background: #161f30; padding: 25px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.4); }}
            h1 {{ text-align: center; color: #38bdf8; font-size: 26px; }}
            .sub {{ text-align: center; color: #94a3b8; font-size: 14px; margin-top: -10px; margin-bottom: 25px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>MindSync - Métricas de Foco e Produtividade</h1>
            <div class="sub">Agregação em Janelas de 15 Minutos</div>
            
            <div class="card">
                <h3>Teclado: Produção Ativa vs Correções (Blocos 15m)</h3>
                <canvas id="kbChart" height="90"></canvas>
            </div>

            <div class="card">
                <h3>Rato: Velocidade Média e Decisão/Retidão (Blocos 15m)</h3>
                <canvas id="mouseChart" height="90"></canvas>
            </div>
        </div>

        <script>
            new Chart(document.getElementById('kbChart'), {{
                type: 'bar',
                data: {{
                    labels: {kb_labels},
                    datasets: [
                        {{ label: 'Teclas Úteis', data: {kb_keys_data}, backgroundColor: '#0ea5e9' }},
                        {{ label: 'Correções (Backspace/Del)', data: {kb_corr_data}, backgroundColor: '#ef4444' }}
                    ]
                }},
                options: {{ scales: {{ y: {{ beginAtZero: true }} }} }}
            }});

            new Chart(document.getElementById('mouseChart'), {{
                type: 'line',
                data: {{
                    labels: {kb_labels},
                    datasets: [
                        {{ label: 'Velocidade Média (px/s)', data: {mouse_speed_data}, borderColor: '#a855f7', backgroundColor: '#a855f7', tension: 0.2 }},
                        {{ label: 'Retidão/Decisão (%)', data: {mouse_ratio_data}, borderColor: '#22c55e', backgroundColor: '#22c55e', tension: 0.2 }}
                    ]
                }},
                options: {{ scales: {{ y: {{ beginAtZero: true }} }} }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content