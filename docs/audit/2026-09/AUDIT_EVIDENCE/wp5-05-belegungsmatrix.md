---
type: REVIEW
scope: wp5-evidence-belegungsmatrix
status: final
date: 2026-09-29
author_agent: validator
---

# WP-5 Evidenz 5 — Belegungsgrad-Matrix

## 1. Methodik (ehrlich, ohne Hochrechnung)

Drei Messungen, alle mit *n* und Reproduktionsbefehl:

| # | Messung | Umfang | Verfahren |
|---|---|---|---|
| **M1** | Test-Referenz-Abdeckung | **n = 835 (100 %)** | Mengenoperation: alle `REQ-L*`-IDs aus `docs/se/L0` + `docs/se/L1` geschnitten mit allen IDs, die in `backend` / `frontend/src` / `e2e` **Testdateien** vorkommen. |
| **M2** | Selbst-deklarierter Marker | **n = 783 (94 % von 835)** | Parser über alle `### REQ-…`-Blöcke der Quelldokumente, `**Implementation State:**` je Block, „letzter gewinnt". 10 REQs ohne Marker. |
| **M3** | Code-Beleg | **n = 29 (stratifiziert)** | Pro L2-System **2** REQs: die erste mit Marker `Implemented` + die erste mit Marker `Not Implemented`/`Backlog`/`Planned`. → **20 von 20 Subsystemen abgedeckt**. Code-Nachweis über gezielte Symbol-/Datei-Suche in Produktionscode, Testverzeichnisse ausgeschlossen. |

**Nicht gemessen / extrapoliert:** L0- und L3-Code-Belegung. Eine Hochrechnung von
L2 auf L3 oder L0 wäre nicht belegbar, weil 300 der 354 L3-IDs in der Matrix gar
nicht auftauchen (Evidenz 1 §2.2) und der Matrix für L3 keinen Zeilensatz führt.

## 2. M1 — Test-Referenz-Abdeckung (100 % der REQs)

```
358 / 835 = 42.9 % mit mindestens einer REQ-ID-Referenz in einer Testdatei
477 / 835 = 57.1 % ohne jede
```

| Ebene | mit | ohne | Quote |
|---|---|---|---|
| L0 | 17 | 41 | 29.3 % |
| L1 | 35 | 59 | 37.2 % |
| L2 | 171 | 158 | **52.0 %** |
| L3 | 135 | 219 | 38.1 % |

Caveat: eine REQ-ID in einem Docstring ist eine **notwendige, nicht hinreichende**
Bedingung für echte Abdeckung. Die 42.9 % sind eine **Obergrenze** für
„anforderungsreferenzierte Tests".

Gegenprobe: von 10 052 Backend-Testdefinitionen beziehen sich **366** (3.6 %) auf
eine `REQ-L*`-ID. Tests sind also faktisch **modulorientiert**, nicht
anforderungsorientiert.

## 3. M2 — Selbst-deklarierter Implementierungsstand (n = 783)

Eigene Parser-Auswertung der Quelldokumente:

| Marker | Anzahl | Anteil (n=783) |
|---|---|---|
| Implemented | 459 | 58.6 % |
| Not Implemented | 221 | 28.2 % |
| Planned | 45 | 5.7 % |
| Backlog | 38 | 4.9 % |
| Deferred | 3 | 0.4 % |
| Teilweise Implementiert | 2 | 0.3 % |
| In Progress | 1 | 0.1 % |
| Freitext „Erfüllt durch bestehende Komponente …" | 4 | 0.5 % |
| **ohne Marker** | **10** | 1.3 % |

**Selbst-deklariert nicht umgesetzt** = Not Implemented + Planned + Backlog +
Deferred = **307** →

| Nenner | Wert | Anteil |
|---|---|---|
| 783 (alle REQs mit Marker) | 307 | **39.2 %** |
| 773 (nur explizite Enum-Marker) | 307 | **39.7 %** |
| 835 (alle Quell-REQ-IDs) | 307 | **36.8 %** |

