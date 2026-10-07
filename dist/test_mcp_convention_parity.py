"""Provider-parity guard for the MCP client configuration `dist/` ships.

One convention, four builders, four generated artifacts -- and until now
nothing tied them to each other beyond a per-builder smoke test that asserted
whatever that builder happened to emit that week. This module pins the
convention the *backend* implements, so a future edit that reintroduces a
different env-var prefix, or an auth header the server does not read, fails
here instead of at a user's `claude plugin install`.

What the backend accepts (the backend wins; the `dist/` side must follow):

* the key prefix is ``reqlo_`` (``_API_KEY_PLAINTEXT_PREFIX`` in
  ``backend/auth_tenancy/rest.py``), and MCP additionally *requires* it -- a
  JWT carried in ``Authorization: Bearer`` is rejected with
  ``bearer_not_supported`` (``backend/mcp_server/tool_registry.py``);
* two transports carry that key: ``X-API-Key`` and ``Authorization: Bearer``
  (the two branches of the REST authenticator, mirrored by
  ``TransportAdapter._extract_api_key`` in
  ``backend/mcp_server/protocol_handler.py``).

Codex's snippet uses the Bearer transport and ships no ``headers`` at all.
That is deliberate, not an oversight: Codex's Streamable-HTTP transport offers
only ``bearer_token_env_var`` and has no custom-header mechanism, so the same
key travels over the other of the two accepted transports. It is pinned as
intentional by `test_codex_bearer_shape_is_intentional` below so nobody
"fixes" it to ``X-API-Key``.

Every invariant is checked twice -- against a fresh build, and against the
committed artifact on disk. `dist/test_full_regeneration.py` already
byte-compares those two against each other; asserting the convention on both
legs is deliberate defence in depth, so this file stands on its own as the
parity guard even if that pipeline test is reworked.
"""
import importlib.util
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest

DIST_DIR = Path(__file__).resolve().parent
REPO_ROOT = DIST_DIR.parent
SERVER_NAME: Final = "reqogniloom"

#: Prefix of every env var a shipped client config interpolates. Matches the
#: names documented in docs/agent-templates/INSTALL.md.
CANONICAL_ENV_PREFIX: Final = "REQOGNILOOM_"

#: A competing prefix that exists only in the `.agent-meta` submodule
#: (`config/plugin-catalog.yaml`, regenerated into `.agent-meta/opencode.json`).
#: Nothing in this repo reads it, so a config that interpolates it is broken.
#: Spelled out here so the guard names the exact regression it exists for.
NON_CANONICAL_ENV_PREFIX: Final = "MCP_REQOGNILOOM_"

#: The two ways the ReqogniLoom backend accepts a ``reqlo_`` API key, and the
#: only two. A package that reaches for anything else authenticates nobody.
ACCEPTED_AUTH_TRANSPORTS: Final[frozenset[str]] = frozenset(
    {
        "X-API-Key",  # REST authenticator + MCP protocol_handler
        "Authorization: Bearer",  # MCP protocol_handler Bearer branch (reqlo_ only)
    }
)
BEARER_TRANSPORT: Final = "Authorization: Bearer"

#: Header names the backend actually reads, derived from the transports above
#: so there is exactly one allow-list to keep current.
ACCEPTED_AUTH_HEADERS: Final[frozenset[str]] = frozenset(
    transport.partition(":")[0] for transport in ACCEPTED_AUTH_TRANSPORTS
)

#: Headers that appear in the submodule's connection block and in nothing else.
#: The backend has zero production reads of them
#: (docs/se/reports/deep_audit/.../09-evidence-register.md, CR-22), so shipping
#: them is dead weight that looks like configuration.
DEAD_WEIGHT_HEADERS: Final[frozenset[str]] = frozenset(
    {"X-Project-ID", "X-User-ID", "X-Workspace-ID"}
)

API_KEY_ENV_VAR: Final = f"{CANONICAL_ENV_PREFIX}API_KEY"
MCP_URL_ENV_VAR: Final = f"{CANONICAL_ENV_PREFIX}MCP_URL"

#: The plaintext prefix of a ReqogniLoom API key, per the backend.
API_KEY_PREFIX: Final = "reqlo_"

# `${NAME}` (Claude Code, Antigravity) and `{env:NAME}` (OpenCode).
_ENV_REF_RE: Final = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\{env:([A-Za-z_][A-Za-z0-9_]*)\}"
)
_EXACT_ENV_REF_RE: Final = re.compile(
    r"^(?:\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\{env:([A-Za-z_][A-Za-z0-9_]*)\})$"
)


