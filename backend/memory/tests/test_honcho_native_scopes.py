"""Tests for optional native Honcho scopes (T-A4-6, PR-A27).

No network and no ``honcho-ai`` import: every test drives a
``unittest.mock`` stand-in through the backend's ``_client`` test seam.
``honcho_migrate_scopes`` is exercised through ``call_command`` with the
backend factory patched, so the command's plan/report/write logic runs
unmodified while the SDK stays fake.
"""
import json
import logging
import re
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

import memory.honcho_backend as honcho_module
import memory.management.commands.honcho_migrate_scopes as migrate_module
from memory.honcho_backend import (
    HonchoMemoryBackend,
    _TRUTHY_VALUES,
    native_scope_id_for,
    scope_peer_id_for,
    scope_session_id_for,
    use_native_scopes,
)
from memory.models import MemoryEntry
from persistence.tests.factories import active_tenant, make_user, make_workspace

#: Honcho v3's id charset (workspaces/peers/scopes). Anything else is a 422.
_HONCHO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _conclusion(entry_id: str, content: str):
    """Minimal stand-in for honcho's ``Conclusion`` (only the fields we read)."""
    from types import SimpleNamespace

    return SimpleNamespace(id=entry_id, content=content, level="explicit")


def _mock_client():
    """SDK client double whose ``peer(id)`` returns a per-id mock.

    ``scope(id, metadata=...)`` is a plain ``MagicMock`` method, so a test can
    assert the derived scope id and ``scope().add_sessions([...])``, and make
    it raise to exercise the fail-open/error-counting paths.
    """
    from unittest import mock

    client = mock.MagicMock()
    peers: dict[str, mock.MagicMock] = {}

    def _peer(peer_id):
        if peer_id not in peers:
            peer = mock.MagicMock()
            peer.message.side_effect = lambda content, **kwargs: mock.MagicMock()
            peers[peer_id] = peer
        return peers[peer_id]

    client.peer.side_effect = _peer
    client.peers_by_id = peers
    return client


def _backend_with_mock_client():
    backend = HonchoMemoryBackend()
    client = _mock_client()
    backend._client = client
    return backend, client


def _forbid_backend_resolution():
    """Patch target for ``_resolve_backend`` in dry-run tests (F10).

    A *raiser*, not a working backend: building the real backend can already
    reach Honcho (settings resolution, client construction), so a dry-run test
    that returns a fake backend would pass even if the command started
    resolving one. This makes "a dry run never constructs a backend" an
    enforced property instead of an accident of the fixture.
    """
    raise AssertionError("a dry run must not construct a memory backend")


def _write_one_fact(backend, client, tenant, user):
    """Drive one real ``write`` so the session/scope path actually runs."""
    peer = client.peer(f"{tenant.id}_{user.id}")
    peer.conclusions.create.return_value = [_conclusion("nano1", "a fact")]
    # Configuring the double above is itself a ``client.peer`` call; drop it so
    # an assertion on the calls ``write`` makes stays honest.
    client.peer.reset_mock()
    return backend.write(tenant.id, "user", user.id, "a fact")


# ---------------------------------------------------------------------------
# Flag resolution
# ---------------------------------------------------------------------------


class TestNativeScopesFlag:
    """The flag is fail-safe: only an explicit truthy token enables scopes."""

    @pytest.mark.parametrize("value", ["", "0", "false", "False", "no", "off", "maybe"])
    def test_flag_off_for_every_non_truthy_value(self, monkeypatch, value):
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", value)
        assert use_native_scopes() is False

    def test_flag_off_when_unset(self, monkeypatch):
        monkeypatch.delenv("HONCHO_USE_NATIVE_SCOPES", raising=False)
        assert use_native_scopes() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " on "])
    def test_flag_on_for_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", value)
        assert use_native_scopes() is True


# ---------------------------------------------------------------------------
# Flag off: byte-identical peer/session naming, no scope traffic
# ---------------------------------------------------------------------------


