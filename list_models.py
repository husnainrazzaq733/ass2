import urllib.request
import json
import os

api_key = os.environ.get("GROQ_API_KEY", "")

def list_models(key):
    url = "https://api.groq.com/openai/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            for m in data['data']:
                print(m['id'])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_models(api_key)
