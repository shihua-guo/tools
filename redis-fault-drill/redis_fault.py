#!/usr/bin/env python3
"""Redis 5 cluster fault drills. Standard library only; Windows relays via SSH."""
from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor


class DrillError(Exception):
    pass


class RedisError(DrillError):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def run(argv, timeout=15):
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DrillError(f"{argv[0]} failed: {type(exc).__name__}") from None
    if result.returncode:
        raise DrillError(result.stderr.strip() or result.stdout.strip()
                         or f"{argv[0]} exit {result.returncode}")
    return result.stdout.strip()


def validate_config(cfg):
    ipaddress.ip_address(cfg["host"])
    nodes = cfg["nodes"]
    if len(nodes) != 6 or len({n["port"] for n in nodes}) != 6:
        raise DrillError("Exactly six distinct Redis ports are required")
    if len({n["container"] for n in nodes}) != 6:
        raise DrillError("Container names must be distinct")
    for n in nodes:
        if type(n["port"]) is not int or not 1 <= n["port"] <= 65535:
            raise DrillError("Invalid Redis port")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", n["container"]):
            raise DrillError("Invalid Docker container name")
    for key in ("password_file", "state_dir"):
        if not cfg[key].startswith("/") or ".." in cfg[key].split("/"):
            raise DrillError(f"{key} must be an absolute server path")
    return cfg


class Redis:
    def __init__(self, host, port, password, timeout=2):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.file = self.sock.makefile("rb")
        try:
            self.command("AUTH", password)  # Redis 5 has no ACL username.
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.file.close()
        self.sock.close()

    def read(self):
        tag = self.file.read(1)
        if not tag:
            raise DrillError("Redis connection closed")
        line = self.file.readline()
        if not line.endswith(b"\r\n"):
            raise DrillError("Truncated Redis response")
        line = line[:-2]
        if tag == b"+":
            return line.decode()
        if tag == b"-":
            raise RedisError(line.decode(errors="replace"))
        if tag == b":":
            return int(line)
        if tag == b"$":
            length = int(line)
            if length == -1:
                return None
            if not 0 <= length <= 8 * 1024 * 1024:
                raise DrillError("Unexpected bulk response size")
            data = self.file.read(length)
            if len(data) != length or self.file.read(2) != b"\r\n":
                raise DrillError("Truncated bulk response")
            return data.decode(errors="replace")
        if tag == b"*":
            length = int(line)
            if length == -1:
                return None
            if not 0 <= length <= 10000:
                raise DrillError("Unexpected array response size")
            return [self.read() for _ in range(length)]
        raise DrillError("Unsupported Redis response")

    def command(self, *args):
        parts = [str(a).encode() for a in args]
        wire = b"*%d\r\n" % len(parts)
        wire += b"".join(b"$%d\r\n" % len(p) + p + b"\r\n" for p in parts)
        self.sock.sendall(wire)
        return self.read()


def info_dict(value):
    return dict(line.split(":", 1) for line in value.splitlines()
                if line and not line.startswith("#") and ":" in line)


def config_value(client, key):
    value = client.command("CONFIG", "GET", key)
    if not value or len(value) != 2:
        raise DrillError(f"Redis does not support {key}")
    return int(value[1])


def probe_key(low, high):
    prefix = "__redis_fault_probe__:" + uuid.uuid4().hex + ":"
    for i in range(100000):
        key = prefix + str(i)
        if low <= binascii.crc_hqx(key.encode(), 0) % 16384 <= high:
            return key
    raise DrillError("Could not choose a probe key")