class TestNativeScopesFlagOffKeepsPeerNaming:
    """The load-bearing property of the flag: OFF changes no id and no call."""

    @pytest.mark.django_db
    def test_native_scopes_flag_off_keeps_peer_naming(self, monkeypatch):
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "false")
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)

            _write_one_fact(backend, client, tenant, user)

            assert [c.args[0] for c in client.peer.call_args_list] == [
                f"{tenant.id}_{user.id}"
            ]
            assert client.session.call_args.args[0] == f"s_{tenant.id}_{user.id}"
            # Not a single scope route is touched while the flag is off.
            client.scope.assert_not_called()

    def test_native_scopes_flag_off_keeps_the_legacy_id_shape(self, monkeypatch):
        """Compared against the literal legacy f-strings, not against the
        resolver itself -- so a refactor cannot make this test tautological."""
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "false")
        tenant_id, user_id, workspace_id, artifact_id = uuid4(), uuid4(), uuid4(), uuid4()

        assert scope_peer_id_for(tenant_id, "user", user_id) == f"{tenant_id}_{user_id}"
        assert (
            scope_peer_id_for(tenant_id, "workspace", workspace_id)
            == f"{tenant_id}_{workspace_id}"
        )
        assert (
            scope_peer_id_for(tenant_id, "artifact", artifact_id)
            == f"{tenant_id}_a_{artifact_id}"
        )
        assert (
            scope_session_id_for(tenant_id, "user", user_id)
            == f"s_{tenant_id}_{user_id}"
        )

    def test_native_scopes_flag_on_never_changes_peer_or_session_ids(self, monkeypatch):
        """Same ids in both modes -- the flag only ADDS a scope object."""
        tenant_id, user_id = uuid4(), uuid4()
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "false")
        off = (
            scope_peer_id_for(tenant_id, "user", user_id),
            scope_session_id_for(tenant_id, "user", user_id),
        )
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "true")
        on = (
            scope_peer_id_for(tenant_id, "user", user_id),
            scope_session_id_for(tenant_id, "user", user_id),
        )
        assert off == on == (f"{tenant_id}_{user_id}", f"s_{tenant_id}_{user_id}")


# ---------------------------------------------------------------------------
# Flag on: the session is attached to its native scope
# ---------------------------------------------------------------------------


