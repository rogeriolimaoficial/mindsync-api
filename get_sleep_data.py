import json
import requests

with open("token.json") as f:
    token_data = json.load(f)

access_token = token_data["access_token"]

response = requests.get(
    "https://api.ouraring.com/v2/usercollection/daily_sleep",
    headers={"Authorization": f"Bearer {access_token}"},
)

print(response.status_code)
print(response.json())
