"""Mostra os blocos de 15 min de um utilizador (por defeito o último dia com dados).

Uso: python view_data.py [user_id] [AAAA-MM-DD]
"""
import sqlite3
import sys

import pandas as pd

from features import build_blocks

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)

conn = sqlite3.connect("mindsync.db")
blocks = build_blocks(conn)
conn.close()

if blocks.empty:
    sys.exit("Sem dados em windows_5s.")

user = sys.argv[1] if len(sys.argv) > 1 else blocks["user_id"].iloc[-1]
blocks = blocks[blocks["user_id"] == user]
day = sys.argv[2] if len(sys.argv) > 2 else blocks["local_date"].iloc[-1]
blocks = blocks[blocks["local_date"] == day]

cols = [
    "timestamp_block", "active_pct", "reliable", "typing_kpm", "corr_eps_per_min",
    "pauses_per_min", "iki_std_ms", "mouse_speed_px_s", "straightness_pct",
    "dir_changes_per_1000px",
]
print(f"=== {user} | {day} (blocos de 15 min, UTC) ===")
print(blocks[cols].round(1).to_string(index=False))
print("\nreliable=0 significa menos de 2 min de escrita ativa no bloco.")
