"""Capture one snapshot for the public status page."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from server import ping

TARGET = {"id": "southmount", "name": "play.southmount.cn", "host": "play.southmount.cn", "port": 25565}
HTTP_TARGETS = [["skin","https://csu-mc.magicalsheep.cn"],["yggdrasil","https://csu-mc.magicalsheep.cn/api/yggdrasil"]]

def checked_at():
    return datetime.now(timezone.utc).isoformat()

def check_http(service, url):
    code = None
    try:
        with urlopen(Request(url, headers={"User-Agent": "MCpage status monitor"}), timeout=8) as response:
            code = response.status
    except HTTPError as error:
        code = error.code
    except OSError:
        pass
    name = {"skin": "CSU-MC 皮肤站", "yggdrasil": "CSU-MC Yggdrasil"}[service]
    return {"id": service, "name": name, "ok": code is not None and 200 <= code < 300,
            "code": code, "checkedAt": checked_at()}

def main():
    try:
        server = ping(TARGET)
    except (OSError, EOFError, ValueError):
        server = {"status": "unreachable"}
    server.update(id=TARGET["id"], name=TARGET["name"], checkedAt=checked_at())
    payload = {"servers": [server], "http": [check_http(*target) for target in HTTP_TARGETS]}
    Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
