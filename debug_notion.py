
from notion_client import Client
import sys

try:
    c = Client(auth="secret_test")
    print(f"Client type: {type(c)}")
    print(f"Databases type: {type(c.databases)}")
    print(f"Has query? {hasattr(c.databases, 'query')}")
    print(f"Dir databases: {dir(c.databases)}")
except Exception as e:
    print(f"Error: {e}")
