"""Tests for the multi-server registry.

Run: python -m pytest tests/test_registry.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


registry = _load("reqogniloom_registry_under_test", _PLUGIN_ROOT / "reqogniloom_registry.py")


class FakeClient:
    """Minimal stand-in for ``ReqogniLoomClient`` (only what probing needs)."""

    def __init__(self, *, version_ok: bool = True, tools_ok: bool = True, tools: int = 248) -> None:
        self.version_ok = version_ok
        self.tools_ok = tools_ok
        self.tools = tools
        self.api_key_seen: list = []

    def version(self):
        if not self.version_ok:
            raise RuntimeError("connection refused")
        return {"version": "1.8.0-beta.21"}

    def tools_list(self, *, api_key=None):
        self.api_key_seen.append(api_key)
        if not self.tools_ok:
            raise RuntimeError("PERMISSION_DENIED")
        return [{"name": f"tool.{i}"} for i in range(self.tools)]


class RegistryFileTests(unittest.TestCase):
    def test_missing_file_reads_as_empty(self) -> None:
        self.assertEqual(registry.load_registry()["servers"], [])
        self.assertTrue(registry.write_gate_enabled())

    def test_corrupt_file_reads_as_empty_and_is_kept(self) -> None:
        path = registry.registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(registry.load_registry()["servers"], [])
        self.assertTrue(path.with_suffix(".json.bad").exists())

    def test_saved_file_is_owner_only(self) -> None:
        registry.save_registry(registry._empty_registry())
        mode = stat.S_IMODE(registry.registry_path().stat().st_mode)
        self.assertEqual(mode, 0o600, f"registry file mode {oct(mode)} is not 0600")

    def test_registry_path_follows_hermes_home(self) -> None:
        # conftest sets HERMES_HOME per test; the path must resolve under it.
        home = Path(os.environ["HERMES_HOME"])
        self.assertEqual(registry.registry_path(), home / "reqogniloom" / "servers.json")


class MigrationTests(unittest.TestCase):
    def test_env_seeds_one_entry_without_copying_a_secret(self) -> None:
        with patch.dict(
            os.environ,
            {"REQOGNILOOM_BASE_URL": "http://qs.test:8001", "REQOGNILOOM_API_KEY": "reqlo_secret"},
        ):
            migrated = registry.ensure_migrated()
        self.assertEqual(migrated["active"], registry.DEFAULT_SERVER_ID)
        entry = migrated["servers"][0]
        self.assertEqual(entry["base_url"], "http://qs.test:8001")
        self.assertEqual(entry["api_key_source"], "env")
        self.assertEqual(entry["api_key_env"], "REQOGNILOOM_API_KEY")
        raw = registry.registry_path().read_text(encoding="utf-8")
        self.assertNotIn("reqlo_secret", raw, "migration must not copy the key into the file")

    def test_base_url_only_migration_creates_keyless_entry(self) -> None:
        with patch.dict(os.environ, {"REQOGNILOOM_BASE_URL": "http://qs.test:8001"}):
            migrated = registry.ensure_migrated()
        entry = migrated["servers"][0]
        self.assertEqual(entry["api_key_source"], "none")
        self.assertIsNone(registry.public_server(entry)["has_api_key"] or None)

    def test_no_env_creates_an_empty_registry(self) -> None:
        migrated = registry.ensure_migrated()
        self.assertEqual(migrated["servers"], [])
        self.assertIsNone(migrated["active"])
        self.assertTrue(registry.registry_path().exists())

    def test_migration_is_idempotent_and_never_overwrites(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        with patch.dict(os.environ, {"REQOGNILOOM_BASE_URL": "http://other.test:8001"}):
            migrated = registry.ensure_migrated()
        self.assertEqual([s["id"] for s in migrated["servers"]], ["qs"])

    def test_invalid_env_base_url_is_ignored_not_fatal(self) -> None:
        with patch.dict(os.environ, {"REQOGNILOOM_BASE_URL": "ftp://nope"}):
            migrated = registry.ensure_migrated()
        self.assertEqual(migrated["servers"], [])


class ValidationTests(unittest.TestCase):
    def test_server_id_must_be_narrow(self) -> None:
        for bad in ("", "Has Space", "UPPER ok?", "-leading", "x" * 33, "punkt.zeichen"):
            with self.subTest(bad=bad), self.assertRaises(registry.RegistryError):
                registry.validate_server_id(bad)

    def test_server_id_is_normalised_to_lowercase(self) -> None:
        self.assertEqual(registry.validate_server_id("  QS-1 "), "qs-1")

    def test_base_url_requires_http_scheme(self) -> None:
        with self.assertRaises(registry.RegistryError):
            registry.validate_base_url("localhost:8001")

    def test_base_url_loses_the_trailing_slash(self) -> None:
        self.assertEqual(registry.validate_base_url("http://qs.test:8001/"), "http://qs.test:8001")


class ServerCrudTests(unittest.TestCase):
    def test_add_activates_the_first_server(self) -> None:
        added = registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_a")
        self.assertEqual(added["active"], "qs")
        self.assertTrue(registry.public_registry(added)["servers"][0]["active"])

    def test_second_server_does_not_steal_the_active_slot(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        added = registry.add_server("prod", "http://prod.test:8001")
        self.assertEqual(added["active"], "qs")

    def test_add_with_activate_switches(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        added = registry.add_server("prod", "http://prod.test:8001", activate=True)
        self.assertEqual(added["active"], "prod")

    def test_duplicate_id_is_rejected(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        with self.assertRaises(registry.RegistryError):
            registry.add_server("QS", "http://other.test:8001")

    def test_unknown_server_lookup_names_what_exists(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        with self.assertRaises(registry.RegistryError) as ctx:
            registry.get_server("nope")
        self.assertIn("qs", str(ctx.exception))

    def test_update_switches_between_file_and_env_key_source(self) -> None:
        registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_old")
        updated = registry.update_server("qs", api_key_env="REQOGNILOOM_API_KEY_QS")
        entry = registry.get_server("qs")
        self.assertEqual(entry["api_key_source"], "env")
        self.assertIsNone(entry["api_key"], "switching to env must drop the stored key")
        self.assertEqual(updated["servers"][0]["api_key_env"], "REQOGNILOOM_API_KEY_QS")

    def test_update_can_clear_a_key(self) -> None:
        registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_old")
        registry.update_server("qs", api_key="")
        entry = registry.get_server("qs")
        self.assertEqual(entry["api_key_source"], "none")
        self.assertIsNone(entry["api_key"])

    def test_remove_repoints_active_to_first_survivor(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        registry.add_server("prod", "http://prod.test:8001")
        updated = registry.remove_server("qs")
        self.assertEqual(updated["active"], "prod")

    def test_remove_last_server_clears_active(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        updated = registry.remove_server("qs")
        self.assertIsNone(updated["active"])
        self.assertIsNone(registry.active_server(updated))

    def test_set_active_requires_a_known_server(self) -> None:
        with self.assertRaises(registry.RegistryError):
            registry.set_active("ghost")

    def test_active_server_is_unambiguous_for_a_single_entry(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        registry.update_registry(lambda reg: {**reg, "active": None})
        entry = registry.active_server()
        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "qs")


class CredentialTests(unittest.TestCase):
    def test_file_key_is_returned(self) -> None:
        registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_file")
        entry = registry.get_server("qs")
        self.assertEqual(registry.resolve_credentials(entry), ("reqlo_file", None))

    def test_env_key_wins_and_is_read_at_call_time(self) -> None:
        registry.add_server("qs", "http://qs.test:8001", api_key_env="REQOGNILOOM_API_KEY_QS")
        entry = registry.get_server("qs")
        self.assertEqual(registry.resolve_credentials(entry), (None, None))
        with patch.dict(os.environ, {"REQOGNILOOM_API_KEY_QS": "reqlo_rotated"}):
            self.assertEqual(registry.resolve_credentials(entry)[0], "reqlo_rotated")

    def test_human_key_is_resolved_separately(self) -> None:
        registry.add_server(
            "qs",
            "http://qs.test:8001",
            api_key="reqlo_agent",
            user_api_key="reqlo_human",
        )
        api_key, user_key = registry.resolve_credentials(registry.get_server("qs"))
        self.assertEqual((api_key, user_key), ("reqlo_agent", "reqlo_human"))

    def test_public_view_never_contains_key_values(self) -> None:
        registry.add_server(
            "qs", "http://qs.test:8001", api_key="reqlo_agent", user_api_key="reqlo_human"
        )
        payload = json.dumps(registry.public_registry())
        self.assertNotIn("reqlo_agent", payload)
        self.assertNotIn("reqlo_human", payload)
        view = registry.public_registry()["servers"][0]
        self.assertTrue(view["has_api_key"])
        self.assertTrue(view["has_user_api_key"])
        self.assertEqual(view["api_key_source"], "file")


class WriteGateTests(unittest.TestCase):
    def test_gate_defaults_to_enabled(self) -> None:
        self.assertTrue(registry.write_gate_enabled())

    def test_gate_can_be_closed_and_reopened(self) -> None:
        registry.set_write_gate(False)
        self.assertFalse(registry.write_gate_enabled())
        registry.set_write_gate(True)
        self.assertTrue(registry.write_gate_enabled())


class WorkspaceMemoryTests(unittest.TestCase):
    def test_workspace_is_remembered_per_server(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        registry.add_server("prod", "http://prod.test:8001")
        registry.remember_workspace("qs", "ws-qs")
        registry.remember_workspace("prod", "ws-prod")
        self.assertEqual(registry.get_server("qs")["last_workspace_id"], "ws-qs")
        self.assertEqual(registry.get_server("prod")["last_workspace_id"], "ws-prod")

    def test_unknown_server_is_ignored_not_fatal(self) -> None:
        registry.remember_workspace("ghost", "ws-1")  # must not raise


class ProbeTests(unittest.TestCase):
    def test_healthy_server_reports_version_and_tool_count(self) -> None:
        client = FakeClient()
        verify = registry.probe_server(
            client, {"id": "qs", "base_url": "http://qs.test:8001", "api_key": "reqlo_agent"}
        )
        self.assertTrue(verify["reachable"])
        self.assertTrue(verify["auth_ok"])
        self.assertEqual(verify["app_version"], "1.8.0-beta.21")
        self.assertEqual(verify["tool_count"], 248)

    def test_unreachable_server_is_reported_as_such(self) -> None:
        verify = registry.probe_server(
            FakeClient(version_ok=False),
            {"id": "qs", "base_url": "http://qs.test:8001", "api_key": "reqlo_agent"},
        )
        self.assertFalse(verify["reachable"])
        self.assertFalse(verify["auth_ok"])
        self.assertIn("connection refused", verify["error"])

    def test_bad_key_is_distinguished_from_down_server(self) -> None:
        verify = registry.probe_server(
            FakeClient(tools_ok=False),
            {"id": "qs", "base_url": "http://qs.test:8001", "api_key": "reqlo_agent"},
        )
        self.assertTrue(verify["reachable"], "reachability comes from the public version call")
        self.assertFalse(verify["auth_ok"])
        self.assertIn("PERMISSION_DENIED", verify["error"])

    def test_missing_key_names_the_entry_not_the_global_variable(self) -> None:
        # Without a credential of its own, the probe must not forward the client's
        # global message ("export REQOGNILOOM_API_KEY") — on a multi-server install
        # that names the wrong lever and hides the real gap.
        client = FakeClient()
        verify = registry.probe_server(client, {"id": "qs", "base_url": "http://qs.test:8001"})
        self.assertTrue(verify["reachable"])
        self.assertFalse(verify["auth_ok"])
        self.assertIn("no credential configured for server 'qs'", verify["error"])
        self.assertEqual(client.api_key_seen, [], "no tools/list call without a credential")

    def test_probe_uses_the_entry_key(self) -> None:
        client = FakeClient()
        registry.probe_server(
            client, {"id": "qs", "base_url": "http://qs.test:8001", "api_key": "reqlo_agent"}
        )
        self.assertEqual(client.api_key_seen, ["reqlo_agent"])

    def test_record_verify_stores_the_outcome(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        registry.record_verify("qs", {"reachable": True, "app_version": "1.8.0-beta.21"})
        view = registry.public_registry()["servers"][0]
        self.assertEqual(view["verify"]["app_version"], "1.8.0-beta.21")


class FormatTests(unittest.TestCase):
    def test_empty_registry_explains_how_to_configure_one(self) -> None:
        text = registry.format_servers()
        self.assertIn("server add", text)
        self.assertIn("REQOGNILOOM_BASE_URL", text)

    def test_listing_marks_the_active_server(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        registry.add_server("prod", "http://prod.test:8001")
        registry.set_active("prod")
        text = registry.format_servers()
        active_line = [line for line in text.splitlines() if line.strip().startswith("*")]
        self.assertEqual(len(active_line), 1)
        self.assertIn("prod", active_line[0])

class KeyEnvPolicyTests(unittest.TestCase):
    """Credentials are only ever read from variables the plugin owns.

    Without this rule the server panel becomes an environment-variable
    exfiltration channel: an entry names ``AWS_SECRET_ACCESS_KEY`` as its
    ``api_key_env`` and the next health probe sends that value as ``X-API-Key``
    to whatever ``base_url`` the same request supplied.
    """

    def test_a_foreign_variable_is_refused_when_writing(self) -> None:
        for bad in ("AWS_SECRET_ACCESS_KEY", "PATH", "REQOGNILOOM_BASE_URL", "reqogniloom_api_key"):
            with self.subTest(name=bad):
                with self.assertRaises(registry.RegistryError):
                    registry.add_server("qs", "http://qs.test:8001", api_key_env=bad)

    def test_a_foreign_variable_is_refused_on_update(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        with self.assertRaises(registry.RegistryError):
            registry.update_server("qs", user_api_key_env="PATH")

    def test_own_variables_are_accepted(self) -> None:
        self.assertEqual(registry.validate_key_env("REQOGNILOOM_API_KEY_QS"), "REQOGNILOOM_API_KEY_QS")
        self.assertEqual(registry.validate_key_env("REQOGNILOOM_USER_API_KEY"), "REQOGNILOOM_USER_API_KEY")
        self.assertIsNone(registry.validate_key_env(""))

    def test_a_hand_edited_file_with_a_foreign_name_yields_no_credential(self) -> None:
        # The file is editable by whoever can reach it, so the reading path has to
        # apply the same rule — without raising, which would turn a config mistake
        # into "server unreachable".
        entry = {
            "id": "qs",
            "base_url": "http://qs.test:8001",
            "api_key_source": "env",
            "api_key_env": "AWS_SECRET_ACCESS_KEY",
        }
        os.environ["AWS_SECRET_ACCESS_KEY"] = "TOP-EXFIL"
        self.addCleanup(os.environ.pop, "AWS_SECRET_ACCESS_KEY", None)
        self.assertEqual(registry.resolve_credentials(entry), (None, None))


class FileModeTests(unittest.TestCase):
    """The directory and the file that hold every credential."""

    def test_registry_directory_is_private_and_file_is_0600(self) -> None:
        registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_agent")
        path = registry.registry_path()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_no_temp_file_survives_a_write(self) -> None:
        registry.add_server("qs", "http://qs.test:8001")
        leftovers = [item.name for item in registry.registry_path().parent.glob("*.tmp")]
        self.assertEqual(leftovers, [])

    def test_a_stale_temp_file_does_not_block_the_next_write(self) -> None:
        # A writer that died between create and replace leaves a file whose name
        # carries its pid+thread; without cleanup every later write would fail.
        registry.add_server("qs", "http://qs.test:8001")
        path = registry.registry_path()
        stale = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        stale.write_text("{}", encoding="utf-8")
        registry.add_server("prod", "http://prod.test:8001")
        self.assertEqual([s["id"] for s in registry.public_registry()["servers"]], ["qs", "prod"])


class BaseUrlPolicyTests(unittest.TestCase):
    """A URL is where a credential goes, so it is checked as such."""

    def test_metadata_and_link_local_targets_are_refused(self) -> None:
        for bad in (
            "http://169.254.169.254",
            "http://metadata.google.internal",
            "http://0.0.0.0:8001",
        ):
            with self.subTest(url=bad):
                with self.assertRaises(registry.RegistryError):
                    registry.add_server("qs", bad)

    def test_private_lan_targets_stay_allowed(self) -> None:
        # The normal case for this plugin: a ReqogniLoom install on a LAN.
        for index, good in enumerate(
            ("http://172.20.5.120:8001", "http://10.0.0.5:8001", "http://localhost:8001")
        ):
            with self.subTest(url=good):
                registry.add_server(f"lan{index}", good)
        self.assertEqual(len(registry.public_registry()["servers"]), 3)

    def test_changing_the_url_clears_the_keys_of_that_entry(self) -> None:
        registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_agent", user_api_key="reqlo_human")
        registry.update_server("qs", base_url="http://other.test:8001")
        entry = registry.get_server("qs")
        self.assertIsNone(entry["api_key"])
        self.assertIsNone(entry["user_api_key"])
        self.assertEqual(entry["api_key_source"], "none")
        self.assertEqual(registry.resolve_credentials(entry), (None, None))

    def test_rewriting_the_same_url_keeps_the_keys(self) -> None:
        registry.add_server("qs", "http://qs.test:8001", api_key="reqlo_agent")
        registry.update_server("qs", base_url="http://qs.test:8001/")
        self.assertEqual(registry.get_server("qs")["api_key"], "reqlo_agent")


class ActiveFlagTests(unittest.TestCase):
    def test_the_only_server_counts_as_active_even_without_a_pointer(self) -> None:
        # A hand-written or restored registry has no `active` pointer; the resolver
        # still commits to that single server, so the UI must show it as active.
        entry = dict(registry._new_entry("qs", "qs", base_url="http://qs.test:8001"))
        registry.save_registry(
            {
                "registry_version": 1,
                "active": None,
                "write_gate": True,
                "servers": [entry],
            }
        )
        view = registry.public_registry()["servers"][0]
        self.assertTrue(view["active"])
        self.assertEqual(registry.active_server()["id"], "qs")