@dataclass(frozen=True)
class BuilderSpec:
    """Where a builder lives, what it renders, and where that render is kept."""

    name: str
    module_path: Path
    out_subpath: str
    committed_path: Path
    container: str
    fmt: str = "json"


CONFIG_BUILDERS: Final[tuple[BuilderSpec, ...]] = (
    BuilderSpec(
        name="claude-code",
        module_path=DIST_DIR / "plugins/claude-code/build_claude_plugin.py",
        out_subpath="reqogniloom/.mcp.json",
        committed_path=Path("dist/plugins/claude-code/reqogniloom/.mcp.json"),
        container="mcpServers",
    ),
    BuilderSpec(
        name="antigravity",
        module_path=(
            DIST_DIR / "plugins/antigravity/build_antigravity_plugin.py"
        ),
        out_subpath="reqogniloom/mcp_config.json",
        committed_path=(
            Path("dist/plugins/antigravity/reqogniloom/mcp_config.json")
        ),
        container="mcpServers",
    ),
    BuilderSpec(
        name="opencode",
        module_path=DIST_DIR / "opencode/build_opencode_package.py",
        out_subpath="opencode.json.snippet",
        committed_path=Path("dist/opencode/opencode.json.snippet"),
        container="mcp",
    ),
    BuilderSpec(
        name="codex",
        module_path=DIST_DIR / "codex/build_codex_package.py",
        out_subpath="config.toml.snippet",
        committed_path=Path("dist/codex/config.toml.snippet"),
        container="mcp_servers",
        fmt="toml",
    ),
)

@dataclass(frozen=True)
class ParityCase:
    """One (builder, origin) pair: the same invariant, checked on both the
    fresh build and the committed artifact."""

    spec: BuilderSpec
    origin: str


ORIGIN_BUILT: Final = "built"
ORIGIN_COMMITTED: Final = "committed"

_PARITY_CASES: Final = [
    ParityCase(spec, origin)
    for spec in CONFIG_BUILDERS
    for origin in (ORIGIN_BUILT, ORIGIN_COMMITTED)
]


@dataclass(frozen=True)
class EmittedServer:
    """The auth-relevant projection of one generated MCP server entry."""

    builder: str
    origin: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    bearer_token_env_var: str | None = None
    #: Every string in the parsed entry. Comments are already gone, so the
    #: documented `reqlo_...` hint in the Codex snippet cannot mask a literal.
    leaves: frozenset[str] = frozenset()

    @property
    def transports(self) -> set[str]:
        """The accepted-transport names this entry carries its key over.

        A ``bearer_token_env_var`` is Codex's only way to send a key, and it
        resolves to ``Authorization: Bearer`` client-side -- the key never
        appears in the config, only the name of the var holding it.
        """
        found: set[str] = set()
        if self.bearer_token_env_var is not None:
            found.add(BEARER_TRANSPORT)
        if "Authorization" in self.headers:
            found.add(BEARER_TRANSPORT)
        if "X-API-Key" in self.headers:
            found.add("X-API-Key")
        return found

    def env_refs(self) -> set[str]:
        """Every env-var name this entry interpolates, across both syntaxes."""
        names = set(env_refs(self.url))
        for value in self.headers.values():
            names |= env_refs(value)
        if self.bearer_token_env_var is not None:
            names.add(self.bearer_token_env_var)
        return names

    def key_values(self) -> dict[str, str]:
        """Emitted values that carry the API key, keyed by where they sit."""
        values = {
            f"headers[{name}]": value
            for name, value in self.headers.items()
            if API_KEY_ENV_VAR in value
        }
        if self.bearer_token_env_var is not None:
            values["bearer_token_env_var"] = self.bearer_token_env_var
        return values


def env_refs(value: str) -> set[str]:
    """Every env-var name `value` references, in either interpolation syntax."""
    return {dollar or brace for dollar, brace in _ENV_REF_RE.findall(value)}


def _string_leaves(value: Any) -> set[str]:
    """Every string in a parsed config, with parser-dropped comments excluded."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {leaf for item in value.values() for leaf in _string_leaves(item)}
    if isinstance(value, list):
        return {leaf for item in value for leaf in _string_leaves(item)}
    return set()


def _load_builder(path: Path) -> ModuleType:
    """Import a builder by path.

    The per-builder test files sit next to their builder and import it as a
    bare sibling module; a cross-directory guard cannot rely on pytest having
    prepended four different directories to ``sys.path``, so it loads each
    builder explicitly instead.
    """
    spec = importlib.util.spec_from_file_location(
        f"_reqlo_parity_{path.stem}", path
    )
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse(spec: BuilderSpec, text: str) -> dict[str, Any]:
    return tomllib.loads(text) if spec.fmt == "toml" else json.loads(text)


def _server_from(spec: BuilderSpec, origin: str, text: str) -> EmittedServer:
    entry = _parse(spec, text)[spec.container][SERVER_NAME]
    bearer = entry.get("bearer_token_env_var")
    return EmittedServer(
        builder=spec.name,
        origin=origin,
        url=entry["url"],
        headers=entry.get("headers") or {},
        bearer_token_env_var=bearer,
        leaves=frozenset(_string_leaves(entry)),
    )


@pytest.fixture(scope="module")
def generated_roots(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One out dir per config-producing builder, each rendered exactly once."""
    root = tmp_path_factory.mktemp("reqlo-convention-parity")
    roots: dict[str, Path] = {}
    for spec in CONFIG_BUILDERS:
        out_dir = root / spec.name
        _load_builder(spec.module_path).build(out_dir)
        roots[spec.name] = out_dir
    return roots


