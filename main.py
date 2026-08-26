import sqlite3
import time
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="MindSync Central API",
    description="API central para agregação de telemetria e biometria.",
    version="1.0.0"
)

# Permitir pedidos de qualquer frontend/dashboard (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "mindsync.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pc_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp REAL,
            event_type TEXT,
            value REAL,
            received_at REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            user_id TEXT,
            message TEXT,
            event_count INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Modelos Pydantic ---
class EventItem(BaseModel):
    timestamp: float
    event_type: str
    value: float

class TelemetryBatch(BaseModel):
    user_id: str
    batch_timestamp: Optional[float] = None
    events: List[EventItem]

# --- Endpoints ---

@app.get("/")
def home():
    return {
        "status": "online",
        "service": "MindSync Central API",
        "time": datetime.utcnow().isoformat()
    }

# Recebe os dados de hora a hora do teu tracker.py
@app.post("/api/telemetry")
def receive_telemetry(batch: TelemetryBatch):
    if not batch.events:
        return {"status": "ignored", "message": "Lote vazio."}

    now = time.time()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        records = [
            (batch.user_id, e.timestamp, e.event_type, e.value, now)
            for e in batch.events
        ]
        cursor.executemany(
            "INSERT INTO pc_events (user_id, timestamp, event_type, value, received_at) VALUES (?, ?, ?, ?, ?)",
            records
        )

        # Regista nos logs internos para poderes consultar facilmente
        cursor.execute(
            "INSERT INTO api_logs (timestamp, user_id, message, event_count) VALUES (?, ?, ?, ?)",
            (now, batch.user_id, "Lote recebido com sucesso", len(records))
        )
        conn.commit()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Recebidos {len(records)} eventos de {batch.user_id}")
        return {
            "status": "success",
            "received_count": len(records),
            "timestamp": now
        }
    except Exception as e:
        conn.rollback()
        print(f"[ERRO] Falha ao guardar dados: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Endpoint para verificares o estado e os últimos envios recebidos (DEBUG/TESTE)
@app.get("/api/debug-status")
def debug_status():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pc_events")
    total_events = cursor.fetchone()[0]

    cursor.execute("SELECT timestamp, user_id, message, event_count FROM api_logs ORDER BY id DESC LIMIT 10")
    logs = [
        {
            "time": datetime.utcfromtimestamp(row[0]).strftime('%Y-%m-%d %H:%M:%S UTC'),
            "user_id": row[1],
            "message": row[2],
            "event_count": row[3]
        }
        for row in cursor.fetchall()
    ]
    conn.close()

    return {
        "database_status": "ok",
        "total_events_stored": total_events,
        "recent_logs": logs
    }