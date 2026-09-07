"""Unit tests; isolated live tests opt in with REDIS_DRILL_TEST_CONFIG."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from redis_fault import DrillError, Engine, probe_key, validate_config
import binascii

BASE = json.loads(Path(__file__).with_name("config.json").read_text())


class UnitTests(unittest.TestCase):
    def test_duplicate_ports_rejected(self):
        cfg = copy.deepcopy(BASE)
        cfg["nodes"][1]["port"] = cfg["nodes"][0]["port"]
        with self.assertRaises(DrillError):
            validate_config(cfg)

    def test_probe_keys_route_to_each_shard(self):
        for low, high in [(0, 5460), (5461, 10922), (10923, 16383), (16383, 16383)]:
            key = probe_key(low, high)
            self.assertTrue(low <= binascii.crc_hqx(key.encode(), 0) % 16384 <= high)

    def test_recovery_continues_after_one_node_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = dict(BASE, state_dir=Path(tmp).as_posix())
            # On Windows use an engine without Linux path validation for this pure test.
            engine = Engine.__new__(Engine)
            engine.cfg, engine.root = cfg, Path(tmp)
            engine.state_path = engine.root / "state.json"
            state = {"nodes": BASE["nodes"], "mode": "pause-io"}
            calls = []
            def restore(_, node):
                calls.append(node["port"])
                if node["port"] == 7001:
                    raise DrillError("injected missing container")
            with patch.object(engine, "restore_node", side_effect=restore):
                with self.assertRaises(DrillError):
                    engine.restore(state)
            self.assertEqual(sorted(calls), list(range(7001, 7007)))
            self.assertEqual(engine.state()["status"], "recovery_failed")


@unittest.skipUnless(os.environ.get("REDIS_DRILL_TEST_CONFIG"), "isolated cluster not configured")
class LiveTests(unittest.TestCase):
    def setUp(self):
        cfg = json.loads(Path(os.environ["REDIS_DRILL_TEST_CONFIG"]).read_text())
        # Never run fault tests against the user's real cluster.
        assert cfg["host"] == "127.0.0.1"
        assert all(n["container"].startswith("redis-drill-test-") for n in cfg["nodes"])
        self.engine = Engine(cfg)
        self.engine.resume()
        self.wait_healthy()

    def tearDown(self):
        self.engine.resume()
        self.wait_healthy()

    def wait_healthy(self):
        deadline = time.monotonic() + 15
        while True:
            try:
                self.engine.snapshot(require_healthy=True)
                return
            except DrillError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.3)

    def wait_recovered(self):
        deadline = time.monotonic() + 15
        while self.engine.state()["status"] != "recovered":
            if time.monotonic() > deadline:
                self.fail("Server timer did not restore the cluster")
            time.sleep(0.3)
        self.wait_healthy()

    def assert_normal(self):
        results = self.engine.probe()["probes"]
        self.assertEqual(len(results), 3)
        for p in results:
            self.assertEqual(p["read"]["result"], "ok")
            self.assertEqual(p["write"]["result"], "ok")

    def test_reject_writes_manual_restore_and_original_settings(self):
        # Nondefault original lag must be restored, including disabled value 0.
        port = self.engine.cfg["nodes"][0]["port"]
        with self.engine.client(port) as r:
            r.command("CONFIG", "SET", "min-replicas-max-lag", 0)
        try:
            before = [(n["min_replicas"], n["max_lag"]) for n in self.engine.snapshot(True)]
            self.engine.start("reject-writes", 30)
            with self.assertRaises(DrillError):
                self.engine.start("pause-io", 5)
            for p in self.engine.probe()["probes"]:
                self.assertEqual(p["read"]["result"], "ok")
                self.assertTrue(p["write"]["result"].startswith("NOREPLICAS"), p)
            self.engine.resume()
            after = [(n["min_replicas"], n["max_lag"]) for n in self.engine.snapshot(True)]
            self.assertEqual(before, after)
            self.assert_normal()
        finally:
            self.engine.resume()
            with self.engine.client(port) as r:
                r.command("CONFIG", "SET", "min-replicas-max-lag", 10)

    def test_reject_writes_timer_restore(self):
        self.engine.start("reject-writes", 5)
        self.wait_recovered()
        self.assert_normal()

    def test_pause_io_timer_restore(self):
        self.engine.start("pause-io", 5)
        for p in self.engine.probe(timeout=0.25)["probes"]:
            self.assertEqual(p["read"]["result"], "timeout")
            self.assertEqual(p["write"]["result"], "timeout")
        self.assertTrue(all(n["paused"] for n in self.engine.snapshot()))
        self.wait_recovered()
        self.assert_normal()

    def test_pause_io_manual_restore_and_stale_timer(self):
        self.engine.start("reject-writes", 30)
        old_id = self.engine.state()["id"]
        self.engine.resume()
        self.engine.start("pause-io", 30)
        self.assertEqual(self.engine.resume(old_id)["result"], "Stale timer ignored")
        self.assertTrue(all(n["paused"] for n in self.engine.snapshot()))
        self.engine.resume()
        self.wait_healthy()
        self.assert_normal()

    def test_timer_failure_prevents_fault(self):
        with patch.object(self.engine, "arm_timer", side_effect=DrillError("timer unavailable")):
            with self.assertRaises(DrillError):
                self.engine.start("reject-writes", 5)
        self.assert_normal()

    def test_partial_failure_rolls_back_all_nodes(self):
        original_apply = self.engine.apply
        def fail_one(mode, node):
            original_apply(mode, node)
            if node["port"] == self.engine.cfg["nodes"][0]["port"]:
                raise DrillError("injected lost acknowledgement after apply")
        with patch.object(self.engine, "apply", side_effect=fail_one):
            with self.assertRaises(DrillError):
                self.engine.start("reject-writes", 30)
        self.assertEqual(self.engine.state()["status"], "recovered")
        self.assert_normal()


if __name__ == "__main__":
    unittest.main(verbosity=2)
