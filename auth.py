import os
import webbrowser
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
REDIRECT_URI = os.getenv("REDIRECT_URI")

AUTH_URL = (
    "https://cloud.ouraring.com/oauth/authorize"
    f"?response_type=code"
    f"&client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&scope=daily+heartrate"
)

print("A abrir o browser para autorizares o acesso...")
webbrowser.open(AUTH_URL)