@pytest.fixture(
    params=_PARITY_CASES,
    ids=[f"{case.spec.name}-{case.origin}" for case in _PARITY_CASES],
    scope="module",
)
def emitted(
    request: pytest.FixtureRequest, generated_roots: dict[str, Path]
) -> EmittedServer:
    """Every shipped server entry, from a fresh build and from the committed
    artifact, so a hand-edit of either leg is caught here."""
    case: ParityCase = request.param
    spec, origin = case.spec, case.origin
    path = (
        generated_roots[spec.name] / spec.out_subpath
        if origin == ORIGIN_BUILT
        else REPO_ROOT / spec.committed_path
    )
    assert path.is_file(), f"{spec.name} did not emit {spec.out_subpath}"
    return _server_from(spec, origin, path.read_text(encoding="utf-8"))


def test_every_env_var_uses_the_canonical_prefix(emitted: EmittedServer) -> None:
    """The anti-drift guard against the submodule's `MCP_REQOGNILOOM_*` variant.

    The server never reads any of these names -- they are client-side
    interpolation only -- so a wrong prefix ships a config that silently
    expands to nothing and authenticates nobody.
    """
    names = emitted.env_refs()
    assert names, f"{emitted.builder}/{emitted.origin}: no env var referenced"
    wrong = {n for n in names if not n.startswith(CANONICAL_ENV_PREFIX)}
    assert not wrong, (
        f"{emitted.builder}/{emitted.origin} interpolates env vars outside the "
        f"{CANONICAL_ENV_PREFIX} prefix: {sorted(wrong)}. The "
        f"{NON_CANONICAL_ENV_PREFIX} variant lives only in the .agent-meta "
        f"submodule and is read by nothing."
    )


def test_the_api_key_travels_over_an_accepted_transport(
    emitted: EmittedServer,
) -> None:
    """The key must go over a header the backend really reads."""
    transports = emitted.transports
    assert transports, (
        f"{emitted.builder}/{emitted.origin} sends no API key at all"
    )
    assert transports <= ACCEPTED_AUTH_TRANSPORTS, (
        f"{emitted.builder}/{emitted.origin} uses auth transport(s) "
        f"{sorted(transports - ACCEPTED_AUTH_TRANSPORTS)}, which the "
        f"ReqogniLoom backend does not accept. Allowed: "
        f"{sorted(ACCEPTED_AUTH_TRANSPORTS)}."
    )


def test_no_header_the_backend_never_reads(emitted: EmittedServer) -> None:
    """Header names are restricted to the auth headers, not merely the auth
    ones being right.

    `X-Project-ID` / `X-User-ID` / `X-Workspace-ID` are the shape this rejects:
    they read as configuration, and the backend has zero production reads of
    them, so they only mislead whoever debugs a failing connection.
    """
    smuggled = set(emitted.headers) - ACCEPTED_AUTH_HEADERS
    assert not smuggled, (
        f"{emitted.builder}/{emitted.origin} ships header(s) "
        f"{sorted(smuggled)} that the backend does not read. Auth headers: "
        f"{sorted(ACCEPTED_AUTH_HEADERS)}; known dead weight: "
        f"{sorted(DEAD_WEIGHT_HEADERS)}."
    )
    assert not smuggled & DEAD_WEIGHT_HEADERS, (
        f"{emitted.builder}/{emitted.origin} reintroduced the dead-weight "
        f"headers {sorted(smuggled & DEAD_WEIGHT_HEADERS)}."
    )


