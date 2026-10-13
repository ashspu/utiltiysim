"""Fail-closed, credential-free single-host orchestration. Python 3.11+ stdlib."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import ssl
import stat
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
SCHEMA = "utilitysim-connected-stack/1"
MARKER = ".connected-stack-volume.json"
ROLES = ("producer", "controller")


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused("Required JSON file is missing or invalid.") from None


def argv(value, label):
    require(isinstance(value, list) and value and all(isinstance(x, str) and x and
            not any(c in x for c in ("\x00", "\n", "\r")) for x in value),
            f"Supply the reviewed {label} executable and argument array.")
    require(not any(re.search(r"(?i)(?:token|password|secret|credential)=", x) for x in value),
            "Credentials must be supplied through protected files, not arguments.")
    require(not any(x.lower() in {"--token", "--password", "--secret", "--credential", "--api-key"} for x in value),
            "Use protected credential files rather than raw credential arguments.")
    return value


def validate_config(cfg):
    require(isinstance(cfg, dict) and cfg.get("schemaVersion") == SCHEMA, "Unsupported deployment schema.")
    require(cfg.get("readiness") == "deployment-ready", "Candidate artifacts are not deployment-ready.")
    require(type(cfg.get("fieldEnabled")) is bool, "Declare whether the managed field owner is enabled.")
    require(type(cfg.get("operatorEnabled", False)) is bool, "Declare whether the billing operator is enabled.")
    require(isinstance(cfg.get("runId"), str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", cfg["runId"]),
            "Supply the actual fixed connected run identity.")
    try:
        uuid.UUID(cfg.get("volumeId", ""))
    except (ValueError, TypeError, AttributeError):
        raise Refused("Supply a logical volume UUID.") from None
    host = cfg.get("producerHost")
    require(isinstance(host, str) and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host)
            and "." in host and not any(part == "" or part.startswith("-") or part.endswith("-") for part in host.split(".")),
            "Supply the actual public producer DNS hostname.")
    require(not host.endswith((".example", ".invalid", ".test", ".local", ".internal", ".localhost"))
            and host not in ("example.com", "example.org", "example.net")
            and not host.endswith((".example.com", ".example.org", ".example.net")), "Placeholder hostnames are refused.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise Refused("Producer requires a DNS hostname, not an IP literal.")
    for name in ("dataRoot", "tlsDirectory", "backupDirectory"):
        path = cfg.get(name)
        require(isinstance(path, str) and path.startswith("/") and path != "/" and
                ".." not in Path(path).parts, f"Supply an absolute Linux {name} path.")
    paths = [Path(cfg[x]) for x in ("dataRoot", "tlsDirectory", "backupDirectory")]
    require(all(not a.is_relative_to(b) and not b.is_relative_to(a)
                for i, a in enumerate(paths) for b in paths[i + 1:]), "Data, TLS and backup paths must be disjoint.")
    require(isinstance(cfg.get("ageRecipient"), str) and re.fullmatch(r"age1[0-9a-z]{58}", cfg["ageRecipient"]),
            "Supply the encrypted backup recipient; identity stays outside deployment config.")
    services = cfg.get("services", {})
    require(isinstance(services, dict) and set(services) == {*ROLES, "edge"}, "Supply exactly producer, controller and edge.")
    for role, service in services.items():
        require(isinstance(service, dict) and isinstance(service.get("image"), str) and
                re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", service["image"]), f"Supply the verified {role} image digest.")
        if role == "edge":
            continue
        require(re.fullmatch(r"[0-9a-f]{40}", service.get("sourceCommit", "")), f"Pin the {role} source commit.")
        path = service.get("secretsFile")
        require(isinstance(path, str) and path.startswith("/") and ".." not in Path(path).parts and
                not Path(path).is_relative_to(paths[0]) and not Path(path).is_relative_to(paths[2]),
                "Protected service secrets must be outside data and backups.")
        names = service.get("requiredSecrets")
        require(isinstance(names, list) and names and len(names) == len(set(names)) and
                all(isinstance(n, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,99}", n) for n in names),
                f"Declare the required scoped {role} credential environment names.")
        argv(service.get("command"), role + "startup")
        argv(service.get("healthCommand"), role + "readiness")
    controller = services["controller"]
    mode = cfg.get("recoveryMode", "owner-hooks/1")
    if cfg.get("operatorEnabled", False):
        require(mode == "owner-cli-stopped/1", "Operator startup requires the reviewed connected owner CLI.")
        require("UTILITYSIM_OPERATOR_TOKEN" in services["producer"]["requiredSecrets"]
                and "CONNECTED_OPERATOR_TOKEN" in controller["requiredSecrets"],
                "Declare a dedicated operator capability at both server owners.")
    require(mode in ("owner-hooks/1", "owner-cli-stopped/1"), "Unsupported recovery integration mode.")
    if mode == "owner-hooks/1":
        argv(controller.get("pauseCommand"), "controller pause")
        argv(controller.get("checkpointCommand"), "controller checkpoint")
    else:
        require(cfg["fieldEnabled"] is False, "Actual VS remote field recovery is unsupported.")
        item = cfg.get("ownerCli")
        require(isinstance(item, dict) and set(item) == {"directory", "remoteConfig", "controllerId", "worldId", "port", "serviceTokenEnv", "clockTokenEnv"},
                "Supply the exact stopped owner CLI configuration.")
        for name in ("directory", "remoteConfig"):
            path = item.get(name)
            require(isinstance(path, str) and (path == "/data" or path.startswith("/data/"))
                    and ".." not in PurePosixPath(path).parts and "\\" not in path,
                    "Owner CLI paths must stay at the original /data mount.")
        require(type(item.get("port")) is int and 1 <= item["port"] <= 65535,
                "Supply the actual loopback controller port.")
        require(all(isinstance(item.get(name), str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", item[name])
                    for name in ("controllerId", "worldId")), "Pin actual controller and producer world identities.")
        require(all(isinstance(item.get(name), str) for name in ("serviceTokenEnv", "clockTokenEnv")) and
                item["serviceTokenEnv"] != item["clockTokenEnv"] and
                all(name in controller["requiredSecrets"] for name in (item["serviceTokenEnv"], item["clockTokenEnv"])),
                "Declare separate controller service and runtime clock capabilities.")
    evidence = cfg.get("evidence", {})
    for name in ("producerContainerAcceptance", "controllerConnectedAcceptance", "linuxRestoreAcceptance"):
        require(isinstance(evidence.get(name), str) and evidence[name].strip(), f"Record reviewed {name} evidence.")
    require(re.fullmatch(r"[0-9a-f]{40}", evidence.get("intervalCompatibilityCommit", "")),
            "Pin the integrated interval-compatibility commit.")
    owners = cfg.get("ownerFiles")
    names = {"world", "catalog", "runtime", "billing", "ledger", "evidence", "controller"}
    require(isinstance(owners, dict) and names <= owners.keys() and
            set(owners) <= names | {"field", "producerField"}, "Bind every producer and VS owner file explicitly.")
    require(not cfg["fieldEnabled"] or "field" in owners and "producerField" in owners,
            "Enabled field requires both physical and VS field owner bindings.")
    paths = set()
    for name, binding in owners.items():
        expected = "producer" if name in ("world", "catalog", "producerField") else "controller"
        require(isinstance(binding, dict) and binding.get("service") == expected and isinstance(binding.get("path"), str),
                "Owner file is missing its required service and original relative path.")
        path = PurePosixPath(binding["path"])
        require(path.parts and not path.is_absolute() and ".." not in path.parts and
                "\\" not in binding["path"] and path.as_posix() == binding["path"], "Unsafe owner file path.")
        identity = (expected, path.as_posix())
        require(identity not in paths, "Independent owners cannot alias one file.")
        paths.add(identity)
    return cfg


def operator_secrets(cfg, values):
    if not cfg.get("operatorEnabled", False):
        return
    producer, controller = values["producer"], values["controller"]
    token = producer.get("UTILITYSIM_OPERATOR_TOKEN")
    require(isinstance(token, str) and 32 <= len(token) <= 4096
            and all(33 <= ord(char) <= 126 for char in token)
            and token == controller.get("CONNECTED_OPERATOR_TOKEN"),
            "Both servers require the same bounded printable operator capability.")
    protected = [value for role in ROLES for key, value in values[role].items()
                 if key not in ("UTILITYSIM_OPERATOR_TOKEN", "CONNECTED_OPERATOR_TOKEN")
                 and any(word in key for word in ("TOKEN", "KEY", "PASSWORD", "SECRET"))]
    require(token not in protected, "Operator capability must differ from gateway, machine, control and clock credentials.")


def secrets(path, required):
    path = Path(path)
    require(path.is_file() and path.resolve() == path.absolute(), "Service secret file is missing or passes through a symbolic link.")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        require(mode & 0o077 == 0, "Service secret files must have mode0600 or0400.")
        require(path.stat().st_uid == 10001, "Service secrets must be readable by UID10001 only.")
    value = read_json(path)
    require(isinstance(value, dict) and set(value) == set(required), "Service credentials do not match required names.")
    require(all(isinstance(v, str) and v and "\x00" not in v and "\n" not in v and "\r" not in v
                for v in value.values()), "Invalid credential file.")
    require(all(len(v) >= 32 for k, v in value.items() if any(word in k for word in ("TOKEN", "PASSWORD", "SECRET"))),
            "Credentials require at least32 characters.")
    return value


def run(command, *, env=None, timeout=120, capture=False):
    try:
        result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=timeout, check=True)
        require(not capture or len(result.stdout) <= 65536, "Command output exceeds its bounded contract.")
        return result.stdout if capture else None
    except (OSError, subprocess.SubprocessError):
        raise Refused("Required executable operation failed; inspect the service locally without disclosing credentials.") from None


def compose_env(cfg, config_path):
    return {**os.environ, "PRODUCER_IMAGE": cfg["services"]["producer"]["image"],
            "CONTROLLER_IMAGE": cfg["services"]["controller"]["image"], "EDGE_IMAGE": cfg["services"]["edge"]["image"],
            "PRODUCER_HOST": cfg["producerHost"], "STACK_DATA_ROOT": cfg["dataRoot"],
            "STACK_CONFIG": str(Path(config_path).resolve()), "STACK_OPS": str(HERE),
            "PRODUCER_SECRETS": cfg["services"]["producer"]["secretsFile"],
            "CONTROLLER_SECRETS": cfg["services"]["controller"]["secretsFile"], "TLS_DIRECTORY": cfg["tlsDirectory"]}


def compose(cfg, config_path, *args, capture=False):
    return run(["docker", "compose", "--project-name", "utilitysim-b", "-f", str(HERE / "compose.json"), *args],
               env=compose_env(cfg, config_path), timeout=180, capture=capture)


def volume(cfg):
    root = Path(cfg["dataRoot"])
    require(root.is_dir() and os.path.ismount(root) and root.resolve() == root.absolute(), "Expected durable mount is absent; refusing ephemeral fallback.")
    require(read_json(root / MARKER) == {"schemaVersion": SCHEMA, "volumeId": cfg["volumeId"], "runId": cfg["runId"]},
            "Mounted volume identity does not match the connected run.")
    for role in ROLES:
        directory = root / role
        require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_uid == 10001,
                "Owner data directory must exist on the mounted disk and belong to UID10001.")


def owner_files(cfg):
    root = Path(cfg["dataRoot"])
    for binding in cfg["ownerFiles"].values():
        path = root / binding["service"] / binding["path"]
        require(path.is_file() and path.resolve() == path.absolute(), "A required original owner file is missing or linked.")


def preflight(cfg, config_path):
    require(sys.platform.startswith("linux"), "Live deployment requires a Linux Docker host; use validate for portable checks.")
    require(shutil.which("docker"), "Docker/Compose is unavailable.")
    volume(cfg)
    owner_files(cfg)
    values = {role: secrets(cfg["services"][role]["secretsFile"], cfg["services"][role]["requiredSecrets"])
              for role in ROLES}
    operator_secrets(cfg, values)
    tls = Path(cfg["tlsDirectory"])
    key, cert = tls / "privatekey.pem", tls / "fullchain.pem"
    require(key.is_file() and cert.is_file() and key.resolve() == key.absolute() and cert.resolve() == cert.absolute(), "Supply real TLS certificate and private key without symbolic links.")
    require(tls.stat().st_uid == 10001 and stat.S_IMODE(tls.stat().st_mode) & 0o077 == 0,
            "TLS directory must belong to UID10001 with mode0700.")
    require(key.stat().st_uid == 10001 and stat.S_IMODE(key.stat().st_mode) & 0o077 == 0, "TLS private key must belong to UID10001 with mode0600/0400.")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        decoded = ssl._ssl._test_decode_cert(str(cert))
        names = [name for kind, name in decoded.get("subjectAltName", ()) if kind == "DNS"]
        host = cfg["producerHost"]
        require(any(name == host or name.startswith("*.") and name.count(".") == host.count(".")
                    and host.endswith(name[1:]) for name in names), "TLS certificate does not cover producer hostname.")
        import time
        require(ssl.cert_time_to_seconds(decoded["notBefore"]) <= time.time() <
                ssl.cert_time_to_seconds(decoded["notAfter"]), "TLS certificate is not currently valid.")
    except (OSError, ValueError, ssl.SSLError):
        raise Refused("TLS certificate/key validation failed.") from None
    run(["docker", "info", "--format", "{{.ServerVersion}}"])
    for service in cfg["services"].values():
        run(["docker", "image", "inspect", service["image"]])
    compose(cfg, config_path, "config", "--quiet")


def initialize(cfg):
    require(sys.platform.startswith("linux"), "Volume initialization requires Linux.")
    root = Path(cfg["dataRoot"])
    require(root.is_dir() and os.path.ismount(root) and root.resolve() == root.absolute(), "Mount an existing durable filesystem first.")
    existing = list(root.iterdir())
    require(not existing or len(existing) == 1 and existing[0].name == "lost+found" and
            existing[0].is_dir() and not any(existing[0].iterdir()),
            "Initialization requires an empty mounted filesystem; it never formats or deletes data.")
    for role in ROLES:
        path = root / role
        path.mkdir(mode=0o700)
        os.chown(path, 10001, 10001)
    (root / MARKER).write_text(json.dumps({"schemaVersion": SCHEMA, "volumeId": cfg["volumeId"], "runId": cfg["runId"]}) + "\n")


def service(role, action):
    cfg = validate_config(read_json("/config/deployment.json"))
    item = cfg["services"][role]
    env = {**os.environ, **secrets("/secrets/service.json", item["requiredSecrets"])}
    if action == "launch":
        command = item["command"]
        os.execvpe(command[0], command, env)
    if action == "health":
        run(item["healthCommand"], env=env, timeout=12)
        return
    if action == "owner-pause":
        require(role == "controller" and cfg.get("recoveryMode") == "owner-cli-stopped/1", "Select the actual stopped owner CLI integration.")
        raw = run(["python", "/ops/owners.py", "pause"], env=env, timeout=110, capture=True)
        # This action reports executed pause/lease facts only, never stopped workers.
        print(raw.decode().strip())
        return
    require(role == "controller", "Controller hooks cannot run in the producer.")
    raw = run(item[action + "Command"], env=env, timeout=120, capture=True)
    try:
        result = json.loads(raw)
    except ValueError:
        raise Refused("Controller hook did not return bounded JSON.") from None
    required = {"runId", "clock", "paused", "idle", "workersStopped", "controllerRevision"}
    if action == "checkpoint":
        required |= {"complete", "owners"}
    require(isinstance(result, dict) and required <= result.keys() and result["runId"] == cfg["runId"]
            and all(result.get(key) is True for key in ("paused", "idle", "workersStopped"))
            and type(result["controllerRevision"]) is int and result["controllerRevision"] >= 0
            and isinstance(result["clock"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", result["clock"]),
            "Controller did not confirm a paused idle fixed-run checkpoint boundary.")
    try:
        datetime.fromisoformat(result["clock"].replace("Z", "+00:00"))
    except ValueError:
        raise Refused("Controller checkpoint clock is not a valid UTC instant.") from None
    if action == "checkpoint":
        require(result["complete"] is True and isinstance(result["owners"], list) and
                all(isinstance(x, str) for x in result["owners"]) and
                set(cfg["ownerFiles"]) <= set(result["owners"]),
                "Checkpoint must include every connected owner, plus field when configured.")
        require(set(result["owners"]) <= {"runtime", "world", "catalog", "billing", "ledger", "evidence", "controller", "field", "producerField"},
                "Checkpoint must return only the defined owner identifiers.")
    print(json.dumps({key: result[key] for key in sorted(required)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate", "preflight", "initialize-volume", "up", "stop", "launch", "health", "pause", "checkpoint", "owner-pause"])
    parser.add_argument("role", nargs="?", choices=ROLES)
    parser.add_argument("--config", default=str(HERE / "deployment.json"))
    args = parser.parse_args()
    if args.action in ("launch", "health", "pause", "checkpoint", "owner-pause"):
        require(args.role, "Select the service role.")
        service(args.role, args.action)
        return
    cfg = validate_config(read_json(args.config))
    if args.action == "initialize-volume":
        initialize(cfg)
    elif args.action == "validate":
        pass
    else:
        if args.action == "stop":
            require(sys.platform.startswith("linux") and shutil.which("docker"), "Stop requires the Linux Docker host.")
            volume(cfg)
        else:
            preflight(cfg, args.config)
        if args.action == "up":
            compose(cfg, args.config, "up", "--detach", "--wait", "--wait-timeout", "120", "--force-recreate", "--no-build", "--pull", "never")
        elif args.action == "stop":
            compose(cfg, args.config, "stop", "--timeout", "120")
    print("Connected-stack check completed. No credential values displayed.")


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, TypeError, KeyError) as exc:
        message = str(exc) if isinstance(exc, Refused) else "Required configuration or executable operation is invalid."
        print("Refused: " + message, file=sys.stderr)
        raise SystemExit(2) from None