class Engine:
    def __init__(self, cfg):
        self.cfg = validate_config(cfg)
        self.root = Path(cfg["state_dir"])
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.password = None

    def client(self, port, timeout=2):
        if self.password is None:
            lines = Path(self.cfg["password_file"]).read_text().splitlines()
            values = [x.split("=", 1)[1] for x in lines if x.startswith("REDIS_PASSWORD=")]
            if len(values) != 1 or not values[0]:
                raise DrillError("REDIS_PASSWORD missing from server credential file")
            self.password = values[0]
        return Redis(self.cfg["host"], port, self.password, timeout)

    @contextlib.contextmanager
    def lock(self):
        import fcntl
        with (self.root / "operation.lock").open("a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DrillError("Another operation is running; retry shortly") from None
            yield

    def state(self):
        if not self.state_path.exists():
            return None
        return json.loads(self.state_path.read_text())

    def save(self, state):
        tmp = self.root / (".state-" + uuid.uuid4().hex)
        with tmp.open("x") as f:
            os.chmod(tmp, 0o600)
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state_path)

    def containers(self):
        data = json.loads(run(["docker", "inspect"] +
                              [n["container"] for n in self.cfg["nodes"]]))
        return {c["Name"].lstrip("/"): c for c in data}

    def snapshot(self, require_healthy=False):
        containers = self.containers()
        result = []
        for node in self.cfg["nodes"]:
            c = containers[node["container"]]
            row = dict(node, container_id=c["Id"], running=c["State"]["Running"],
                       paused=c["State"]["Paused"])
            try:
                if not row["running"] or row["paused"]:
                    raise DrillError("Container stopped or paused")
                with self.client(node["port"]) as r:
                    server = info_dict(r.command("INFO", "server"))
                    cluster = info_dict(r.command("CLUSTER", "INFO"))
                    topology = r.command("CLUSTER", "NODES")
                    rows = [s.split() for s in topology.splitlines()]
                    own = next(x for x in rows if "myself" in x[2].split(","))
                    row.update(version=server["redis_version"], run_id=server["run_id"],
                               node_id=own[0], role="master" if "master" in own[2].split(",") else "replica",
                               cluster_state=cluster["cluster_state"],
                               min_replicas=config_value(r, "min-replicas-to-write"),
                               max_lag=config_value(r, "min-replicas-max-lag"),
                               peer_ids=sorted(x[0] for x in rows))
                    if row["role"] == "master":
                        ranges = [v for v in own[8:] if not v.startswith("[")]
                        first = ranges[0].split("-")
                        row["probe_key"] = probe_key(int(first[0]), int(first[-1]))
                    if require_healthy:
                        expected = {f'{self.cfg["host"]}:{n["port"]}' for n in self.cfg["nodes"]}
                        actual = {x[1].split("@")[0] for x in rows}
                        if expected != actual or any(x[7] != "connected" or
                                set(x[2].split(",")) & {"fail", "fail?", "handshake", "noaddr"} for x in rows):
                            raise DrillError("Unexpected cluster members or unhealthy links")
                        if cluster["cluster_state"] != "ok" or int(cluster["cluster_slots_ok"]) != 16384:
                            raise DrillError("Cluster is not healthy")
                        if not row["version"].startswith("5."):
                            raise DrillError("This tool's fault modes are validated for Redis 5")
            except (OSError, DrillError, KeyError, IndexError, StopIteration) as exc:
                row["error"] = str(exc) or type(exc).__name__
            result.append(row)
        if require_healthy:
            errors = [f'{x["port"]}: {x["error"]}' for x in result if "error" in x]
            if errors:
                raise DrillError("Preflight failed: " + "; ".join(errors))
            ids = sorted(x["node_id"] for x in result)
            if any(x["peer_ids"] != ids for x in result) or sum(x["role"] == "master" for x in result) != 3:
                raise DrillError("Expected one cluster with three masters and three replicas")
        return result

    def status(self):
        return {"target": self.cfg["name"], "checked_at": utc(),
                "incident": self.state(), "nodes": self.snapshot()}

    def arm_timer(self, state, seconds):
        runner = self.root / ("incident-" + state["id"] + ".py")
        shutil.copyfile(Path(__file__).resolve(), runner)
        os.chmod(runner, 0o600)
        encoded = base64.b64encode(json.dumps(self.cfg).encode()).decode()
        run(["systemd-run", "--unit=" + state["timer_unit"], "--collect",
             f"--on-active={seconds}s", "--timer-property=AccuracySec=1s",
             "--property=Type=oneshot", "--property=Restart=on-failure",
             "--property=RestartSec=3s", "--property=StartLimitIntervalSec=0",
             sys.executable, str(runner), "--target-b64", encoded, "--json",
             "resume", "--incident", state["id"]])
        if run(["systemctl", "is-active", state["timer_unit"] + ".timer"]) != "active":
            raise DrillError("Recovery timer was not activated")

    def apply(self, mode, node):
        if mode == "pause-io":
            run(["docker", "pause", node["container_id"]])
        else:
            with self.client(node["port"]) as r:
                r.command("CONFIG", "SET", "min-replicas-max-lag", node["applied_lag"])
                r.command("CONFIG", "SET", "min-replicas-to-write", 6)

    def start(self, mode, seconds):
        if mode not in ("reject-writes", "pause-io"):
            raise DrillError("Unknown fault mode")
        if type(seconds) is not int or not 5 <= seconds <= 3600:
            raise DrillError("Duration must be 5..3600 seconds")
        with self.lock():
            previous = self.state()
            if previous and previous["status"] != "recovered":
                raise DrillError("An incident is unresolved; run resume before starting another")
            nodes = self.snapshot(require_healthy=True)
            for n in nodes:
                n["applied_lag"] = n["max_lag"] if n["max_lag"] > 0 else 10
            incident = uuid.uuid4().hex
            state = {"id": incident, "mode": mode, "status": "arming", "created_at": utc(),
                     "recover_after_seconds": seconds, "recover_at_unix": time.time() + seconds,
                     "timer_unit": "redis-fault-" + incident, "nodes": nodes}
            self.save(state)
            try:
                self.arm_timer(state, seconds)  # Never inject a fault without recovery armed.
            except BaseException:
                state.update(status="recovered", result="No fault injected: timer setup failed", recovered_at=utc())
                self.save(state)
                raise
            try:
                state["status"] = "applying"
                self.save(state)
                # Try every node, and wait for all outcomes before rollback.
                with ThreadPoolExecutor(max_workers=6) as pool:
                    futures = [pool.submit(self.apply, mode, n) for n in nodes]
                    failures = []
                    for f in futures:
                        try:
                            f.result()
                        except Exception as exc:
                            failures.append(str(exc))
                if failures:
                    raise DrillError("Fault only partially applied: " + "; ".join(failures))
                state["status"] = "active"
                self.save(state)
            except BaseException:
                self.restore(state)
                raise
            return {"target": self.cfg["name"], "incident": state}

    def restore_node(self, state, node):
        c = json.loads(run(["docker", "inspect", node["container"]]))[0]
        if c["Id"] != node["container_id"]:
            raise DrillError(f'{node["container"]} was replaced; refusing to change its replacement')
        if state["mode"] == "pause-io":
            if c["State"]["Paused"]:
                run(["docker", "unpause", c["Id"]])
            return
        with self.client(node["port"]) as r:
            server = info_dict(r.command("INFO", "server"))
            current_min = config_value(r, "min-replicas-to-write")
            current_lag = config_value(r, "min-replicas-max-lag")
            original = (node["min_replicas"], node["max_lag"])
            if (current_min, current_lag) == original:
                return
            if server["run_id"] != node["run_id"]:
                raise DrillError(f'{node["port"]}: Redis restarted with different settings; inspect manually')
            if current_min not in (6, original[0]) or current_lag not in (node["applied_lag"], original[1]):
                raise DrillError(f'{node["port"]}: settings changed by another operator; refusing to overwrite')
            r.command("CONFIG", "SET", "min-replicas-to-write", original[0])
            r.command("CONFIG", "SET", "min-replicas-max-lag", original[1])

    def restore(self, state):
        errors = []
        try:
            with ThreadPoolExecutor(max_workers=6) as pool:
                pairs = [(n, pool.submit(self.restore_node, state, n)) for n in state["nodes"]]
                for node, f in pairs:
                    try:
                        f.result()
                    except Exception as exc:
                        errors.append(f'{node["port"]}: {exc}')
        except Exception as exc:
            errors.append(str(exc))
        state["restore_errors"] = errors
        state["status"] = "recovery_failed" if errors else "recovered"
        if not errors:
            state["recovered_at"] = utc()
        self.save(state)
        if errors:
            raise DrillError("Recovery incomplete; timer will retry: " + "; ".join(errors))
        return {"target": self.cfg["name"], "incident": state}

    def resume(self, incident=None):
        with self.lock():
            state = self.state()
            if not state or state["status"] == "recovered":
                return {"result": "No active drill"}
            if incident and state["id"] != incident:
                return {"result": "Stale timer ignored"}
            return self.restore(state)

    def probe(self, timeout=1):
        state = self.state()
        if state and state["status"] != "recovered" and state["mode"] == "pause-io":
            nodes = state["nodes"]  # Live topology is unavailable while containers are frozen.
        else:
            nodes = self.snapshot(require_healthy=True)
        masters = [n for n in nodes if n.get("role") == "master"]
        def one(node, operation):
            started = time.monotonic()
            try:
                with self.client(node["port"], timeout) as r:
                    # Random missing key: exercise real GET/DEL paths, without inserting data.
                    value = r.command(operation, node["probe_key"])
                    result = "ok" if value in (None, 0) else "unexpected_value"
            except (socket.timeout, TimeoutError):
                result = "timeout"
            except (OSError, DrillError) as exc:
                result = str(exc)
            return {"result": result, "elapsed_ms": round((time.monotonic() - started) * 1000)}
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = [(n, pool.submit(one, n, "GET"), pool.submit(one, n, "DEL")) for n in masters]
            return {"target": self.cfg["name"], "probes": [
                {"port": n["port"], "read": read.result(), "write": write.result()}
                for n, read, write in jobs]}


