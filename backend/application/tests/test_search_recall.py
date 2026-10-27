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

WHY ``hybrid >= vector`` IS NOT ASSERTED HERE (CR-02)
-----------------------------------------------------
The T-A3-4 recall clause has two halves: per ID query ``hybrid >= keyword``,
and overall ``hybrid >= vector``. Only the first half is a CI gate. The second
is deliberately a *report* number, for the same reason the synonym/thematic
subsets are: under the ``mock`` embedding provider ``vector`` returns
deterministic noise while ``hybrid`` is that same noise plus the lexical list,
so a CI assertion would compare two mock artefacts against each other and hold
by construction. That is a vacuous green — worse than no assertion, because it
reads like coverage. ``search_recall_report`` therefore computes the
``hybrid >= vector`` comparison per subset (Markdown table and the
``hybrid_ge_vector`` JSON field) and is run against a real embedding provider,
where the comparison has meaning.

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

WHY THE CORPUS IS LARGER THAN THE RECALL WINDOW (CR-01)
-------------------------------------------------------
The dataset stays small in absolute terms — the gate's job is to catch a
ranking regression, not to benchmark throughput — but it is deliberately
**larger than the window**: :data:`CORPUS_SIZE` rows against ``LIMIT = 10``. A
corpus at or below the window makes ``recall@10`` structurally unfalsifiable:
all expected rows fit into the first ten slots however badly the ranking
behaves, ``keyword`` recall is 100 % by construction, and ``hybrid >= keyword``
cannot fail. The decoys are realistic sibling requirements whose UIDs can never
collide with an ``expect_uid``, so an expected row has to *win* a slot instead
of merely being present. :class:`TestCorpusShape` pins that ratio so a future
"let's shrink the fixture" edit cannot quietly restore the unfalsifiable
window.
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
    Command,
    SubsetScore,
    load_recall_set,
)
from application.search_service import SearchService
from audit.models import AuditEntry
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
    make_user,
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
#: the expected UIDs. They also make the corpus larger than the recall window
#: (CR-01): with only as many rows as the window, ``recall@10`` is satisfied by
#: every expected row simply being present and the gate can never go red. The
#: UIDs above are chosen so no decoy UID contains an ``expect_uid`` as a
#: substring — the lexical pass matches on ``LIKE %uid%``, so an overlapping
#: UID would put a second candidate into every ID query's result list.
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
    {
        "uid": "REQ-L1-002",
        "title": "Mandantentrennung in der Datenbank",
        "description": (
            "Jede Abfrage ist auf den aktiven Mandanten eingeschränkt; "
            "Row-Level-Security erzwingt die Grenze in der Datenbank selbst."
        ),
    },
    {
        "uid": "REQ-L1-003",
        "title": "Barrierefreie Eingabemasken",
        "description": (
            "Alle Felder tragen ein Label und sind ohne Zeigegerät erreichbar "
            "(WCAG 2.1 AA)."
        ),
    },
    {
        "uid": "REQ-L1-005",
        "title": "Rücknahme eines abgebrochenen Imports",
        "description": (
            "Ein fehlgeschlagener Bulk-Import hinterlässt keine halb "
            "geschriebenen Datensätze."
        ),
    },
    {
        "uid": "REQ-L2-005",
        "title": "Wiederholung fehlgeschlagener Hintergrundjobs",
        "description": (
            "Ein Job wird dreimal mit wachsender Wartezeit wiederholt, bevor "
            "er als gescheitert gilt."
        ),
    },
    {
        "uid": "REQ-L2-011",
        "title": "Aufbewahrungsfrist für Protokolleinträge",
        "description": (
            "Einträge bleiben zwölf Monate lesbar und werden danach "
            "monatsweise archiviert."
        ),
    },
    {
        "uid": "REQ-L2-012",
        "title": "Umschaltung der Oberflächensprache",
        "description": (
            "Die Oberfläche wechselt zwischen Deutsch und Englisch, ohne die "
            "Sitzung zu verlieren."
        ),
    },
    {
        "uid": "REQ-L2-013",
        "title": "Sichtbarkeit einzelner Artefakte",
        "description": (
            "Eine Regel pro Nutzer und Artefakt entscheidet über Lesen und "
            "Schreiben."
        ),
    },
    {
        "uid": "REQ-L3-007",
        "title": "Veröffentlichtes Schema der Anbindung",
        "description": (
            "Das OpenAPI-Dokument wird bei jedem Build erzeugt und bleibt "
            "abwärtskompatibel."
        ),
    },
    {
        "uid": "REQ-L3-030",
        "title": "Begriffsglossar je Arbeitsbereich",
        "description": (
            "Fachbegriffe werden mit Definition und Synonymen zentral gepflegt "
            "und in der Suche aufgelöst."
        ),
    },
    {
        "uid": "REQ-L3-031",
        "title": "Versionierte Diagramme",
        "description": (
            "Jede Änderung an einem Diagramm erzeugt eine neue, unveränderliche "
            "Version."
        ),
    },
    {
        "uid": "REQ-L4-005",
        "title": "Bedienung ohne Zeigegerät",
        "description": "Alle Aktionen der Seitenleiste haben ein Tastenkürzel.",
    },
    {
        "uid": "REQ-L4-009",
        "title": "Kontrast der Statusfarben",
        "description": (
            "Statusfarben erreichen ein Kontrastverhältnis von mindestens 4.5:1."
        ),
    },
)

