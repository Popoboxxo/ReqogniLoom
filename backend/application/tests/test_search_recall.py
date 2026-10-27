"""T-A3-4 / PR-A8 — recall set for ``artifact.search`` (COMP-AS-010).

A structured CI gate over the recall set in
``application/tests/fixtures/search_recall_set.yaml`` (20 queries: 6 exact-UID
lookups, 2 negative UID lookups, 6 synonym queries, 6 thematic queries).

WHAT THIS GATE MEASURES, AND WHAT IT DELIBERATELY DOES NOT
---------------------------------------------------------
CI runs with the ``mock`` embedding provider, so the semantic pass produces
deterministic noise. Measuring ranking quality on paraphrases with it would
measure the mock, not the search. The gate therefore covers only

* the ``id`` subset — recall@10 for ``keyword`` and ``hybrid``, with the
  assertion ``recall(hybrid) >= recall(keyword)`` (T-A3-4's DoD), plus the
  rank-1 counts so a regression of the T-A3-2 exact-match pin is visible even
  while recall stays at 100 %, and
* the ``id_negative`` subset — an identifier that exists nowhere must yield
  zero hits in ``keyword`` mode.

``synonym``, ``thematic`` and the ``vector`` mode are *not* gated here. They
are measured by ``manage.py search_recall_report`` against a real embedding
provider; the command reads the same YAML, so both surfaces stay in sync.

WHY THE TEST BUILDS ITS OWN CORPUS
----------------------------------
Per the issue, the gate must be hermetic — it may not depend on ``seed_demo``
or a pre-populated database. ``auth_tenancy/management/commands/seed_demo.py``
provisions a tenant, a workspace, an admin user and their role/attribute
defaults; it creates **no artifacts at all**, so it offers no stable UID set to
lean on. The ``expect_uid`` values are therefore fixed *in the fixture* and
created here by the test through the shared factories: the YAML stays the
single source of truth for both the gate and the report command, and the
dataset a report run sees is the dataset the gate asserts on.

Datasets are small on purpose (6 expected rows + 4 decoys in one workspace):
the gate's job is to catch a ranking regression, not to benchmark throughput.
"""
from __future__ import annotations

import json
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from application.management.commands.search_recall_report import (
    DEFAULT_FIXTURE,
    QUERY_KINDS,
    load_recall_set,
)
from application.search_service import SearchService
from llm_adapter.embedding_service import (
    generate_embedding_with_model,
    get_embedding_text,
)
from persistence.middleware import set_request_tenant
from persistence.models import Artifact, ArtifactVersion, Requirement, TraceLink
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

#: Recall window used by the gate — the N in recall@N, and the same default the
#: report command uses.
LIMIT = 10

#: Expected subset distribution of the fixture: 6 ID, 2 negative ID, 6 synonym,
#: 6 thematic = 20.
EXPECTED_DISTRIBUTION = {"id": 6, "id_negative": 2, "synonym": 6, "thematic": 6}

#: The rows the ``id`` subset resolves against. The UIDs here and the
#: ``expect_uid`` values in the YAML are one contract — a change on either side
#: without the other is a red gate, not a silently unresolved report.
_EXPECTED_REQUIREMENTS: tuple[dict[str, str], ...] = (
    {
        "uid": "REQ-L1-001",
        "title": "Suchoberfläche für Artefakte",
        "description": (
            "Volltextsuche über Requirements, Architektur und Testfälle; "
            "jeder Treffer zeigt UID, Titel und Relevanz."
        ),
    },
    {
        "uid": "REQ-L1-004",
        "title": "Ladezeit der Suchseite unter 500 ms",
        "description": (
            "Die Trefferliste wird innerhalb von 500 ms gerendert, auch bei "
            "200 Treffern in einem Workspace."
        ),
    },
    {
        "uid": "REQ-L2-010",
        "title": "Zugriffskontrolle für fremde Workspaces",
        "description": (
            "Item-Level-Permissions: ein Aufrufer ohne Leserecht erhält keine "
            "Treffer aus einem fremden Workspace."
        ),
    },
    {
        "uid": "REQ-L3-021",
        "title": "Baseline-Vergleich zwischen zwei Snapshots",
        "description": (
            "Der Diff listet hinzugefügte, entfernte und geänderte Artefakte "
            "zwischen zwei Baselines auf Feldebene."
        ),
    },
    {
        "uid": "REQ-L3-044",
        "title": "Trace-Link-Abdeckung im V-Modell",
        "description": (
            "Coverage-Aggregation über L0 bis L4; jeder Trace-Link-Typ zählt "
            "für die Abdeckung genau einmal."
        ),
    },
    {
        "uid": "REQ-L4-002",
        "title": "Akkulaufzeit des mobilen Clients",
        "description": (
            "Der Client verbraucht bei aktiver Synchronisation höchstens vier "
            "Prozent Akku pro Stunde."
        ),
    },
)

