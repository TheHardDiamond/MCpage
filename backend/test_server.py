import io
import json
import threading
import unittest
from unittest.mock import patch

from server import Collector, ping, varint

TARGET = {"id": "velocity", "name": "Velocity", "host": "localhost"}

class CollectorTests(unittest.TestCase):
    def test_manual_and_scheduled_calls_share_lock_and_cooldown(self):
        entered = threading.Event()
        release = threading.Event()
        results = []
        now = [0]
        calls = []
        def probe(target):
            calls.append(target["id"])
            entered.set()
            release.wait(2)
            return {"status": "online"}
        collector = Collector([TARGET], probe=probe, clock=lambda: now[0])
        worker = threading.Thread(target=lambda: results.append(collector.refresh("velocity")))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertTrue(collector.refresh("velocity", "client-1")[1]["busy"])
            self.assertEqual(collector.refresh("velocity", "client-2")[1]["retryAfter"], 60)
            self.assertEqual(collector.refresh("unknown", "client-2")[0], 404)
        finally:
            release.set()
            worker.join(2)
        self.assertEqual(results[0][1]["status"], "online")
        now[0] = 59
        self.assertEqual(collector.refresh("velocity")[1]["retryAfter"], 1)
        self.assertEqual(len(calls), 1)
        now[0] = 60
        collector.refresh("velocity")
        self.assertEqual(len(calls), 2)

    def test_rate_limit_and_timeout(self):
        def probe(target):
            raise TimeoutError()
        collector = Collector([TARGET], probe=probe, clock=lambda: 100)
        for _ in range(5):
            self.assertEqual(collector.refresh("velocity", "client")[1]["status"], "unreachable")
        self.assertEqual(collector.refresh("velocity", "client"), (429, {"retryAfter": 60}))
        self.assertEqual(collector.refresh("velocity", "other")[0], 200)

    def test_runs_again_at_five_minutes_without_clients(self):
        now = [0]
        calls = []
        def probe(target):
            calls.append(now[0])
            return {"status": "online"}
        def sleep(seconds):
            self.assertEqual(seconds, 300)
            now[0] += seconds
            if now[0] == 600:
                raise InterruptedError
        collector = Collector([TARGET], probe=probe, clock=lambda: now[0])
        with patch("server.time.sleep", sleep), self.assertRaises(InterruptedError):
            collector.run()
        self.assertEqual(calls, [0, 300])

    def test_protocol_parses_samples_and_missing_icon(self):
        payload = json.dumps({
            "description": {"text": "Velocity", "extra": [{"text": " §aServer"}]},
            "players": {"online": 14, "max": 100, "sample": [
                {"name": "Anonymous Player"}, {"name": "匿名玩家"}, {"name": "Steve"},
            ]},
        }).encode()
        packet = b"\0" + varint(len(payload)) + payload
        wire = io.BytesIO(varint(len(packet)) + packet)
        with patch("server.socket.create_connection") as connect:
            connection = connect.return_value.__enter__.return_value
            connection.recv.side_effect = wire.read
            result = ping(TARGET)
        self.assertEqual(result["online"], 14)
        self.assertEqual(result["sample"], ["Steve"])
        self.assertEqual(result["anonymous"], 2)
        self.assertEqual(result["motd"], "Velocity Server")
        self.assertIsNone(result["icon"])

