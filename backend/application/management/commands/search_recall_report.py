"""Read-only recall report for ``artifact.search`` (T-A3-4, PR-A8).

Measures a recall set (default
``application/tests/fixtures/search_recall_set.yaml``, 20 queries) against the
artefacts of one workspace and prints one Markdown table per search mode.

WHY A COMMAND AND NOT ONLY A TEST
---------------------------------
This project's CI runs with ``LLM_PROVIDER=mock`` / a mock embedding provider,
so the semantic pass contributes deterministic noise and any ranking judgement
on the ``synonym``/``thematic`` subsets would measure the mock, not the search.
The CI gate (``application/tests/test_search_recall.py``) therefore covers only
the ID and negative-ID subsets. The remaining subsets, and the ``vector`` mode,
can only be measured against a real embedding provider — this command is that
QS surface. Run it with the production embedding configuration set
(``EMBEDDING_PROVIDER=sentence-transformers`` and the model weights available).

READ-ONLY
---------
The command writes nothing: no ``.save()``, no bulk write, no migration, no file
output. It arms the tenant context (app-layer thread-local + the DB ``SET
app.current_tenant`` RLS variable), reads, and clears it again in a ``finally``.
The only side effect of a run is stdout.

METRICS
-------
``recall@10`` is subset-specific, because only the ``id`` subset has ground
truth:

* ``id`` — share of queries whose ``expect_uid`` row appears within the first
  ``--limit`` results. This is true recall.
* ``id_negative`` — share of queries that returned **no** hits at all (the
  expectation is an empty result set); shown as ``n/n (leer)``.
* ``synonym`` / ``thematic`` — hit-rate: share of queries with at least one hit.
  There is no expected-UID ground truth for these, so this is *not* recall; read
  it as "does the search find anything at all for this phrasing".

``Rang-1-Treffer`` (rank-1) is reported for ``id`` only: queries where the
``expect_uid`` row landed at position 1. It makes the T-A3-2 exact-match pin
visible — a pin regression shows up as rank-1 dropping while recall stays put.

``hybrid >= vector`` (CR-02)
----------------------------
The T-A3-4 recall clause has two halves. The per-query one — ``hybrid >=
keyword`` on the ``id`` subset — is a CI gate
(``application/tests/test_search_recall.py``). The overall one — ``hybrid >=
vector`` — is measured **here**, not in CI: CI runs the ``mock`` embedding
provider, where ``vector`` returns deterministic noise and ``hybrid`` is that
same noise plus the lexical list. An assertion on those two numbers would
compare two mock artefacts and hold by construction — a vacuous green that
looks like coverage. Against a real embedding provider the comparison is
meaningful, so every run prints a ``hybrid >= vector`` line per subset, and
``--json`` carries the same verdict as ``hybrid_ge_vector`` next to
``hybrid_recall`` / ``vector_recall``.

Per subset, not globally: ``satisfied/evaluated`` is not comparable across
subsets (``id`` is true recall, ``id_negative`` counts correctly-empty results,
``synonym``/``thematic`` are hit-rates), so a single aggregate percentage would
mix three different metrics into one number.

``hybrid_ge_vector`` is ``null`` — not ``false`` — when the comparison cannot be
made: one of the two modes was not requested via ``--modes``, or the subset had
nothing to evaluate (e.g. an unseeded workspace, where every ``expect_uid`` is
``unresolved``). A verdict needs a measurement on both sides.

An ``expect_uid`` that does not exist in the target workspace is counted as
``unresolved`` and reported separately. It is not a failure: a report run
against a workspace that was never seeded with the recall corpus legitimately
has nothing to resolve, and silently scoring those as misses would make the
number depend on the dataset instead of the search.

Usage::

    python manage.py search_recall_report --workspace <uuid>
    python manage.py search_recall_report --workspace <uuid> --json
    python manage.py search_recall_report --workspace <uuid> \\
        --modes keyword,hybrid --limit 10
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from django.core.management.base import BaseCommand, CommandError

#: The four query subsets of the recall set, in report order.
QUERY_KINDS: tuple[str, ...] = ("id", "id_negative", "synonym", "thematic")

#: Keys every query entry must carry.
_REQUIRED_QUERY_KEYS: tuple[str, ...] = ("id", "kind", "query", "locale")

#: Search modes the report can measure.
_MODES: tuple[str, ...] = ("keyword", "hybrid", "vector")

#: Default fixture — the file the CI gate reads, kept next to this package.
DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "search_recall_set.yaml"
)

#: Subsets whose metric is true recall against a known expected row.
_GROUND_TRUTH_KINDS: frozenset[str] = frozenset({"id"})


def load_recall_set(path: str | Path) -> dict[str, Any]:
    """Read and structurally validate a recall-set YAML document.

    Kept import-free of Django so the CI gate can load the same file without a
    database. Raises :class:`ValueError` for a malformed document — the caller
    turns that into its own error type (``CommandError`` here, an assertion in
    the gate).

    Args:
        path: Path to the YAML fixture.

    Returns:
        The parsed document with a ``queries`` list.

    Raises:
        ValueError: File missing/unparsable, missing keys, unknown ``kind``,
            unknown ``locale``, a duplicate query ``id``, or an ``id`` entry
            without ``expect_uid``.
    """
    fixture_path = Path(path)
    try:
        document = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"recall set not readable: {fixture_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"recall set is not valid YAML: {fixture_path}: {exc}") from exc

    if not isinstance(document, dict):
        raise ValueError(f"recall set must be a mapping, got {type(document).__name__}")
    queries = document.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("recall set has no non-empty 'queries' list")

    seen_ids: set[str] = set()
    for index, entry in enumerate(queries):
        where = f"queries[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where} must be a mapping")
        missing = [key for key in _REQUIRED_QUERY_KEYS if not entry.get(key)]
        if missing:
            raise ValueError(f"{where} is missing {', '.join(missing)}")
        query_id = str(entry["id"])
        if query_id in seen_ids:
            raise ValueError(f"duplicate query id {query_id!r}")
        seen_ids.add(query_id)
        if entry["kind"] not in QUERY_KINDS:
            raise ValueError(
                f"{where} ({query_id}) has unknown kind {entry['kind']!r}; "
                f"expected one of {list(QUERY_KINDS)}"
            )
        if entry["locale"] not in {"de", "en"}:
            raise ValueError(
                f"{where} ({query_id}) has unknown locale {entry['locale']!r}"
            )
        if entry["kind"] == "id" and not entry.get("expect_uid"):
            raise ValueError(f"{where} ({query_id}) is kind 'id' without expect_uid")
    return document


@dataclass
class SubsetScore:
    """One subset's result in one mode.

    Attributes:
        subset: One of :data:`QUERY_KINDS`.
        evaluated: Queries that contributed a measurement (``id`` excludes
            queries whose ``expect_uid`` did not resolve in this workspace).
        satisfied: Queries that met their subset's expectation.
        rank_one: Queries whose expected row landed at position 1 (``id`` only;
            ``None`` for the other subsets, which have no expected row).
        unreachable: Queries that raised while searching, so a broken mode does
            not silently look like a perfect score.
    """

    subset: str
    evaluated: int = 0
    satisfied: int = 0
    rank_one: int | None = None
    unreachable: list[str] = field(default_factory=list)

    @property
    def rank_one_display(self) -> str:
        if self.rank_one is None:
            return "—"
        return f"{self.rank_one}/{self.evaluated}"

    @property
    def metric_suffix(self) -> str:
        """Marker for subsets whose numerator means something other than recall."""
        if self.subset == "id_negative":
            return " (leer)"
        if self.subset in _GROUND_TRUTH_KINDS:
            return ""
        return " (Trefferquote)"

    @property
    def recall(self) -> float | None:
        """``satisfied / evaluated``, or ``None`` when nothing was evaluated.

        ``None`` is not a zero score: a subset with no evaluated query (an
        unseeded workspace, a mode that failed on every query) carries no
        measurement at all, and reporting it as 0 % would invent one.
        """
        if self.evaluated == 0:
            return None
        return self.satisfied / self.evaluated

    def recall_at_least(self, other: "SubsetScore") -> bool | None:
        """``self.recall >= other.recall``, or ``None`` if either is unmeasured.

        Compares the fractions cross-multiplied so the verdict cannot flip on
        floating-point rounding (e.g. two thirds vs two thirds).
        """
        if self.evaluated == 0 or other.evaluated == 0:
            return None
        return self.satisfied * other.evaluated >= other.satisfied * self.evaluated

    def as_dict(self) -> dict[str, Any]:
        return {
            "subset": self.subset,
            "evaluated": self.evaluated,
            "satisfied": self.satisfied,
            "rank_one": self.rank_one,
            "unreachable": list(self.unreachable),
        }


class Command(BaseCommand):
    """Print a read-only recall report for ``artifact.search`` (T-A3-4)."""

    help = (
        "Measure a recall set against one workspace's artefacts and print a "
        "Markdown table per search mode (read-only, T-A3-4)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--fixture",
            default=str(DEFAULT_FIXTURE),
            help=f"Recall-set YAML (default: {DEFAULT_FIXTURE}).",
        )
        parser.add_argument(
            "--workspace",
            required=True,
            help="Workspace UUID whose artefacts are searched (required).",
        )
        parser.add_argument(
            "--user",
            default=None,
            help=(
                "User UUID to resolve the AuthContext for (default: the first "
                "tenant admin of the workspace's tenant, else its first user)."
            ),
        )
        parser.add_argument(
            "--modes",
            default=",".join(_MODES),
            help=f"Comma-separated search modes (default: {','.join(_MODES)}).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Result window per query, i.e. the N in recall@N (default: 10).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the same numbers as JSON instead of Markdown tables.",
        )

    # -- orchestration ------------------------------------------------------

    def handle(self, *args, **options) -> None:
        from persistence.middleware import clear_request_tenant, set_request_tenant
        from persistence.models import Workspace

        try:
            document = load_recall_set(options["fixture"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        modes = self._parse_modes(options["modes"])
        limit = int(options["limit"])
        if limit < 1:
            raise CommandError("--limit must be >= 1.")

        workspace_id = self._parse_uuid(options["workspace"], "--workspace")
        workspace = Workspace.unscoped.filter(id=workspace_id).first()
        if workspace is None:
            raise CommandError(f"No workspace with id {workspace_id}.")

        # A management command has no request/middleware around it, so both
        # isolation layers must be armed explicitly — without it the
        # least-privilege runtime role reads an empty table under RLS (same
        # rationale as ``backfill_embeddings``).
        set_request_tenant(workspace.tenant_id)
        try:
            ctx = self._build_context(
                workspace=workspace, user_id=options["user"]
            )
            expectations = self._resolve_expectations(
                document["queries"], workspace_id=workspace_id
            )
            report = self._measure(
                document=document,
                queries=document["queries"],
                expectations=expectations,
                ctx=ctx,
                workspace_id=workspace_id,
                modes=modes,
                limit=limit,
            )
        finally:
            clear_request_tenant()

        if options["json"]:
            self._write_json(
                report=report,
                workspace_id=workspace_id,
                fixture=options["fixture"],
                limit=limit,
            )
        else:
            self._write_markdown(
                report=report,
                workspace_id=workspace_id,
                fixture=options["fixture"],
                limit=limit,
            )

    # -- argument/context resolution ---------------------------------------

    @staticmethod
    def _parse_modes(raw: str) -> list[str]:
        modes = [part.strip() for part in str(raw).split(",") if part.strip()]
        unknown = [mode for mode in modes if mode not in _MODES]
        if unknown:
            raise CommandError(
                f"Unknown mode(s): {', '.join(unknown)}. "
                f"Allowed: {', '.join(_MODES)}."
            )
        if not modes:
            raise CommandError("--modes must name at least one mode.")
        return modes

    @staticmethod
    def _parse_uuid(raw: Any, option: str) -> UUID:
        try:
            return UUID(str(raw))
        except (TypeError, ValueError) as exc:
            raise CommandError(f"{option} is not a UUID: {raw!r}") from exc

    def _build_context(self, *, workspace, user_id: Any):
        """Resolve the real :class:`AuthContext` for this run.

        Uses the project's own construction path
        (:class:`~auth_tenancy.services.tenant_context.TenantContextService`)
        rather than fabricating a context, so the roles the search sees are the
        roles that user really holds in this workspace.

        Raises:
            CommandError: The workspace has no user to measure as, the given
                ``--user`` does not exist in the workspace's tenant, or the
                tenant cannot be resolved (inactive/unknown).
        """
        from auth_tenancy.context import AuthMethod, IdentityClaims
        from auth_tenancy.errors import TenantResolutionError
        from auth_tenancy.services.authorization import AuthorizationService
        from auth_tenancy.services.tenant_context import TenantContextService
        from persistence.models import User

        if user_id:
            wanted = self._parse_uuid(user_id, "--user")
            user = User.objects.filter(
                id=wanted, tenant_id=workspace.tenant_id
            ).first()
            if user is None:
                raise CommandError(
                    f"No user {wanted} in tenant {workspace.tenant_id}."
                )
        else:
            user = self._default_user(workspace.tenant_id)
            if user is None:
                raise CommandError(
                    "No user in the workspace's tenant to build an AuthContext "
                    "for; pass --user <uuid>."
                )

        roles = AuthorizationService().active_roles_for(
            user_id=user.id, workspace_id=workspace.id
        )
        if not roles:
            # CR-06: an empty role set is a legitimate run (the report still
            # measures retrieval), but it is *not* the same report a workspace
            # member would get — permission-scoped hits are filtered by the
            # caller's roles. Warn instead of silently emitting an identical
            # looking number, so nobody reads it as "as a viewer/admin".
            self.stderr.write(
                self.style.WARNING(
                    f"warning: user {user.id} holds no active role in workspace "
                    f"{workspace.id}; the report runs with an empty role set and "
                    "is not representative of a workspace member. Pass --user "
                    "<uuid> with a member that holds a role."
                )
            )
        claims = IdentityClaims(
            user_id=user.id,
            tenant_id=workspace.tenant_id,
            roles=roles,
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        service = TenantContextService()
        try:
            tenant_context = service.resolve_tenant_context(claims)
        except TenantResolutionError as exc:
            raise CommandError(
                f"Tenant {workspace.tenant_id} cannot be resolved "
                "(inactive or missing)."
            ) from exc
        return service.build_auth_context(
            claims, tenant_context, roles, workspace_id=workspace.id
        )

    @staticmethod
    def _default_user(tenant_id: UUID):
        """First non-suspended tenant admin, else the first user of the tenant.

        Both branches are ordered explicitly (CR-06): an unordered
        ``.first()`` lets the database pick whichever row it likes, so two runs
        against the same data could build different AuthContexts — and with
        different roles, different numbers — from identical input.
        """
        from auth_tenancy.models import TenantRole
        from persistence.models import User

        admin = (
            TenantRole.unscoped.filter(
                tenant_id=tenant_id,
                role=TenantRole.ROLE_ADMIN,
                suspended_at__isnull=True,
            )
            .select_related("user")
            .order_by("user__username", "user_id")
            .first()
        )
        if admin is not None and admin.user is not None and admin.user.is_active:
            return admin.user
        return (
            User.objects.filter(tenant_id=tenant_id, is_active=True)
            .order_by("username", "id")
            .first()
        )

    @staticmethod
    def _resolve_expectations(
        queries: Iterable[dict[str, Any]], *, workspace_id: UUID
    ) -> dict[str, str | None]:
        """Map ``expect_uid`` -> ``pl_requirement.id`` (``None`` if unresolved)."""
        from persistence.models import Requirement

        wanted = [
            str(entry["expect_uid"])
            for entry in queries
            if entry["kind"] == "id"
        ]
        # ``Requirement.workspace`` is a nullable denormalized copy (#133) that
        # not every writer fills; the artifact's workspace is the authoritative
        # one (it is what the search pass joins on).
        found = dict(
            Requirement.objects.filter(
                artifact__workspace_id=workspace_id, uid__in=wanted
            ).values_list("uid", "id")
        )
        return {
            uid: str(found[uid]) if uid in found else None for uid in wanted
        }

    # -- measurement --------------------------------------------------------

    def _measure(
        self,
        *,
        document: dict[str, Any],
        queries: list[dict[str, Any]],
        expectations: dict[str, str | None],
        ctx,
        workspace_id: UUID,
        modes: list[str],
        limit: int,
    ) -> dict[str, Any]:
        """Run every query in every mode and aggregate per subset."""
        from application.search_service import SearchService

        service = SearchService()
        unresolved = sorted(
            uid for uid, requirement_id in expectations.items() if requirement_id is None
        )
        per_mode: dict[str, dict[str, SubsetScore]] = {}
        for mode in modes:
            scores = {kind: SubsetScore(kind) for kind in QUERY_KINDS}
            for entry in queries:
                kind = str(entry["kind"])
                score = scores[kind]
                if kind == "id":
                    expected_id = expectations.get(str(entry["expect_uid"]))
                    if expected_id is None:
                        # Counted once, in `unresolved` — never as a miss.
                        continue
                else:
                    expected_id = None
                try:
                    result = service.search(
                        str(entry["query"]),
                        ctx,
                        workspace_id=workspace_id,
                        mode=mode,
                        limit=limit,
                    )
                except Exception:  # noqa: BLE001 — one bad query must not kill the report
                    score.unreachable.append(str(entry["id"]))
                    continue
                score.evaluated += 1
                if kind == "id_negative":
                    if result.total_count == 0:
                        score.satisfied += 1
                elif kind == "id":
                    rank = next(
                        (
                            position
                            for position, hit in enumerate(result.results, start=1)
                            if hit.id == expected_id
                        ),
                        None,
                    )
                    if rank is not None:
                        score.satisfied += 1
                        if rank == 1:
                            score.rank_one = (score.rank_one or 0) + 1
                elif result.total_count > 0:
                    score.satisfied += 1
            for score in scores.values():
                if score.subset == "id" and score.rank_one is None:
                    score.rank_one = 0
            per_mode[mode] = scores

        return {
            "modes": per_mode,
            "comparison": self._compare_hybrid_with_vector(per_mode),
            "unresolved": unresolved,
            "dataset": document.get("dataset"),
            "query_count": len(queries),
        }

    @staticmethod
    def _compare_hybrid_with_vector(
        per_mode: dict[str, dict[str, SubsetScore]],
    ) -> dict[str, dict[str, Any]]:
        """Compute the ``hybrid >= vector`` verdict per subset (CR-02).

        Only a *verdict* is returned, never a failure: the T-A3-4 clause is a
        quality statement about a real embedding provider, and this command is
        the surface that reports it (see the module docstring for why it is not
        a CI gate under the ``mock`` provider).

        Args:
            per_mode: Measured subsets, keyed by mode.

        Returns:
            One entry per subset with ``hybrid_recall`` / ``vector_recall``
            (fractions or ``None``), their counts, and ``hybrid_ge_vector``
            (``True``/``False``/``None`` when unmeasurable).
        """
        hybrid_scores = per_mode.get("hybrid")
        vector_scores = per_mode.get("vector")
        comparison: dict[str, dict[str, Any]] = {}
        for kind in QUERY_KINDS:
            hybrid = hybrid_scores[kind] if hybrid_scores else None
            vector = vector_scores[kind] if vector_scores else None
            verdict = (
                hybrid.recall_at_least(vector)
                if hybrid is not None and vector is not None
                else None
            )
            comparison[kind] = {
                "subset": kind,
                "hybrid_recall": hybrid.recall if hybrid else None,
                "vector_recall": vector.recall if vector else None,
                "hybrid_satisfied": hybrid.satisfied if hybrid else None,
                "hybrid_evaluated": hybrid.evaluated if hybrid else None,
                "vector_satisfied": vector.satisfied if vector else None,
                "vector_evaluated": vector.evaluated if vector else None,
                "hybrid_ge_vector": verdict,
            }
        return comparison

    # -- output -------------------------------------------------------------

    def _write_markdown(
        self, *, report: dict[str, Any], workspace_id: UUID, fixture: str, limit: int
    ) -> None:
        from llm_adapter.embedding_service import current_embedding_model_id

        self.stdout.write(
            f"# Search recall report (recall@{limit})\n"
            f"workspace: {workspace_id}\n"
            f"fixture: {fixture}\n"
            f"dataset: {report['dataset']} ({report['query_count']} queries)\n"
            f"embedding model: {current_embedding_model_id()}\n"
        )
        for mode, scores in report["modes"].items():
            self.stdout.write(f"## mode: {mode}\n")
            self.stdout.write(
                f"| Subset | recall@{limit} | Rang-1-Treffer | n |"
            )
            self.stdout.write("|--------|-----------|----------------|----|")
            for kind in QUERY_KINDS:
                score: SubsetScore = scores[kind]
                self.stdout.write(
                    f"| {kind} | {score.satisfied}/{score.evaluated}"
                    f"{score.metric_suffix} | {score.rank_one_display} "
                    f"| {score.evaluated} |"
                )
            failed = {
                kind: scores[kind].unreachable
                for kind in QUERY_KINDS
                if scores[kind].unreachable
            }
            if failed:
                for kind, query_ids in failed.items():
                    self.stdout.write(
                        f"\nERROR: {kind}: search failed for {', '.join(query_ids)}"
                    )
            self.stdout.write("")

        self._write_comparison(report["comparison"], limit=limit)

        unresolved = report["unresolved"]
        self.stdout.write(
            f"unresolved expect_uid (not present in this workspace): "
            f"{len(unresolved)}"
        )
        for uid in unresolved:
            self.stdout.write(f"  - {uid}")
        self.stdout.write(
            f"\nrecall@{limit} is subset-specific: 'id' is true recall, "
            "'id_negative' counts correctly-empty results, "
            "'synonym'/'thematic' report a hit-rate (no ground truth)."
        )

    def _write_comparison(
        self, comparison: dict[str, dict[str, Any]], *, limit: int
    ) -> None:
        """Print the per-subset ``hybrid >= vector`` verdict (CR-02)."""
        self.stdout.write("## hybrid vs vector (T-A3-4 recall clause)\n")
        self.stdout.write(
            f"| Subset | hybrid recall@{limit} | vector recall@{limit} "
            "| hybrid >= vector |"
        )
        self.stdout.write("|--------|------------------|------------------|------------------|")
        unmeasured: list[str] = []
        for kind in QUERY_KINDS:
            row = comparison[kind]
            verdict = row["hybrid_ge_vector"]
            if verdict is None:
                unmeasured.append(kind)
                badge = "—"
            else:
                badge = "yes" if verdict else "NO"
            self.stdout.write(
                f"| {kind} | {self._ratio(row['hybrid_satisfied'], row['hybrid_evaluated'])} "
                f"| {self._ratio(row['vector_satisfied'], row['vector_evaluated'])} "
                f"| {badge} |"
            )
        if unmeasured:
            self.stdout.write(
                f"\nnot measured for: {', '.join(unmeasured)} — the verdict needs "
                "both the 'hybrid' and 'vector' mode (--modes hybrid,vector) and at "
                "least one evaluated query per subset."
            )
        self.stdout.write("")

    @staticmethod
    def _ratio(satisfied: int | None, evaluated: int | None) -> str:
        """Render a measured fraction as ``satisfied/evaluated``, else ``—``."""
        if satisfied is None or not evaluated:
            return "—"
        return f"{satisfied}/{evaluated}"

    def _write_json(
        self, *, report: dict[str, Any], workspace_id: UUID, fixture: str, limit: int
    ) -> None:
        import json

        from llm_adapter.embedding_service import current_embedding_model_id

        payload = {
            "workspace_id": str(workspace_id),
            "fixture": fixture,
            "dataset": report["dataset"],
            "query_count": report["query_count"],
            "limit": limit,
            "embedding_model": current_embedding_model_id(),
            "modes": {
                mode: {
                    "subsets": {
                        kind: scores[kind].as_dict() for kind in QUERY_KINDS
                    }
                }
                for mode, scores in report["modes"].items()
            },
            # CR-02: the T-A3-4 "hybrid >= vector" clause, per subset. Kept as
            # its own block rather than folded into ``modes`` because the
            # verdict spans two modes.
            "hybrid_vs_vector": report["comparison"],
            "unresolved": report["unresolved"],
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
