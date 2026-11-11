import base64
import ipaddress
import json
import math
import os
import re
import socket
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PERIOD = 300
COOLDOWN = 60

def varint(value):
    value &= 0xffffffff
    data = bytearray()
    while value >= 128:
        data.append((value & 127) | 128)
        value >>= 7
    data.append(value)
    return bytes(data)

def read_int(stream):
    value = 0
    for shift in range(0, 35, 7):
        byte = stream.read(1)
        if not byte:
            raise EOFError()
        value |= (byte[0] & 127) << shift
        if byte[0] < 128:
            return value
    raise ValueError("Invalid VarInt")

def plain(component, depth=0):
    if depth >= 16:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, list):
        return "".join(plain(part, depth + 1) for part in component)
    if isinstance(component, dict):
        return plain(component.get("text", component.get("translate", "")), depth + 1) + plain(component.get("extra", []), depth + 1)
    return ""

def ping(target):
    import io
    host = target.get("handshakeHost", target["host"]).encode("idna")
    port = target.get("port", 25565)
    handshake = b"\0" + varint(-1) + varint(len(host)) + host + port.to_bytes(2, "big") + b"\1"
    deadline = time.monotonic() + 5
    with socket.create_connection((target["host"], port), timeout=5) as connection:
        connection.sendall(varint(len(handshake)) + handshake + b"\1\0")
        class Reader:
            def read(self, size):
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                return connection.recv(size)
        reader = Reader()
        size = read_int(reader)
        if not 2 <= size <= 262144:
            raise ValueError("Invalid status frame size")
        frame = bytearray()
        while len(frame) < size:
            chunk = reader.read(size - len(frame))
            if not chunk:
                raise EOFError()
            frame.extend(chunk)
        packet = io.BytesIO(frame)
        if read_int(packet) != 0:
            raise ValueError("Invalid status packet")
        length = read_int(packet)
        payload = packet.read()
        if len(payload) != length:
            raise ValueError("Invalid JSON length")
        status = json.loads(payload)

    players = status.get("players", {})
    sample = [entry["name"][:100] for entry in (players.get("sample") or [])[:256]
              if isinstance(entry, dict) and isinstance(entry.get("name"), str)]
    icon = status.get("favicon")
    prefix = "data:image/png;base64,"
    if not isinstance(icon, str) or not icon.startswith(prefix) or len(icon) > 120000:
        icon = None
    else:
        try:
            if not base64.b64decode(icon[len(prefix):], validate=True).startswith(b"\x89PNG\r\n\x1a\n"):
                icon = None
        except ValueError:
            icon = None
    return {
        "status": "online",
        "motd": re.sub(r"§[0-9a-fk-orx]", "", plain(status.get("description")), flags=re.I)[:500],
        "online": players.get("online") if type(players.get("online")) is int else None,
        "max": players.get("max") if type(players.get("max")) is int else None,
        "sample": [name for name in sample if name.strip().casefold() not in ("匿名玩家", "anonymous player")],
        "anonymous": sum(name.strip().casefold() in ("匿名玩家", "anonymous player") for name in sample),
        "icon": icon,
    }

class Collector:
    def __init__(self, targets, probe=ping, clock=time.monotonic):
        self.targets = {target["id"]: target for target in targets}
        if len(self.targets) != len(targets) or any(not re.fullmatch(r"[a-z0-9-]+", key) for key in self.targets):
            raise ValueError("Server IDs must be unique lowercase slugs")
        self.probe = probe
        self.clock = clock
        self.lock = threading.Lock()
        self.results = {}
        self.attempts = {}
        self.running = set()
        self.clients = {}

    def _snapshot(self, key):
        return {
            "id": key,
            "name": self.targets[key]["name"],
            **self.results.get(key, {"status": "pending"}),
            "retryAfter": math.ceil(max(0, self.attempts.get(key, -math.inf) + COOLDOWN - self.clock())),
            "busy": key in self.running,
        }

    def snapshots(self):
        with self.lock:
            return [self._snapshot(key) for key in self.targets]

    def refresh(self, key, client=None):
        with self.lock:
            if key not in self.targets:
                return 404, {"error": "Unknown server"}
            now = self.clock()
            if client is not None:
                for address, attempts in list(self.clients.items()):
                    if attempts[-1] <= now - 60:
                        del self.clients[address]
                if client not in self.clients and len(self.clients) >= 4096:
                    return 429, {"retryAfter": 60}
                attempts = self.clients.setdefault(client, deque())
                while attempts and attempts[0] <= now - 60:
                    attempts.popleft()
                if len(attempts) >= 5:
                    return 429, {"retryAfter": math.ceil(attempts[0] + 60 - now)}
                attempts.append(now)
            current = self._snapshot(key)
            if current["busy"] or current["retryAfter"]:
                return 200, current
            self.running.add(key)
            self.attempts[key] = now

        try:
            result = self.probe(self.targets[key])
        except Exception:
            result = {"status": "unreachable"}
        result["checkedAt"] = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.results[key] = result
            self.running.remove(key)
            return 200, self._snapshot(key)

    def run(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            while True:
                started = self.clock()
                list(executor.map(self.refresh, self.targets))
                time.sleep(max(0, PERIOD - (self.clock() - started)))

def serve(config):
    collector = Collector(config["servers"])
    origins = set(config.get("origins", []))
    trusted = {ipaddress.ip_address(address) for address in config.get("trustedProxies", [])}

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body=None):
            data = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
            self.send_response(status)
            origin = self.headers.get("Origin")
            if origin in origins:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if status == 429:
                self.send_header("Retry-After", str(body["retryAfter"]))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def client(self):
            peer = ipaddress.ip_address(self.client_address[0])
            if peer in trusted:
                # The immediate proxy must overwrite this header.
                try:
                    peer = ipaddress.ip_address(self.headers.get("X-Real-IP", ""))
                except ValueError:
                    pass
            if peer.version == 6 and peer.ipv4_mapped:
                peer = peer.ipv4_mapped
            return str(peer)

        def do_GET(self):
            if self.path == "/api/servers":
                self.reply(200, collector.snapshots())
            else:
                self.reply(404, {"error": "Unknown route"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self.reply(403, {"error": "Origin not allowed"})
                return
            match = re.fullmatch(r"/api/servers/([a-z0-9-]+)/refresh", self.path)
            if not match:
                self.reply(404, {"error": "Unknown route"})
                return
            self.reply(*collector.refresh(match[1], self.client()))

    server = ThreadingHTTPServer((config.get("bind", "127.0.0.1"), config.get("httpPort", 8787)), Handler)
    threading.Thread(target=collector.run, daemon=True).start()
    server.serve_forever()

if __name__ == "__main__":
    serve(json.loads(Path(os.environ.get("MC_CONFIG", "backend/config.local.json")).read_text(encoding="utf-8-sig")))