Gegenprobe mit der Matrix §4.1 (`:659-664`): 334 von 811 = 41.2 %.
Eigene Messung 307 von 783 = 39.2 %. Abweichung −4.7 Prozentpunkte, erklärbar
durch 20 doppelt vergebene IDs, 10 markerlose REQs und die Freitext-Marker.

## 4. M3 — Belegungsgrad-Matrix, Stichprobe n = 29 (20/20 Subsysteme)

| REQ-ID | Ebene | Marker (Quelle) | Code-Beleg | Test-Beleg | Status |
|---|---|---|---|---|---|
| REQ-L2-AS-001 | L2 | Impl / Covered | ✔ `backend/application/*` (36 Dateien, Zyklenerkennung) | ✔ | **belegt** |
| REQ-L2-AS-005 | L2 | **Not Impl** / Covered | ✔ `backend/application/*` (34) | ✔ | belegt — **Marker veraltet** |
| REQ-L2-AL-001 | L2 | Impl / Covered | ✔ `backend/audit/writer.py`, 22 Prod-Dateien | ✔ | **belegt** |
| REQ-L2-AT-001 | L2 | Impl / Covered | ✔ `backend/auth_tenancy/services/password_authentication.py` | ✔ | **belegt** |
| REQ-L2-AT-018 | L2 | **Not Impl** / Missing | ✔ **18 Prod-Dateien**: `auth_tenancy/services/item_permission.py`, `rest_item_permission.py`, `permission_shadow.py`, `permission_cache.py`, `application/effective_permission_service.py`, Migration `0003_item_permission.py` | ✔ `tests/test_item_permission.py`, `test_item_permission_rest.py` | belegt — **Marker veraltet** |
| REQ-L2-BL-001 | L2 | Impl / Covered | ✔ `backend/baseline/delta_index_builder.py` | ✔ | **belegt** |
| REQ-L2-BL-008 | L2 | Not Impl / Missing | ✘ nur 2 Prod-Dateien, keine Performance-Messung | ✘ | **nur_doku** |
| REQ-L2-CM-001 | L2 | **Not Impl** / Missing | ✔ `backend/application/comment_service.py:51 class CommentService(ServiceBase)` (11.5 KB); `backend/rest_api/collaboration_views.py:105 class CommentViewSet`; MCP `backend/mcp_server/tools/comment.py:57 class CommentToolGroup` (`comment.create/list/resolve`, Registry `tool_registry.py:82,86,368`) | ✔ `application/tests/test_collaboration_models.py`, `test_collaboration_rls.py` | belegt — **Marker veraltet** |
| REQ-L2-AI-001 | L2 | Not Impl / Missing | ✘ `backend/ai_orchestration` existiert nicht (0 py); keine `AiOrchestration`-Komponente in `frontend/src/components` | ✘ | **aspirational** |
| REQ-L2-DS-001 | L2 | Impl / Covered | ✔ `backend/diagram/manager.py` | ✔ | **belegt** |
| REQ-L2-ICD-001 | L2 | Impl / Covered | ✔ `backend/icd/` (20) | ✔ | **belegt** |
| REQ-L2-LA-001 | L2 | Impl / Covered | ✔ `backend/llm_adapter/` (12) | ✔ | **belegt** |
| REQ-L2-LA-009 | L2 | Not Impl / kein Marker | ✔ `persistence` LlmSettings + REST | ✔ | belegt — **Marker veraltet** |
| **REQ-L2-MC-014** | L2 | **Impl / Covered** | ✘ **`rg 'semantic_search' backend frontend/src e2e` → 1 Treffer, ein Testmethodenname.** Kein `search.py` in `backend/mcp_server/tools/` (29 Module). Namenskonvention ist `<gruppe>.<verb>`; vorhanden ist `artifact.search` (lexikalisch), `tool_registry.py:418` | ✘ | **WIDERSPRUCH** |
| REQ-L2-MC-017 | L2 | Planned / Untested | ⚠ `mcp_server/throttling.py` existiert, Secret-Handling nicht verifizierbar | ✘ | **nur_doku** |
| REQ-L2-PL-001 | L2 | Impl / Covered | ✔ `backend/persistence/tenancy.py` (18) | ✔ | **belegt** |
| REQ-L2-PL-007 | L2 | **Not Impl** / Missing | ✔ `backend/reqogniloom/settings.py` (Pool-Parameter) | ✘ | belegt, ohne Test — **Marker veraltet** |
| REQ-L2-PC-001 | L2 | Impl / Covered | ✔ `backend/presets/registry.py` (11) | ✔ | **belegt** |
| **REQ-L2-RF-001** | L2 | Impl / **Missing** | ✔ 350 Prod-Dateien | ✔ | belegt — **aber WIDERSPRUCH** (112 fehlende Keys, `AUD-2026-09-002/-016`) |
| REQ-L2-RF-015 | L2 | **Not Impl** / Missing | ✔ `frontend/src/components/BaselinesView/BaselinesPanels.tsx:18-19` importiert `BaselineDiff`/`DiffItem`, `:166` *„REQ-L2-BL-003: baseline compare panel (field-level diff)"* | ✔ `BaselinesView.test.tsx` | belegt — **Marker veraltet** |
| REQ-L2-RQ-001 | L2 | **Not Impl** / Missing | ✔ `backend/application/reqif_import_service.py` (+`reqif_export_service.py`) | ✔ 9 Testdateien | belegt — **Marker veraltet** |
| **REQ-L2-RO-001** | L2 | Impl / Covered | ✔ `backend/resilience/dispatcher.py`, `tasks.py` | ✔ | belegt — **aber WIDERSPRUCH** (4× Fanout, `AUD-2026-09-120`) |
| REQ-L2-RA-001 | L2 | Impl / Covered | ✔ 22 ViewSet-Module in `backend/rest_api/` | ✔ | **belegt** |
| REQ-L2-RA-014 | L2 | Not Impl / Missing | ✘ kein `GlossaryTerm` in Serializer/URL/View | ✘ | **aspirational** |
| REQ-L2-SM-001 | L2 | Impl / Covered | ✔ `backend/rest_api/metrics_views.py` | ✔ | **belegt** |
| REQ-L2-TE-001 | L2 | Impl / Covered | ✔ `backend/traceability/` (18) | ✔ | **belegt** |
| REQ-L2-TE-014 | L2 | Not Impl / Missing | ✘ nur `query_engine.cross_project` (= TE-015, Query). **CRUD fehlt.** | ✘ | **aspirational** |
| REQ-L2-VS-001 | L2 | Not Impl / Missing | ✘ kein `VectorField`-/`semantic_search`-Einstiegspunkt | ✘ | **aspirational** |
| REQ-L2-WE-001 | L2 | Impl / Covered | ✔ `backend/workflow/definition_store.py` (9) | ✔ | **belegt** |