def test_the_key_is_an_env_reference_never_a_literal(
    emitted: EmittedServer,
) -> None:
    """Every key-carrying value resolves to an env var, so no builder can
    commit a working key into a file that ships to every user."""
    values = emitted.key_values()
    assert values, (
        f"{emitted.builder}/{emitted.origin} declares no API-key value; the "
        f"config would connect unauthenticated"
    )
    for location, value in values.items():
        if location == "bearer_token_env_var":
            assert value == API_KEY_ENV_VAR, (
                f"{emitted.builder}/{emitted.origin}: bearer_token_env_var "
                f"must name {API_KEY_ENV_VAR}, got {value!r}"
            )
            continue
        match = _EXACT_ENV_REF_RE.match(value)
        assert match, (
            f"{emitted.builder}/{emitted.origin}: {location} must be an "
            f"env-var reference (${{NAME}} or {{env:NAME}}), got {value!r}"
        )
        assert (match.group(1) or match.group(2)) == API_KEY_ENV_VAR, (
            f"{emitted.builder}/{emitted.origin}: {location} must reference "
            f"{API_KEY_ENV_VAR}, got {value!r}"
        )


def test_no_config_carries_a_plaintext_key(emitted: EmittedServer) -> None:
    """Catches a key pasted into a config value the assertions above do not
    model, e.g. a query parameter or an extra key beside `headers`."""
    assert not any(API_KEY_PREFIX in leaf for leaf in emitted.leaves), (
        f"{emitted.builder}/{emitted.origin} embeds a literal {API_KEY_PREFIX}… "
        f"key in a config value: {sorted(emitted.leaves)}"
    )


def test_codex_bearer_shape_is_intentional(generated_roots: dict[str, Path]) -> None:
    """Pins Codex's deviation from the X-API-Key shape as intentional.

    Codex's Streamable-HTTP transport has no custom-header mechanism at all --
    only `bearer_token_env_var`, which the client expands into
    `Authorization: Bearer`. That is the *other* of the two transports the
    backend accepts for a `reqlo_` key, so the same API key works and only
    the transport differs (see the rationale in build_codex_package.py). This
    test exists so the asymmetry is read as a decision rather than corrected
    into a header Codex would silently drop.
    """
    spec = next(s for s in CONFIG_BUILDERS if s.name == "codex")
    raw = (generated_roots["codex"] / spec.out_subpath).read_text(
        encoding="utf-8"
    )
    server = _server_from(spec, ORIGIN_BUILT, raw)

    assert "headers" not in _parse(spec, raw)[spec.container][SERVER_NAME], (
        "Codex must not gain a custom headers block: its transport would "
        "ignore it, leaving the snippet looking authenticated when it is not"
    )
    assert server.bearer_token_env_var == API_KEY_ENV_VAR
    assert server.transports == {BEARER_TRANSPORT}
    assert server.transports <= ACCEPTED_AUTH_TRANSPORTS


def test_the_documented_env_var_names_are_the_only_ones_used(
    generated_roots: dict[str, Path],
) -> None:
    """Across all four packages, exactly the two names INSTALL.md documents are
    interpolated -- so the docs and the shipped configs cannot part ways."""
    referenced: set[str] = set()
    for spec in CONFIG_BUILDERS:
        raw = (generated_roots[spec.name] / spec.out_subpath).read_text(
            encoding="utf-8"
        )
        referenced |= _server_from(spec, ORIGIN_BUILT, raw).env_refs()

    assert referenced == {MCP_URL_ENV_VAR, API_KEY_ENV_VAR}, (
        f"the packages interpolate {sorted(referenced)}, but "
        f"docs/agent-templates/INSTALL.md documents "
        f"{{{MCP_URL_ENV_VAR}, {API_KEY_ENV_VAR}}}"
    )


def test_no_builder_mentions_the_non_canonical_prefix() -> None:
    """Source-level guard for every builder on disk.

    A builder added tomorrow that copies the submodule's connection block
    would fail here even before it has a committed artifact.
    """
    offenders = {
        path.relative_to(REPO_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(DIST_DIR.rglob("build_*.py"))
        if NON_CANONICAL_ENV_PREFIX in path.read_text(encoding="utf-8")
    }
    assert not offenders, (
        f"builder(s) reference {NON_CANONICAL_ENV_PREFIX}*: "
        f"{sorted(offenders)}. That prefix exists only in the .agent-meta "
        f"submodule's plugin catalog and is read by nothing in this repo."
    )


def test_every_builder_is_covered_by_this_guard() -> None:
    """Meta-guard: a builder this file does not know about is unguarded, and
    the failure would be silent. Fail here instead."""
    on_disk = {path.parent.name for path in DIST_DIR.rglob("build_*.py")}
    covered = {spec.name for spec in CONFIG_BUILDERS}
    assert on_disk == covered, (
        f"dist/ builders on disk {sorted(on_disk)} do not match the builders "
        f"guarded here {sorted(covered)}; add the new one to CONFIG_BUILDERS"
    )