class TestNativeScopesFlagOn:
    @pytest.mark.django_db
    def test_flag_on_attaches_the_session_to_its_native_scope(self, monkeypatch):
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "true")
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)

            _write_one_fact(backend, client, tenant, user)

            expected_scope_id = f"reqogniloom_scope_{tenant.id}_{user.id}"
            client.scope.assert_called_once_with(
                expected_scope_id,
                metadata={
                    "reqogniloom_tenant_id": str(tenant.id),
                    "reqogniloom_scope": "user",
                    "reqogniloom_scope_id": str(user.id),
                },
            )
            client.scope.return_value.add_sessions.assert_called_once_with(
                [f"s_{tenant.id}_{user.id}"]
            )
            # The peer is still the legacy id: the flag adds, it never renames.
            assert [c.args[0] for c in client.peer.call_args_list] == [
                f"{tenant.id}_{user.id}"
            ]

    @pytest.mark.django_db
    def test_flag_on_attaches_only_once_per_scope(self, monkeypatch):
        """A batch write to the same scope must not re-issue the membership."""
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "true")
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            client.peer(f"{tenant.id}_{user.id}").conclusions.create.return_value = [
                _conclusion("nano1", "a fact")
            ]

            backend.write(tenant.id, "user", user.id, "a fact")
            client.peer(f"{tenant.id}_{user.id}").conclusions.create.return_value = [
                _conclusion("nano2", "another fact")
            ]
            backend.write(tenant.id, "user", user.id, "another fact")

            assert client.scope.call_count == 1

    @pytest.mark.django_db
    def test_flag_on_scope_failure_never_breaks_a_write(self, monkeypatch, caplog):
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "true")
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            client.scope.side_effect = RuntimeError("401 unauthorized")

            ref = _write_one_fact(backend, client, tenant, user)

            assert ref.backend_ref == "nano1"
            assert "a fact" not in caplog.text
            assert "native scope attach failed" in caplog.text

    @pytest.mark.django_db
    def test_flag_on_scope_id_error_never_swallows_the_message_publish(
        self, monkeypatch, caplog
    ):
        """F5: the memo key is resolved INSIDE the try.

        If ``scope_session_id_for`` raised outside it, the ``ValueError`` would
        escape into ``_publish_engine_message``'s handler and the Deriver would
        silently lose the observation. The session id used by the publish path
        is stubbed so ONLY the scope-attach key resolution raises.
        """
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "true")
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            monkeypatch.setattr(
                backend,
                "_scope_session_id",
                lambda *args: f"s_{tenant.id}_{user.id}",
            )

            def _boom(*args, **kwargs):
                raise ValueError("unknown memory scope: 'user'")

            monkeypatch.setattr(honcho_module, "scope_session_id_for", _boom)
            client.peer(f"{tenant.id}_{user.id}").conclusions.create.return_value = [
                _conclusion("nano1", "a fact")
            ]

            ref = backend.write(tenant.id, "user", user.id, "a fact")

            # The conclusion and the message both landed; only the scope
            # attach failed, and it failed quietly.
            assert ref.backend_ref == "nano1"
            client.session.return_value.add_messages.assert_called_once()
            client.scope.assert_not_called()
            assert "native scope attach failed" in caplog.text
            assert "a fact" not in caplog.text

    @pytest.mark.django_db
    def test_flag_on_repeated_scope_failure_warns_once_then_debugs(
        self, monkeypatch, caplog
    ):
        """F1: a permanent 401 must not log one WARNING per write forever."""
        monkeypatch.setenv("HONCHO_USE_NATIVE_SCOPES", "true")
        monkeypatch.setattr(honcho_module, "_native_scope_failure_warnings", {})
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            client.scope.side_effect = RuntimeError("401 unauthorized")

            with caplog.at_level(logging.DEBUG, logger="memory.honcho_backend"):
                for _ in range(3):
                    backend._native_scope_memberships.clear()
                    _write_one_fact(backend, client, tenant, user)

        levels = [
            record.levelno
            for record in caplog.records
            if "native scope attach failed" in record.getMessage()
        ]
        assert levels == [logging.WARNING, logging.DEBUG, logging.DEBUG]
        assert "a fact" not in caplog.text


class TestNativeScopeFailureWarningInterval:
    """F1: the per-process warning de-duplication is coarse, not permanent."""

    def test_scope_failure_warns_again_after_the_interval(self, monkeypatch, caplog):
        monkeypatch.setattr(honcho_module, "_native_scope_failure_warnings", {})
        monkeypatch.setattr(honcho_module, "_NATIVE_SCOPE_WARN_INTERVAL_SECONDS", 0.0)
        tenant_id, scope_id = uuid4(), uuid4()
        runtime_error = RuntimeError("401 unauthorized")

        with caplog.at_level(logging.DEBUG, logger="memory.honcho_backend"):
            honcho_module._warn_native_scope_attach_failure(
                tenant_id, "user", scope_id, runtime_error
            )
            honcho_module._warn_native_scope_attach_failure(
                tenant_id, "user", scope_id, runtime_error
            )

        levels = [
            record.levelno
            for record in caplog.records
            if "native scope attach failed" in record.getMessage()
        ]
        assert levels == [logging.WARNING, logging.WARNING]

    def test_a_different_exception_type_is_warned_separately(self, monkeypatch, caplog):
        """The de-duplication key includes the exception type."""
        monkeypatch.setattr(honcho_module, "_native_scope_failure_warnings", {})
        tenant_id, scope_id = uuid4(), uuid4()

        with caplog.at_level(logging.DEBUG, logger="memory.honcho_backend"):
            honcho_module._warn_native_scope_attach_failure(
                tenant_id, "user", scope_id, RuntimeError("401 unauthorized")
            )
            honcho_module._warn_native_scope_attach_failure(
                tenant_id, "user", scope_id, TimeoutError("5xx")
            )

        levels = [
            record.levelno
            for record in caplog.records
            if "native scope attach failed" in record.getMessage()
        ]
        assert levels == [logging.WARNING, logging.WARNING]


