"""Operator opt-in must preserve secret separation and existing CLI startup."""
import os
import stat
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import owners
import stack
from test_stack import fixture


def operator_fixture():
    cfg = fixture()
    cfg.update(operatorEnabled=True, recoveryMode="owner-cli-stopped/1")
    cfg["ownerCli"].update(controllerId="controller", worldId="world")
    cfg["services"]["controller"]["requiredSecrets"] = [
        "CONNECTED_SERVICE_TOKEN", "CONNECTED_CLOCK_TOKEN", "CONNECTED_OPERATOR_TOKEN"]
    cfg["services"]["producer"]["requiredSecrets"].append("UTILITYSIM_OPERATOR_TOKEN")
    return cfg


class OperatorTests(unittest.TestCase):
    def test_opt_in_requires_both_owner_capabilities(self):
        cfg = operator_fixture()
        stack.validate_config(cfg)
        cfg["services"]["producer"]["requiredSecrets"].remove("UTILITYSIM_OPERATOR_TOKEN")
        with self.assertRaises(stack.Refused):
            stack.validate_config(cfg)

    def test_secret_values_match_and_cannot_alias_other_capabilities(self):
        cfg = operator_fixture()
        values = {"producer": {"UTILITYSIM_OPERATOR_TOKEN": "o" * 40, "UTILITYSIM_MACHINE_KEY": "m" * 40},
                  "controller": {"CONNECTED_OPERATOR_TOKEN": "o" * 40, "CONNECTED_CLOCK_TOKEN": "c" * 40}}
        stack.operator_secrets(cfg, values)
        values["controller"]["CONNECTED_OPERATOR_TOKEN"] = "x" * 40
        with self.assertRaises(stack.Refused):
            stack.operator_secrets(cfg, values)
        values["controller"]["CONNECTED_OPERATOR_TOKEN"] = "o" * 40
        values["producer"]["UTILITYSIM_MACHINE_KEY"] = "o" * 40
        with self.assertRaises(stack.Refused):
            stack.operator_secrets(cfg, values)

    def test_cli_receives_protected_file_not_token_and_files_are_removed(self):
        cfg = operator_fixture()
        module = ModuleType("connected.__main__")
        files = []

        def start(command):
            self.assertNotIn("o" * 40, command)
            for option, value in (("--service-token-file", "s" * 40),
                                  ("--operator-token-file", "o" * 40)):
                path = Path(command[command.index(option) + 1])
                self.assertEqual(path.read_text(), value)
                if os.name == "posix":
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                files.append(path)
            return 7

        module.main = start
        with patch.dict("sys.modules", {"connected.__main__": module}), patch.dict(os.environ, {
                "CONNECTED_SERVICE_TOKEN": "s" * 40, "CONNECTED_CLOCK_TOKEN": "c" * 40,
                "CONNECTED_OPERATOR_TOKEN": "o" * 40}):
            self.assertEqual(owners.serve(cfg), 7)
        self.assertTrue(files)
        self.assertTrue(all(not path.exists() for path in files))

    def test_clock_alias_is_rejected_before_native_startup(self):
        cfg = operator_fixture()
        module = ModuleType("connected.__main__")
        module.main = lambda _: self.fail("Unsafe startup occurred")
        with patch.dict("sys.modules", {"connected.__main__": module}), patch.dict(os.environ, {
                "CONNECTED_SERVICE_TOKEN": "s" * 40, "CONNECTED_CLOCK_TOKEN": "o" * 40,
                "CONNECTED_OPERATOR_TOKEN": "o" * 40}):
            with self.assertRaises(stack.Refused):
                owners.serve(cfg)


if __name__ == "__main__":
    unittest.main()
