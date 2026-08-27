import os
from dotenv import load_dotenv

load_dotenv()

print("CLIENT_ID:", os.getenv("CLIENT_ID"))
print("CLIENT_SECRET:", os.getenv("CLIENT_SECRET")[:4] + "...")
print("REDIRECT_URI:", os.getenv("REDIRECT_URI"))