class TestNativeScopeId:
    @pytest.mark.parametrize("scope", ["user", "workspace", "artifact"])
    def test_native_scope_id_matches_honchos_charset_and_bounds(self, scope):
        tenant_id, scope_id = uuid4(), uuid4()
        native_id = native_scope_id_for(tenant_id, scope, scope_id)

        assert _HONCHO_ID_PATTERN.match(native_id)
        assert len(native_id) <= 506
        assert not native_id.startswith("scope.")
        assert str(tenant_id) in native_id and str(scope_id) in native_id

    def test_native_scope_id_rejects_an_unknown_scope(self):
        with pytest.raises(ValueError, match="unknown memory scope"):
            native_scope_id_for(uuid4(), "not-a-scope", uuid4())


# ---------------------------------------------------------------------------
# honcho_migrate_scopes
# ---------------------------------------------------------------------------


def _plan_line(stdout: StringIO) -> dict:
    """Parse the single-tenant JSON line the command emitted."""
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    assert lines, "the command emitted no report"
    return json.loads(lines[-1])


class TestMigrateScopesCommand:
    def _seed(self, tenant):
        """Two Honcho-mirrored scopes plus one pgvector-only row."""
        user = make_user(tenant)
        workspace = make_workspace(tenant)
        MemoryEntry.objects.create(
            tenant_id=tenant.id,
            scope="user",
            user_id=user.id,
            content="user fact",
            backend_ref="nano-user",
        )
        MemoryEntry.objects.create(
            tenant_id=tenant.id,
            scope="workspace",
            workspace_id=workspace.id,
            content="workspace fact",
            backend_ref="nano-workspace",
        )
        MemoryEntry.objects.create(
            tenant_id=tenant.id,
            scope="user",
            user_id=user.id,
            content="pgvector fact",
        )
        return user, workspace

    @pytest.mark.django_db
    def test_migrate_scopes_dry_run_reports_without_writing(self, monkeypatch):
        with active_tenant() as tenant:
            self._seed(tenant)
            # F10: a raiser, so this fails if the dry run ever resolves a
            # backend (constructing one can talk to Honcho).
            monkeypatch.setattr(
                migrate_module, "_resolve_backend", _forbid_backend_resolution
            )

            stdout = StringIO()
            call_command(
                "honcho_migrate_scopes", "--tenant", str(tenant.id), stdout=stdout
            )
            line = _plan_line(stdout)

            assert line["dry_run"] is True
            assert line["planned_scopes"] == 2
            assert line["planned_entries"] == 2
            # The pgvector row (backend_ref NULL) has no Honcho session.
            assert line["skipped_entries"] == 1
            assert line["written_scopes"] == 0
            assert line["failed"] == 0
            assert {item["scope"] for item in line["scopes"]} == {"user", "workspace"}
            for item in line["scopes"]:
                assert item["native_scope_id"].startswith("reqogniloom_scope_")
                assert item["session_id"].startswith("s_")

    @pytest.mark.django_db
    def test_migrate_scopes_defaults_to_dry_run_without_any_flag(self, monkeypatch):
        """No counter-flag == no approval == no write, even with no --dry-run."""
        with active_tenant() as tenant:
            self._seed(tenant)
            # F10: see the dry-run test above -- no backend may be constructed.
            monkeypatch.setattr(
                migrate_module, "_resolve_backend", _forbid_backend_resolution
            )

            stdout = StringIO()
            call_command("honcho_migrate_scopes", "--tenant", str(tenant.id), stdout=stdout)
            line = _plan_line(stdout)

            assert line["dry_run"] is True
            assert line["planned_scopes"] == 2
            assert line["written_scopes"] == 0

    @pytest.mark.django_db
    def test_migrate_scopes_apply_creates_scopes_and_attaches_sessions(self, monkeypatch):
        with active_tenant() as tenant:
            user, workspace = self._seed(tenant)
            backend, client = _backend_with_mock_client()
            monkeypatch.setattr(migrate_module, "_resolve_backend", lambda: backend)

            stdout = StringIO()
            call_command(
                "honcho_migrate_scopes",
                "--tenant",
                str(tenant.id),
                "--no-dry-run",
                stdout=stdout,
            )
            line = _plan_line(stdout)

            assert line["dry_run"] is False
            assert line["written_scopes"] == 2
            assert line["failed"] == 0
            # Sorted by (scope, scope_id): "user" before "workspace".
            assert client.scope.call_count == 2
            attached = [
                c.args[0] for c in client.scope.return_value.add_sessions.call_args_list
            ]
            assert attached == [
                [f"s_{tenant.id}_{user.id}"],
                [f"s_{tenant.id}_{workspace.id}"],
            ]

    @pytest.mark.django_db
    def test_migrate_scopes_apply_counts_failures_and_exits_non_zero(self, monkeypatch):
        with active_tenant() as tenant:
            self._seed(tenant)
            backend, client = _backend_with_mock_client()
            client.scope.side_effect = RuntimeError("401 unauthorized")
            monkeypatch.setattr(migrate_module, "_resolve_backend", lambda: backend)

            stdout = StringIO()
            with pytest.raises(CommandError, match="401 usually means"):
                call_command(
                    "honcho_migrate_scopes",
                    "--tenant",
                    str(tenant.id),
                    "--no-dry-run",
                    stdout=stdout,
                )
            line = _plan_line(stdout)
            assert line["written_scopes"] == 0
            assert line["failed"] == 2
            assert line["failures"] == {"RuntimeError": 2}

    def test_migrate_scopes_apply_requires_the_honcho_backend(self, monkeypatch):
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        with pytest.raises(CommandError, match="MEMORY_BACKEND=honcho"):
            call_command("honcho_migrate_scopes", "--no-dry-run")

    @pytest.mark.django_db
    def test_migrate_scopes_rejects_an_unknown_tenant(self, monkeypatch):
        """F6: a valid-looking but nonexistent tenant must not report green.

        Before this guard ``--tenant <uuid4>`` produced ``planned_scopes: 0``
        and exit 0, which reads as "nothing to migrate" for a typo'd id.
        """
        monkeypatch.setattr(
            migrate_module, "_resolve_backend", _forbid_backend_resolution
        )
        unknown = uuid4()

        with pytest.raises(CommandError, match=rf"unknown tenant {unknown}"):
            call_command("honcho_migrate_scopes", "--tenant", str(unknown))

    @pytest.mark.django_db
    def test_report_documents_the_key_and_observer_constraints(self, monkeypatch):
        with active_tenant() as tenant:
            self._seed(tenant)
            backend, _client = _backend_with_mock_client()
            monkeypatch.setattr(migrate_module, "_resolve_backend", lambda: backend)

            stdout = StringIO()
            call_command("honcho_migrate_scopes", "--tenant", str(tenant.id), stdout=stdout)
            notes = " ".join(_plan_line(stdout)["notes"])

            assert "workspace-scoped or admin" in notes
            assert "not an observer" in notes
            assert "dream target" in notes


