
import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("NOTION_TOKEN")
db_id = os.getenv("NOTION_DB_ID")

print(f"Token: {token[:4]}...{token[-4:] if token else 'None'}")
print(f"DB ID: {db_id}")

client = Client(auth=token)

try:
    print("Testing users.me...")
    user = client.users.me()
    print("User:", user)
except Exception as e:
    print(f"Users.me failed: {e}")

try:
    print(f"\nTesting database retrieve for ID: {db_id}")
    db = client.databases.retrieve(database_id=db_id)
    print("DB Retrieve success:", db.get("id"))
except Exception as e:
    print(f"DB Retrieve failed: {e}")

import requests

print("\n--- Testing via requests ---")
headers = {
    "Authorization": f"Bearer {token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}
url_retrieve = f"https://api.notion.com/v1/databases/{db_id}"
print(f"GET {url_retrieve}")
r = requests.get(url_retrieve, headers=headers)
print(f"Retrieve Status: {r.status_code}")
if r.status_code != 200:
    print(r.text)

url_query = f"https://api.notion.com/v1/databases/{db_id}/query"
print(f"POST {url_query}")
r = requests.post(url_query, headers=headers, json={"page_size": 1})
print(f"Query Status: {r.status_code}")
print("Response:", r.text[:200])
