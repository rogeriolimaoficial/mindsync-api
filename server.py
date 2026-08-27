import os
import json
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Não veio nenhum código, algo correu mal na autorização."

    response = requests.post(
        "https://api.ouraring.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )

    if response.status_code == 200:
        with open("token.json", "w") as f:
            json.dump(response.json(), f, indent=2)
        return "Autorizado com sucesso! Já podes fechar esta janela. Token guardado em token.json."

    return f"Status: {response.status_code}<br>Resposta: {response.text}"

if __name__ == "__main__":
    app.run(port=3000)