# ---------------------------------------------------------------------------
# Shipped-configuration guard (F12)
# ---------------------------------------------------------------------------

#: Repository root, derived from this file's location
#: (``backend/memory/tests/test_honcho_native_scopes.py``). Inside the test
#: container only ``./backend`` and ``./docs`` are bind-mounted, so the
#: root-level files this guard reads exist on a host checkout / in CI (which
#: runs pytest from a full ``backend/`` checkout) but not in the container.
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: ``HONCHO_USE_NATIVE_SCOPES`` followed by whatever maps it to a value:
#: ``NAME=value`` (.env), ``NAME: value`` (YAML), ``NAME", "value"``
#: (``os.environ.setdefault``) and ``NAME"] = "value"`` (item assignment).
#: The captured group is the value token, if any; ``${NAME:-false}`` therefore
#: reads as one non-truthy token, which is what Compose would substitute, and an
#: empty assignment (``NAME=``) captures ``""`` -- deliberately not truthy.
_FLAG_ASSIGNMENT = re.compile(
    r"""HONCHO_USE_NATIVE_SCOPES["']?\s*[\]:,]?\s*[:=]?\s*["']?([^\s"'#=,][^\s"'#,]*)?"""
)


def _required_config_paths():
    """The root-level paths that only exist on a full checkout."""
    return [
        _REPO_ROOT / ".env.example",
        _REPO_ROOT / "deploy",
        _REPO_ROOT / "testing",
        _REPO_ROOT / "backend" / "reqogniloom",
    ]


