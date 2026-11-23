"""Troca o código de autorização da Oura por tokens e guarda-os em token.json (ignorado pelo git).

Uso: python get_token.py <CODIGO>   (ou corre sem argumentos e cola o código)
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID").strip()
CLIENT_SECRET = os.getenv("CLIENT_SECRET").strip()
REDIRECT_URI = os.getenv("REDIRECT_URI").strip()

code = sys.argv[1] if len(sys.argv) > 1 else input("Código de autorização: ").strip()

response = requests.post(
    "https://api.ouraring.com/oauth/token",
    data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
    auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
)

print(response.status_code)
if response.status_code == 200:
    with open("token.json", "w") as f:
        json.dump(response.json(), f, indent=2)
    print("Tokens guardados em token.json")
else:
    print(response.text)
