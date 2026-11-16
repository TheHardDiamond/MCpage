"""Merge HTTP probe counts by Beijing date, including earlier snapshots."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING = timezone(timedelta(hours=8))

def record(history, checks):
    for check in checks:
        day = datetime.fromisoformat(check["checkedAt"]).astimezone(BEIJING).date().isoformat()
        counts = history.setdefault(check["id"], {}).setdefault(day, {"ok": 0, "failed": 0})
        counts["ok" if check["ok"] else "failed"] += 1

def main():
    output = Path("status.json")
    current = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    history = {}
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        if "httpHistory" in previous:
            history = previous["httpHistory"]
        else:
            commits = subprocess.check_output(
                ["git", "log", "--format=%H", "--", "status.json"], text=True
            ).splitlines()
            for commit in commits:
                snapshot = json.loads(subprocess.check_output(
                    ["git", "show", f"{commit}:status.json"], encoding="utf-8"
                ))
                record(history, snapshot.get("http", []))
    record(history, current["http"])
    current["httpHistory"] = history
    output.write_text(json.dumps(current, ensure_ascii=False) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