def _require_repo_checkout() -> None:
    """Skip (per test) when the host-only checkout is not mounted.

    Same convention as ``test_honcho_deploy_contract.py``: the guard asserts on
    the checkout, not on the deployed image, so a missing mount skips instead of
    erroring -- while CI (full checkout) still runs it for real.
    """
    missing = [str(path) for path in _required_config_paths() if not path.exists()]
    if missing:
        pytest.skip(
            "shipped-configuration guard needs the repository checkout; not "
            f"present in this environment: {missing}"
        )


def _shipped_config_files():
    """Every file whose content can switch the flag on in a deployment."""
    files = [_REPO_ROOT / ".env.example"]
    files += sorted((_REPO_ROOT / "deploy").glob("*.yml"))
    files += sorted((_REPO_ROOT / "testing").glob("*.yml"))
    files += sorted((_REPO_ROOT / "backend" / "reqogniloom").glob("settings*.py"))
    # 10 today: .env.example + 6 deploy/*.yml + 1 testing/*.yml + 2 settings*.py
    assert len(files) >= 10, f"config discovery found too few files: {files}"
    return files


class TestNoShippedConfigurationEnablesNativeScopes:
    """F12: the flag must stay OFF in every shipped configuration."""

    def test_no_shipped_configuration_enables_the_flag(self):
        _require_repo_checkout()
        offenders = []
        for path in _shipped_config_files():
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                # A commented-out line cannot configure anything -- the .env
                # and Compose files document the rollout in comments.
                if line.lstrip().startswith("#"):
                    continue
                for value in _FLAG_ASSIGNMENT.findall(line):
                    if value.strip().strip("'\"").lower() in _TRUTHY_VALUES:
                        offenders.append(f"{path.relative_to(_REPO_ROOT)}:{number}")
        assert offenders == [], (
            "HONCHO_USE_NATIVE_SCOPES is enabled in shipped configuration "
            f"(must stay off by default): {offenders}"
        )

    def test_env_example_documents_the_flag_as_off(self):
        """F9: the variable is documented, and documented as EMPTY (off)."""
        _require_repo_checkout()
        text = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "\nHONCHO_USE_NATIVE_SCOPES=\n" in text
        for step in (
            "honcho_migrate_scopes --dry-run",
            "honcho_migrate_scopes --apply",
            "explicit user approval",
            "workspace-scoped or admin",
        ):
            assert step in text
