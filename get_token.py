import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID").strip()
CLIENT_SECRET = os.getenv("CLIENT_SECRET").strip()
REDIRECT_URI = os.getenv("REDIRECT_URI").strip()

CODE = "zxe8RriQ4BwUpVP8I93d39glqXpFnSXD"

data = {
    "grant_type": "authorization_code",
    "code": CODE,
    "redirect_uri": REDIRECT_URI,
}

print("A enviar:", data)

response = requests.post(
    "https://api.ouraring.com/oauth/token",
    data=data,
    auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
)

print(response.status_code)
print(response.text)