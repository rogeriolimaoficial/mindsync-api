from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
import sqlite3
import os
from datetime import datetime, timezone

app = FastAPI(title="MindSync Central API")

DB_FILE = "mindsync.db"

# --- ESTRUTURA DOS DADOS ---
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

# --- BASE DE DADOS ---
def init_db():
    # Como mudámos a estrutura, apagamos a DB antiga (localmente) se existir
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except:
            pass
            
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

# --- ROTAS DA API ---
@app.get("/")
def read_root():
    return {"status": "online", "service": "MindSync Central API v2"}

@app.post("/api/telemetry")
def receive_telemetry(payload: TelemetryPayload):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Guardar Teclado
    for kb in payload.keyboard_events:
        cursor.execute("""
            INSERT INTO keyboard_logs (user_id, timestamp, duration_s, total_keys, correction_keys)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (payload.user_id, kb.timestamp, kb.duration_s, kb.total_keys, kb.correction_keys))
        
    # Guardar Rato
    for mouse in payload.mouse_events:
        cursor.execute("""
            INSERT INTO mouse_logs (user_id, timestamp, duration_s, distance_px, straight_distance_px, straightness_ratio, speed_px_s)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

# --- DASHBOARD VISUAL (HTML + Chart.js) ---
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    # Extrai os últimos 100 blocos de teclado e rato para o gráfico
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT timestamp, total_keys, correction_keys FROM keyboard_logs ORDER BY id DESC LIMIT 50")
    kb_data = cursor.fetchall()[::-1] # Inverter para ordem cronológica
    
    cursor.execute("SELECT timestamp, speed_px_s, straightness_ratio FROM mouse_logs ORDER BY id DESC LIMIT 50")
    mouse_data = cursor.fetchall()[::-1]
    conn.close()

    # Prepara os dados para o Javascript
    kb_labels = [row[0][11:19] for row in kb_data]
    kb_keys = [row[1] for row in kb_data]
    
    mouse_labels = [row[0][11:19] for row in mouse_data]
    mouse_speed = [row[1] for row in mouse_data]
    mouse_straight = [row[2] * 100 for row in mouse_data] # Passar a %

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <title>MindSync Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .card {{ background: #1e293b; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            h1 {{ text-align: center; color: #38bdf8; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>MindSync - Análise de Fluxo de Trabalho</h1>
            
            <div class="card">
                <h3>Teclado: Produtividade vs Correções (Blocos 5s)</h3>
                <canvas id="kbChart" height="80"></canvas>
            </div>

            <div class="card">
                <h3>Rato: Velocidade e Decisão (Trajetórias)</h3>
                <canvas id="mouseChart" height="80"></canvas>
            </div>
        </div>

        <script>
            // Gráfico Teclado
            new Chart(document.getElementById('kbChart'), {{
                type: 'bar',
                data: {{
                    labels: {kb_labels},
                    datasets: [
                        {{ label: 'Teclas Úteis', data: {kb_keys}, backgroundColor: '#38bdf8' }}
                    ]
                }},
                options: {{ scales: {{ y: {{ beginAtZero: true }} }} }}
            }});

            // Gráfico Rato
            new Chart(document.getElementById('mouseChart'), {{
                type: 'line',
                data: {{
                    labels: {mouse_labels},
                    datasets: [
                        {{ label: 'Velocidade (px/s)', data: {mouse_speed}, borderColor: '#a855f7', tension: 0.3 }},
                        {{ label: 'Retidão (%)', data: {mouse_straight}, borderColor: '#4ade80', tension: 0.3 }}
                    ]
                }},
                options: {{ scales: {{ y: {{ beginAtZero: true }} }} }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content