import json
from pathlib import Path

state = json.loads((Path(__file__).parents[2] / "workspace" / "reality" / "account.json").read_text())
raise SystemExit(0 if state == {"applied_count": 1, "operation_ids": ["pilot-credit-001"]} else 1)