def relay(cfg, args):
    identity = str(Path(cfg["ssh_identity"]).expanduser())
    destination = cfg["ssh_host"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+", destination):
        raise DrillError("Invalid SSH destination")
    ssh = ["ssh", "-i", identity, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", destination]
    root = cfg["state_dir"]
    remote = root + "/redis_fault.py"
    temporary = remote + ".upload-" + uuid.uuid4().hex
    upload = (f"umask 077; mkdir -p -- {shlex.quote(root)} && "
              f"cat > {shlex.quote(temporary)} && mv -- {shlex.quote(temporary)} {shlex.quote(remote)}")
    result = subprocess.run(ssh + [upload], input=Path(__file__).read_bytes())
    if result.returncode:
        raise DrillError("Could not deploy the server-side tool via SSH")
    encoded = base64.b64encode(json.dumps(cfg).encode()).decode()
    remote_args = ["python3", remote, "--target-b64", encoded]
    if args.json:
        remote_args.append("--json")
    remote_args.append(args.action)
    if args.action in ("reject-writes", "pause-io"):
        remote_args += ["--seconds", str(args.seconds)]
    result = subprocess.run(ssh + [shlex.join(remote_args)])
    return result.returncode


def display(result, as_json=False):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if "target" in result:
        print("目标:", result["target"])
    state = result.get("incident")
    if state:
        print(f'演练: {state["mode"]} | 状态: {state["status"]} | ID: {state["id"]}')
        if state["status"] != "recovered":
            print("计划恢复:", dt.datetime.fromtimestamp(state["recover_at_unix"]).astimezone().isoformat(timespec="seconds"))
            print("恢复由服务器 systemd 执行，关闭 Windows 工具不会取消恢复。")
        for error in state.get("restore_errors", []):
            print("恢复异常:", error)
    for n in result.get("nodes", []):
        print(f'{n["port"]}: Redis {n.get("version", "?")} {n.get("role", "?")} '
              f'paused={n["paused"]} cluster={n.get("cluster_state", "?")} '
              f'min-replicas={n.get("min_replicas", "?")} {n.get("error", "")}')
    for p in result.get("probes", []):
        print(f'{p["port"]}: 读={p["read"]["result"]} ({p["read"]["elapsed_ms"]} ms), '
              f'写={p["write"]["result"]} ({p["write"]["elapsed_ms"]} ms)')
    if "result" in result:
        print(result["result"])


def execute(cfg, args):
    if os.name == "nt" or args.via_ssh:
        return relay(cfg, args)
    engine = Engine(cfg)
    if args.action in ("reject-writes", "pause-io"):
        result = engine.start(args.action, args.seconds)
    elif args.action == "resume":
        result = engine.resume(getattr(args, "incident", None))
    elif args.action == "probe":
        result = engine.probe()
    else:
        result = engine.status()
    display(result, args.json)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Redis 5 集群故障演练：写入报错 / 阻塞读写 / 定时恢复")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--via-ssh", action="store_true", help="Linux 客户端也通过 SSH 执行")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--target-b64", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("status", "probe", "menu"):
        sub.add_parser(name)
    for name in ("reject-writes", "pause-io"):
        p = sub.add_parser(name)
        p.add_argument("--seconds", type=int, default=60, help="5..3600 秒；默认 60")
    p = sub.add_parser("resume")
    p.add_argument("--incident", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    cfg = validate_config(json.loads(base64.b64decode(args.target_b64)) if args.target_b64
                          else json.loads(Path(args.config).read_text(encoding="utf-8-sig")))
    if args.action != "menu":
        return execute(cfg, args)
    print(f'\nRedis 故障演练工具 — {cfg["name"]} ({cfg["host"]})')
    print("打开菜单不会注入故障。两个故障模式互斥；开始前检查全部六个节点。")
    while True:
        print("\n1. 查看状态\n2. 写入立即报错（读取继续）\n3. 阻塞所有读写\n4. 立即恢复\n5. 验证读写\n0. 退出")
        choice = input("选择: ").strip()
        if choice == "0":
            return 0
        actions = {"1": "status", "2": "reject-writes", "3": "pause-io", "4": "resume", "5": "probe"}
        if choice not in actions:
            print("请输入菜单编号。")
            continue
        args.action = actions[choice]
        try:
            if choice in ("2", "3"):
                args.seconds = int(input("持续秒数，5..3600（回车 60）: ").strip() or "60")
                if not 5 <= args.seconds <= 3600:
                    raise DrillError("持续时间必须为 5..3600 秒")
            execute(cfg, args)
        except (DrillError, OSError, ValueError) as exc:
            print("操作失败:", exc)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        sys.exit(main())
    except (DrillError, OSError, ValueError) as exc:
        print("操作失败:", exc, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("操作中断；已启动的服务器定时恢复仍然有效。", file=sys.stderr)
        sys.exit(130)