#: Noise rows: realistic sibling wording that must never be mistaken for one of
#: the expected UIDs. They also keep the corpus from being a 1-row workspace,
#: where any ranking bug would still trivially return rank 1.
_DECOY_REQUIREMENTS: tuple[dict[str, str], ...] = (
    {
        "title": "Anforderung an die Protokollierung",
        "description": "Jede Änderung an einem Artefakt erzeugt einen Audit-Eintrag.",
    },
    {
        "title": "Testfall für den ReqIF-Import",
        "description": "Ein ReqIF-2.0-Dokument mit drei Requirements wird importiert.",
    },
    {
        "title": "Schnittstelle zum PDF-Report",
        "description": "Die Schnittstelle liefert ein PDF mit Deckblatt und Revisionsstand.",
    },
    {
        "title": "Export nach ReqIF",
        "description": "Der Export schreibt ReqIF 1.2 inklusive aller Trace-Links.",
    },
)


# ---------- helpers ----------


def _load_fixture() -> dict[str, Any]:
    return load_recall_set(DEFAULT_FIXTURE)


def _seed_corpus(workspace) -> dict[str, str]:
    """Create the recall corpus in *workspace*; return ``{uid: requirement id}``.

    Embeddings are written the way production writes them
    (``get_embedding_text`` + ``generate_embedding_with_model`` + a bare
    ``.update()``), so ``hybrid`` mode exercises the real RRF path instead of
    its no-semantic-hits fallback. Requires ``EMBEDDING_PROVIDER=mock`` to be
    set by the test — the mock provider is deterministic per text.
    """
    resolved: dict[str, str] = {}
    for row in (*_EXPECTED_REQUIREMENTS, *_DECOY_REQUIREMENTS):
        requirement = make_requirement(workspace, **row)
        embedding, model_id = generate_embedding_with_model(
            get_embedding_text(requirement)
        )
        if embedding is not None:
            Requirement.objects.filter(id=requirement.id).update(
                embedding=embedding, embedding_model=model_id
            )
        uid = row.get("uid")
        if uid:
            resolved[uid] = str(requirement.id)
    return resolved


def _recall_at_10(
    query: str,
    mode: str,
    expected_id: str,
    workspace,
    ctx,
) -> tuple[bool, int | None]:
    """Search *query* in *mode* and report ``(found within limit, rank)``.

    One search per call serves both numbers, so the gate does not pay for the
    same query twice and recall and rank can never disagree.
    """
    result = SearchService().search(
        query, ctx, workspace_id=workspace.id, mode=mode, limit=LIMIT
    )
    for position, hit in enumerate(result.results, start=1):
        if hit.id == expected_id:
            return True, position
    return False, None


def _id_queries(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in fixture["queries"] if entry["kind"] == "id"]


# ---------- fixture structure (no DB) ----------


