import sqlite3
import pandas as pd
import numpy as np

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)

conn = sqlite3.connect("behavior.db")
df = pd.read_sql_query("SELECT * FROM events ORDER BY rowid", conn)
conn.close()

df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")

# ---- TECLADO (janelas de 20s) ----
keyboard_df = df.set_index("datetime")
keypresses = keyboard_df[keyboard_df["event_type"] == "keypress"]
corrections = keyboard_df[keyboard_df["event_type"] == "correction"]

keypress_counts = keypresses.resample("20s").size()
correction_counts = corrections.resample("20s").size()

summary = pd.DataFrame({
    "keypresses": keypress_counts,
    "corrections": correction_counts
}).fillna(0)
summary["total_teclas"] = summary["keypresses"] + summary["corrections"]
summary["taxa_erro_%"] = (summary["corrections"] / summary["total_teclas"] * 100).fillna(0)
summary["teclas_por_min"] = summary["keypresses"] * 3
summary = summary[summary["total_teclas"] > 0]

print("=== TECLADO (por janela de 20s) ===")
print(summary.round(1))
print()

# ---- RATO ----
mouse_x = df[df["event_type"].isin(["mouse_x", "mouse_move_x"])]["value"].values
mouse_y = df[df["event_type"].isin(["mouse_y", "mouse_move_y"])]["value"].values

n = min(len(mouse_x), len(mouse_y))
points = np.column_stack((mouse_x[:n], mouse_y[:n]))

print("=== RATO ===")
print(f"Total de movimentos registados: {n}")

if n > 2:
    deltas = np.diff(points, axis=0)
    distances = np.linalg.norm(deltas, axis=1)
    total_distance = distances.sum()

    straight_line_distance = np.linalg.norm(points[-1] - points[0])

    angles = np.arctan2(deltas[:, 1], deltas[:, 0])
    angle_changes = np.abs(np.diff(angles))
    angle_changes = np.minimum(angle_changes, 2*np.pi - angle_changes)
    avg_direction_change = np.degrees(angle_changes.mean())

    print(f"Distância total percorrida: {total_distance:.0f}px")
    print(f"Distância em linha reta (início-fim): {straight_line_distance:.0f}px")
    print(f"Mudança média de direção entre movimentos: {avg_direction_change:.1f}°")
    print("(quanto mais próximo de 0°, mais 'limpo'/direto; quanto mais perto de 90-180°, mais errático)")