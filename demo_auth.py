import requests
from datetime import datetime

API_URL = "https://mindsync-api.onrender.com/api/biometrics/bulk"
MASTER_TOKEN = "mindsync_biometrics_master_key_2026"
USER_ID = "miguel_user"
TODAY = datetime.now().strftime("%Y-%m-%d")

# Payload de teste biométrico
payload = {
    "user_id": USER_ID,
    "items": [{
        "user_id": USER_ID,
        "source": "whoop",
        "recorded_date": TODAY,
        "recovery_score": 94.0,           # 94% de recuperação
        "sleep_score": 91.0,              # 91% de sono
        "hrv_rmssd_ms": 82.5,             # 82.5 ms
        "resting_heart_rate_bpm": 44,     # 44 bpm
        "temp_deviation_celsius": -0.3,   # -0.3 °C
        "daily_strain_score": 10.5
    }]
}

print("=" * 60)
print("  TESTE DE AUTENTICAÇÃO E INGESTÃO DE DADOS (MINDSYNC API)")
print("=" * 60)

# --- 1. TENTATIVA COM TOKEN INVÁLIDO ---
print("\n[1] A enviar pedido com Token FALSO ('Bearer token_invalido_123')...")
headers_bad = {"Authorization": "Bearer token_invalido_123", "Content-Type": "application/json"}
res_bad = requests.post(API_URL, json=payload, headers=headers_bad)

print(f"    -> Status HTTP: {res_bad.status_code} (Esperado: 401)")
print(f"    -> Resposta da API: {res_bad.json()}")

if res_bad.status_code == 401:
    print("    -> [OK] Segurança validada: Pedido não autorizado foi bloqueado com sucesso!")

# --- 2. TENTATIVA COM TOKEN CORRETO ---
print("\n[2] A enviar pedido com Token VÁLIDO ('Bearer mindsync_biometrics_master_key_2026')...")
headers_good = {"Authorization": f"Bearer {MASTER_TOKEN}", "Content-Type": "application/json"}
res_good = requests.post(API_URL, json=payload, headers=headers_good)

print(f"    -> Status HTTP: {res_good.status_code} (Esperado: 200)")
print(f"    -> Resposta da API: {res_good.json()}")

if res_good.status_code == 200:
    print("    -> [OK] Autenticado com sucesso: Dados gravados na base de dados!")

print("\n" + "=" * 60)
print("Abre o teu browser em: https://mindsync-api.onrender.com/dashboard")
print("=" * 60)