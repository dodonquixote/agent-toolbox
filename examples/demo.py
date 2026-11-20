"""Day 1 demo: list the registered tools and fetch a page with fetch_url.

Run:  python examples/demo.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_toolbox import registry

print("Registered tools:")
for definition in registry.function_definitions():
    fn = definition["function"]
    print(f"  - {fn['name']}: {fn['description']}")

print("\nFetching https://example.com ...")
result = registry.call("fetch_url", {"url": "https://example.com", "max_chars": 500})
print(json.dumps(result, indent=2, ensure_ascii=False))