#: Every row the test creates. Must stay strictly larger than :data:`LIMIT` —
#: see the module docstring (CR-01); :class:`TestCorpusShape` enforces it.
CORPUS_SIZE = len(_EXPECTED_REQUIREMENTS) + len(_DECOY_REQUIREMENTS)


# ---------- helpers ----------


def _load_fixture() -> dict[str, Any]:
    return load_recall_set(DEFAULT_FIXTURE)


def _seed_corpus(workspace) -> dict[str, str]:
    """Create the recall corpus in *workspace*; return ``{uid: requirement id}``.

    The mapping covers every corpus row that carries a ``uid`` — expected rows
    *and* the UID-bearing decoys. Callers that need the expectation contract
    must therefore intersect with the fixture's ``expect_uid`` values rather
    than compare the mapping for equality (a decoy must never be able to
    satisfy an ID query by sharing a UID).

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


# ---------- corpus shape (no DB) ----------


class TestCorpusShape:
    """CR-01: a corpus at/below the window makes ``recall@10`` unfalsifiable.

    The corpus is 22 rows (6 expected + 16 decoys) against a window of 10; the
    invariant is the *relation*, not the number, so the fixture may grow but
    never shrink back to the window.
    """

    def test_corpus_is_larger_than_the_recall_window(self):
        assert CORPUS_SIZE > LIMIT, (
            f"corpus has {CORPUS_SIZE} rows for a recall window of {LIMIT}: "
            "every expected row fits into the window by construction, so "
            "recall@10 can never drop and 'hybrid >= keyword' can never fail. "
            "Add decoys instead of shrinking the corpus."
        )

    def test_no_decoy_uid_can_impersonate_an_expected_uid(self):
        expected = {row["uid"] for row in _EXPECTED_REQUIREMENTS}
        decoy_uids = {
            row["uid"] for row in _DECOY_REQUIREMENTS if "uid" in row
        }

        assert expected.isdisjoint(decoy_uids), (
            "a decoy repeats an expect_uid: "
            f"{sorted(expected & decoy_uids)}"
        )
        # The lexical pass matches ``uid LIKE %query%``, so a decoy UID that
        # *contains* an expected UID adds a second exact-tier candidate to that
        # query and makes the rank-1 assertion ambiguous rather than strict.
        overlapping = {
            (expected_uid, decoy_uid)
            for expected_uid in expected
            for decoy_uid in decoy_uids
            if expected_uid.lower() in decoy_uid.lower()
        }
        assert not overlapping, (
            f"decoy UIDs contain an expect_uid as a substring: {sorted(overlapping)}"
        )


# ---------- CI gate: ID subset ----------


@pytest.mark.django_db
class TestIdRecallGate:
    """``hybrid`` must not retrieve fewer expected rows than ``keyword``."""

    def test_hybrid_recall_is_at_least_keyword_recall_on_the_id_subset(
        self, monkeypatch
    ):
        """``hybrid >= keyword`` is only meaningful with a corpus > window.

        Every expected row has to *win* one of the ``LIMIT`` slots against
        :data:`CORPUS_SIZE` candidates; see the module docstring (CR-01).
        """
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        fixture = _load_fixture()
        expected_queries = _id_queries(fixture)
        expected_uids = {entry["expect_uid"] for entry in expected_queries}

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            resolved = _seed_corpus(workspace)
            ctx = editor_ctx(tenant, workspace)

            # Fixture and corpus must not drift apart: an ``expect_uid`` the
            # corpus does not create would silently score as a miss. Decoys
            # carry UIDs too, so this is a subset check, not an equality check
            # (an equality check would forbid every UID-bearing decoy).
            assert expected_uids <= set(resolved)
            # The unfalsifiable-window guard, measured on the real database
            # rather than only on the module constants: the corpus must be
            # bigger than the window the searches below use.
            corpus_rows = Requirement.objects.filter(
                artifact__workspace_id=workspace.id
            ).count()
            assert corpus_rows == CORPUS_SIZE
            assert corpus_rows > LIMIT

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
        """The pin's observable contract: rank 1, ``pinned`` *and* score 1.0.

        ``relevance_score == 1.0`` alone does not prove the pin: with three
        ranked lists the RRF maximum is ``3 / (_RRF_K + 1) == 3/61``, which
        normalises to 1.0 for any hit that is rank 0 in all three lists — an
        unpinned hit can reach the same number. ``SearchHit.pinned`` is the
        marker that says "lifted out of the fusion by the exact-match tier",
        so asserting it is what makes this test pin-sensitive (CR-04).

        With the pin disabled (``_PIN_MIN_NORMALIZED_LEXICAL_SCORE`` raised
        above the exact-UID tier) the hit stays at rank 1 but loses
        ``pinned`` and scores ~0.65 — the fused value, not the pinned one. A
        rank-1-only or score-only check would therefore not notice the
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
        assert top.pinned is True, (
            "the exact-UID hit reached rank 1 but was not pinned above the "
            "fused ranking (T-A3-2 exact-match pin regressed)"
        )
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
    """``search_recall_report`` is the QS surface for the non-gated subsets.

    It is also where the plan's ``hybrid >= vector`` clause is answered
    (CR-02), why the recall header follows ``--limit`` (CR-05) and why an empty
    role set has to be announced (CR-06).
    """

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
        # CR-02: the clause's verdict is part of every run, even when only one
        # half of the comparison was requested (then it is unmeasured, not
        # silently absent).
        assert "## hybrid vs vector (T-A3-4 recall clause)" in output
        assert "| Subset | hybrid recall@10 | vector recall@10 | hybrid >= vector |" in output
        assert "not measured for: id, id_negative, synonym, thematic" in output
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
        # CR-02: with only ``keyword`` requested the clause has no second
        # operand, so the verdict is ``None`` — never a fabricated ``False``.
        assert payload["hybrid_vs_vector"]["id"]["hybrid_ge_vector"] is None
        assert payload["hybrid_vs_vector"]["id"]["hybrid_recall"] is None
        assert payload["hybrid_vs_vector"]["id"]["vector_recall"] is None

    def test_report_json_hybrid_versus_vector_matches_the_measured_subsets(
        self, monkeypatch
    ):
        """CR-02: the printed verdict must agree with the numbers it compares."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            _seed_corpus(workspace)
            editor_ctx(tenant, workspace)

            stdout = StringIO()
            call_command(
                "search_recall_report",
                "--workspace",
                str(workspace.id),
                "--modes",
                "hybrid,vector",
                "--json",
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        hybrid = payload["modes"]["hybrid"]["subsets"]
        vector = payload["modes"]["vector"]["subsets"]
        for kind in QUERY_KINDS:
            row = payload["hybrid_vs_vector"][kind]
            assert row["subset"] == kind
            assert row["hybrid_satisfied"] == hybrid[kind]["satisfied"]
            assert row["vector_satisfied"] == vector[kind]["satisfied"]
            if hybrid[kind]["evaluated"] and vector[kind]["evaluated"]:
                expected = (
                    hybrid[kind]["satisfied"] * vector[kind]["evaluated"]
                    >= vector[kind]["satisfied"] * hybrid[kind]["evaluated"]
                )
                assert row["hybrid_ge_vector"] is expected, (
                    f"{kind}: printed verdict {row['hybrid_ge_vector']} disagrees "
                    f"with hybrid={hybrid[kind]['satisfied']}/"
                    f"{hybrid[kind]['evaluated']} vs vector="
                    f"{vector[kind]['satisfied']}/{vector[kind]['evaluated']}"
                )
            else:
                assert row["hybrid_ge_vector"] is None

    def test_report_header_follows_the_configured_limit(self, monkeypatch):
        """CR-05: ``--limit`` is the N in recall@N — the header must say so."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            _seed_corpus(workspace)
            editor_ctx(tenant, workspace)

            stdout = StringIO()
            call_command(
                "search_recall_report",
                "--workspace",
                str(workspace.id),
                "--modes",
                "keyword",
                "--limit",
                "7",
                stdout=stdout,
            )

        output = stdout.getvalue()
        assert "| Subset | recall@7 | Rang-1-Treffer | n |" in output
        assert "| Subset | hybrid recall@7 | vector recall@7 | hybrid >= vector |" in output
        assert "recall@7 is subset-specific" in output
        assert "recall@10" not in output

    def test_report_warns_when_the_caller_holds_no_role(self, monkeypatch):
        """CR-06: an empty role set must not yield a silent, identical report."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")

        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            _seed_corpus(workspace)
            # A tenant member with no role in *this* workspace: the search still
            # runs, but permission-scoped hits are filtered by an empty role set.
            roleless = make_user(tenant)

            stdout = StringIO()
            stderr = StringIO()
            call_command(
                "search_recall_report",
                "--workspace",
                str(workspace.id),
                "--user",
                str(roleless.id),
                "--modes",
                "keyword",
                "--json",
                stdout=stdout,
                stderr=stderr,
            )

        warning = stderr.getvalue()
        assert "holds no active role in workspace" in warning
        assert str(roleless.id) in warning
        # The warning is a warning: the report itself is still produced.
        assert json.loads(stdout.getvalue())["query_count"] == 20

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

    def test_default_user_prefers_the_alphabetically_first_tenant_admin(self):
        """CR-06: identity resolution must not follow primary-key order.

        ``QuerySet.first()`` on an unordered queryset falls back to
        primary-key order, so the role rows are created with explicit inverted
        ids: the pk-order winner (``zulu-admin``) and the alphabetical winner
        (``alpha-admin``) are then guaranteed to differ. Without the explicit
        ``order_by`` the lookup deterministically returns ``zulu-admin``, so
        this test cannot pass by luck on a run where the fix is missing.
        """
        from uuid import UUID

        from auth_tenancy.models import TenantRole

        with active_tenant() as tenant:
            for username, role_id in (
                ("zulu-admin", UUID(int=1)),
                ("alpha-admin", UUID(int=2**128 - 1)),
            ):
                admin = make_user(tenant, username=username)
                TenantRole.objects.create(
                    id=role_id,
                    tenant=tenant,
                    user=admin,
                    role=TenantRole.ROLE_ADMIN,
                )

            resolved = Command._default_user(tenant.id)

        assert resolved is not None
        assert resolved.username == "alpha-admin"


# ---------- hybrid >= vector clause (no DB) ----------


class TestHybridVersusVectorComparison:
    """CR-02: the clause's arithmetic, without a search or a database.

    The clause itself is reported, not gated (see the module docstring), so the
    part worth pinning in CI is that the command computes the verdict correctly
    — including the ``False`` case, which is the one a mock provider would
    never produce.
    """

    @staticmethod
    def _compare(
        *,
        hybrid: dict[str, tuple[int, int]],
        vector: dict[str, tuple[int, int]] | None,
    ) -> dict[str, dict[str, object]]:
        def scores(by_kind: dict[str, tuple[int, int]]) -> dict[str, SubsetScore]:
            built = {kind: SubsetScore(kind) for kind in QUERY_KINDS}
            for kind, (satisfied, evaluated) in by_kind.items():
                built[kind].satisfied = satisfied
                built[kind].evaluated = evaluated
            return built

        per_mode = {"hybrid": scores(hybrid)}
        if vector is not None:
            per_mode["vector"] = scores(vector)
        return Command._compare_hybrid_with_vector(per_mode)

    def test_verdict_is_true_when_hybrid_matches_vector(self):
        comparison = self._compare(
            hybrid={"id": (6, 6)},
            vector={"id": (6, 6)},
        )

        assert comparison["id"]["hybrid_ge_vector"] is True

    def test_verdict_is_false_for_a_worse_hybrid_recall(self):
        comparison = self._compare(
            hybrid={"id": (3, 6)},
            vector={"id": (6, 6)},
        )

        row = comparison["id"]
        assert row["hybrid_ge_vector"] is False
        # The false case must carry both numbers, or it is an unarguable "no".
        assert row["hybrid_recall"] == pytest.approx(0.5)
        assert row["vector_recall"] == pytest.approx(1.0)

    def test_verdict_is_none_without_the_vector_mode(self):
        comparison = self._compare(hybrid={"id": (6, 6)}, vector=None)

        assert comparison["id"]["hybrid_ge_vector"] is None
        assert comparison["id"]["vector_recall"] is None

    def test_verdict_is_none_when_a_subset_was_not_evaluated(self):
        comparison = self._compare(
            hybrid={"id": (0, 0)},
            vector={"id": (0, 0)},
        )

        assert comparison["id"]["hybrid_ge_vector"] is None

    def test_equal_fractions_compare_equal_without_float_rounding(self):
        comparison = self._compare(
            hybrid={"id": (2, 3)},
            vector={"id": (4, 6)},
        )

        assert comparison["id"]["hybrid_ge_vector"] is True


def _row_snapshot() -> dict[str, object]:
    """Row counts plus a content fingerprint for the tables this command reads.

    A count alone cannot prove "read-only": an in-place edit would leave every
    count unchanged. The fingerprints cover the fields a search could plausibly
    touch (identity, title, UID) — an embedding rewrite is caught by the
    ``embedding_model`` column of the fingerprint.

    ``AuditEntry`` is counted too (CR-07): the append-only trail is the one
    table a search could plausibly *gain* a row in (a read that leaks into an
    audited service call), and no count of the read tables would show it.
    """
    return {
        "Artifact": Artifact.objects.count(),
        "Requirement": Requirement.objects.count(),
        "ArtifactVersion": ArtifactVersion.objects.count(),
        "TraceLink": TraceLink.objects.count(),
        "AuditEntry": AuditEntry.objects.count(),
        "requirement_fingerprint": sorted(
            Requirement.objects.values_list(
                "id", "title", "uid", "embedding_model"
            )
        ),
    }