class TestRecallSetStructure:
    """The fixture itself is a contract: 20 queries, distribution 6/2/6/6."""

    def test_fixture_has_twenty_queries_in_the_agreed_distribution(self):
        fixture = _load_fixture()
        queries = fixture["queries"]

        assert len(queries) == 20
        distribution = {kind: 0 for kind in QUERY_KINDS}
        for entry in queries:
            distribution[entry["kind"]] += 1
        assert distribution == EXPECTED_DISTRIBUTION

    def test_query_ids_are_unique_and_every_id_query_declares_an_expect_uid(self):
        queries = _load_fixture()["queries"]

        query_ids = [entry["id"] for entry in queries]
        assert len(set(query_ids)) == len(query_ids)

        id_entries = [entry for entry in queries if entry["kind"] == "id"]
        assert len({entry["expect_uid"] for entry in id_entries}) == len(id_entries)
        for entry in queries:
            assert entry["query"].strip(), f"{entry['id']} has an empty query"
            assert entry["locale"] in {"de", "en"}

    def test_structure_loader_rejects_an_id_query_without_expect_uid(self, tmp_path):
        broken = tmp_path / "broken.yaml"
        broken.write_text(
            "dataset: broken\n"
            "queries:\n"
            "  - id: Q-BAD-01\n"
            "    kind: id\n"
            "    query: REQ-L1-001\n"
            "    locale: de\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="without expect_uid"):
            load_recall_set(broken)


# ---------- CI gate: ID subset ----------


@pytest.mark.django_db
class TestIdRecallGate:
    """``hybrid`` must not retrieve fewer expected rows than ``keyword``."""

    def test_hybrid_recall_is_at_least_keyword_recall_on_the_id_subset(
        self, monkeypatch
    ):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        fixture = _load_fixture()
        expected_queries = _id_queries(fixture)

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            resolved = _seed_corpus(workspace)
            ctx = editor_ctx(tenant, workspace)

            # Fixture and corpus must not drift apart: a UID in the YAML that
            # the corpus does not create would silently score as a miss.
            assert sorted(resolved) == sorted(
                entry["expect_uid"] for entry in expected_queries
            )

            recall: dict[str, int] = {}
            rank_one: dict[str, int] = {}
            for mode in ("keyword", "hybrid"):
                found = 0
                first = 0
                for entry in expected_queries:
                    hit, rank = _recall_at_10(
                        entry["query"],
                        mode,
                        resolved[entry["expect_uid"]],
                        workspace,
                        ctx,
                    )
                    found += int(hit)
                    first += int(rank == 1)
                recall[mode] = found
                rank_one[mode] = first

        total = len(expected_queries)
        assert recall["keyword"] == total, (
            f"keyword recall@10 = {recall['keyword']}/{total}: the lexical "
            "exact-UID tier no longer retrieves every expected row"
        )
        assert recall["hybrid"] >= recall["keyword"], (
            f"recall@10 regressed: hybrid={recall['hybrid']}/{total} "
            f"< keyword={recall['keyword']}/{total}"
        )
        # Rank-1 evidence (T-A3-2 / A-L21): both modes returned the expected
        # UID first, matching the PR #1513 after-values. Under the mock
        # embedding provider this counts the *observed* ranking rather than
        # proving the pin — the mock's semantic order is noise, so the exact-UID
        # lexical hit wins the RRF even unpinned. The pin-sensitive assertion is
        # the ``relevance_score == 1.0`` in
        # :meth:`test_hybrid_pins_an_exact_uid_at_score_one`; the adversarial
        # A-L21 case (a semantically closer neighbour) lives in
        # ``test_search_semantic_fusion.py::test_exact_uid_ranks_first_under_rrf``.
        assert rank_one["hybrid"] == total, (
            f"hybrid rank-1 = {rank_one['hybrid']}/{total} "
            f"(keyword rank-1 = {rank_one['keyword']}/{total}): the exact-match "
            "pin is not lifting the expected UID to the front"
        )
        assert rank_one["keyword"] == total, (
            f"keyword rank-1 = {rank_one['keyword']}/{total}: an expected UID "
            "is not ranked first"
        )

    def test_hybrid_pins_an_exact_uid_at_score_one(self, monkeypatch):
        """The pin's observable contract: rank 1 *and* ``relevance_score == 1.0``.

        This is the gate's pin-sensitive assertion: with the pin disabled
        (``_PIN_MIN_NORMALIZED_LEXICAL_SCORE`` raised above the exact-UID tier)
        the same hit stays at rank 1 but scores ~0.65 — the RRF value, not the
        pinned one. A rank-1-only check would therefore not notice the
        regression.
        """
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        entry = _id_queries(_load_fixture())[0]

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            resolved = _seed_corpus(workspace)
            ctx = editor_ctx(tenant, workspace)

            result = SearchService().search(
                entry["query"],
                ctx,
                workspace_id=workspace.id,
                mode="hybrid",
                limit=LIMIT,
            )

        assert result.results, "hybrid search returned nothing for an exact UID"
        top = result.results[0]
        assert top.id == resolved[entry["expect_uid"]]
        assert top.relevance_score == pytest.approx(1.0)


# ---------- CI gate: negative ID subset ----------


@pytest.mark.django_db
class TestNegativeIdGate:
    """An identifier that exists nowhere must not "find" anything."""

    def test_keyword_returns_no_hits_for_unknown_identifiers(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        negative_queries = [
            entry
            for entry in _load_fixture()["queries"]
            if entry["kind"] == "id_negative"
        ]

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            _seed_corpus(workspace)
            ctx = editor_ctx(tenant, workspace)

            totals = {
                entry["id"]: SearchService()
                .search(
                    entry["query"],
                    ctx,
                    workspace_id=workspace.id,
                    mode="keyword",
                    limit=LIMIT,
                )
                .total_count
                for entry in negative_queries
            }

        assert totals == {entry["id"]: 0 for entry in negative_queries}, (
            f"unknown identifiers produced hits: "
            f"{ {qid: count for qid, count in totals.items() if count} }"
        )


# ---------- read-only report command ----------


@pytest.mark.django_db
class TestSearchRecallReportCommand:
    """``search_recall_report`` is the QS surface for the non-gated subsets."""

    def test_report_prints_all_subsets_and_writes_nothing(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            _seed_corpus(workspace)
            # The command resolves a real AuthContext, so the workspace needs a
            # member. ``--user`` exercises that explicit path.
            ctx = editor_ctx(tenant, workspace)
            before = _row_snapshot()

            stdout = StringIO()
            call_command(
                "search_recall_report",
                "--workspace",
                str(workspace.id),
                "--user",
                str(ctx.user_id),
                "--modes",
                "keyword,hybrid",
                stdout=stdout,
            )
            # The command clears the tenant context in its ``finally`` (the
            # same contract ``backfill_embeddings`` follows), so re-arm it
            # before reading the "after" snapshot in this in-process caller.
            set_request_tenant(tenant.id)
            after = _row_snapshot()

        output = stdout.getvalue()
        assert "| Subset | recall@10 | Rang-1-Treffer | n |" in output
        for kind in QUERY_KINDS:
            assert f"| {kind} |" in output
        assert "## mode: keyword" in output
        assert "## mode: hybrid" in output
        assert "unresolved expect_uid (not present in this workspace): 0" in output
        changed = {
            table: (before[table], after[table])
            for table in before
            if before[table] != after[table]
        }
        assert before == after, f"search_recall_report mutated the database: {changed}"

    def test_report_json_carries_the_same_numbers(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            _seed_corpus(workspace)
            # Default identity resolution: the workspace's first member.
            editor_ctx(tenant, workspace)

            stdout = StringIO()
            call_command(
                "search_recall_report",
                "--workspace",
                str(workspace.id),
                "--modes",
                "keyword",
                "--json",
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        assert payload["workspace_id"] == str(workspace.id)
        assert payload["query_count"] == 20
        assert payload["unresolved"] == []
        keyword = payload["modes"]["keyword"]["subsets"]
        assert keyword["id"]["evaluated"] == 6
        assert keyword["id"]["satisfied"] == 6
        assert keyword["id"]["rank_one"] == 6
        assert keyword["id_negative"] == {
            "subset": "id_negative",
            "evaluated": 2,
            "satisfied": 2,
            "rank_one": None,
            "unreachable": [],
        }

    def test_report_counts_unresolved_expectations_separately(self, monkeypatch):
        """A workspace without the corpus is not a failure — it is unresolved."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            editor_ctx(tenant, workspace)

            stdout = StringIO()
            call_command(
                "search_recall_report",
                "--workspace",
                str(workspace.id),
                "--modes",
                "keyword",
                "--json",
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        assert len(payload["unresolved"]) == 6
        assert payload["modes"]["keyword"]["subsets"]["id"]["evaluated"] == 0

    def test_report_fails_clearly_for_an_unknown_workspace(self):
        with pytest.raises(CommandError, match="No workspace with id"):
            call_command(
                "search_recall_report",
                "--workspace",
                "00000000-0000-0000-0000-000000000000",
                stdout=StringIO(),
            )


def _row_snapshot() -> dict[str, object]:
    """Row counts plus a content fingerprint for the tables this command reads.

    A count alone cannot prove "read-only": an in-place edit would leave every
    count unchanged. The fingerprints cover the fields a search could plausibly
    touch (identity, title, UID) — an embedding rewrite is caught by the
    ``embedding_model`` column of the fingerprint.
    """
    return {
        "Artifact": Artifact.objects.count(),
        "Requirement": Requirement.objects.count(),
        "ArtifactVersion": ArtifactVersion.objects.count(),
        "TraceLink": TraceLink.objects.count(),
        "requirement_fingerprint": sorted(
            Requirement.objects.values_list(
                "id", "title", "uid", "embedding_model"
            )
        ),
    }