### 4.1 Auszählung der Stichprobe (n = 29)

| Status | n | Anteil |
|---|---|---|
| **belegt** (Code + Test-Referenz) | **14** | 48.3 % |
| **belegt, aber WIDERSPRUCH** (Beleg widerlegt das Verhalten) | 2 | 6.9 % |
| belegt, nur Code (kein Test-Bezug) | 1 | 3.4 % |
| **Marker veraltet** (Code **und** Tests existieren, REQ sagt „nicht implementiert") | **7** | 24.1 % |
| **nur_doku** (kein belastbarer Code-Nachweis) | 2 | 6.9 % |
| **aspirational** (weder Code noch Test) | 3 | 10.3 % |
| **Summe** | **29** | 100 % |

**Anteil aspirational in der Stichprobe (n = 29, L2, alle 20 Subsysteme): 10.3 %.**
Nimmt man `nur_doku` hinzu (kein belastbarer Nachweis): **17.2 %**.

Der größte Einzelblock ist der **invertierte Marker (24.1 %)**: sieben REQs sind
als nicht umgesetzt markiert, obwohl Produktionscode **und** Tests existieren
(`AS-005`, `AT-018`, `LA-009`, `PL-007`, `CM-001`, `RF-015`, `RQ-001`).

Vergleich mit der Selbstauskunft: dieselbe Stichprobe enthält **14 REQ mit Marker
`Implemented`**; davon sind **2 widerlegt** (MC-014 ohne Code, RO-001 mit
Fanout) und **2 mit falschem Test-Marker** (RF-001 „Missing" trotz 350
Prod-Dateien, PL-007 „Missing" trotz Settings-Code) → **28.6 % der
`Implemented`-Marker dieser Stichprobe sind nicht haltbar.**

> **Korrekturhinweis (Methodik-Transparenz):** Der erste Durchgang dieses
> Belegungsnachweises stufte `REQ-L2-CM-001` (Kommentar-CRUD) als *aspirational*
> und `REQ-L2-RF-015` (visuelles Baseline-Diff) als *aspirational*. Die
> Nachprüfung am konkreten Symbol (`CommentService`, `CommentViewSet`,
> `CommentToolGroup`, `BaselineDiff`) widerlegte beide Einstufungen. Keyword-Suche
> allein ist kein Nachweis — jeder aspirational-Einstufung in dieser Matrix liegt
> ein negativer Symbol-Nachweis zugrunde, kein bloßes Fehlertreffer-Muster.

## 5. Hochrechnung — mit expliziter Vorbehaltsangabe

Eine Hochrechnung des Stichprobenanteils auf alle 835 REQs ist **nicht
belastbar**, weil die Grundgesamtheit heterogen ist (L0/L1 ohne eigene Code-Prüfung,
L3 zu 86 % nicht in der Matrix). Belastbar sind nur zwei Aussagen:

| Aussage | Wert | Grundlage |
|---|---|---|
| **Selbst-deklariert nicht umgesetzt** | **36.8 %** (307/835) | M2, 100 %-Parse |
| **Keine Test-Referenz vorhanden** | **57.1 %** (477/835) | M1, 100 %-Mengenoperation |
| **Nachweislich ohne Code** (Stichprobe, stratifiziert, L2) | **10.3 %** aspirational / **17.2 %** inkl. `nur_doku` | M3, n = 29 |

**Konservative Gesamtschätzung des aspirationalen Anteils: 10.3 % bis 57.1 %.**
Die untere Grenze ist der Stichproben-Nachweis (n = 29, L2), die obere das
Fehlen jeder Test-Referenz (477/835). Beide sind gemessen, keine ist geschätzt.
Die Selbstauskunft der Dokumente (36.8 %) liegt dazwischen, ist aber als
*dokumentierte Absicht* zu lesen und als *Ist-Stand* nachweislich zu 24 %
**zu niedrig** (7 von 29 Stichproben-REQs sind invertiert markiert).

Der wahre Wert für „aspirational im Sinne von: versprochen, aber nicht
umgesetzt" ist die Obergrenze **57.1 %** (keine Test-Referenz) minus der Anteil
der REQs, die Code ohne Test haben — dieser Anteil wurde nicht gemessen, daher
ist 57.1 % die **belegte Obergrenze** und 10.3 % die **belegte Untergrenze**.

## 6. Systemische Beobachtung

Die Matrix-Felder *Impl. State* und *Test Status* sind **nicht gepflegt**:

- 4 von 29 Stichproben-REQs (13.8 %) sind als nicht-implementiert markiert,
  obwohl Code **und** Tests existieren.
- 2 von 14 `Implemented`-REQs (14.3 %) sind widerlegt.
- 1 von 14 `Implemented`-REQs trägt `Test Status: Covered`, obwohl der
  zugehörige Testverweis fehlt (RF-001).
- 13 von 21 L2-REQs der Matrix (`:399-411`) tragen **gar keinen** Marker.

Damit ist die Matrix als Belegquelle für den Implementierungsstand **nicht
verwertbar** — in beide Richtungen. Das ist die Ursache dafür, dass 324 REQ-IDs
aus der Matrix verschwunden sind und keine gepflegte Zählung existiert.
