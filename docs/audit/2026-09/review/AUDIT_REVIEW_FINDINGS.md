---
type: REVIEW
scope: audit-review-findings
status: final
date: 2026-10-01
author_agent: validator
branch: chore/audit-review-2026-09
source:
  - docs/audit/2026-09/review/evidence/REVIEW_WP1A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1B.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C_SUPP.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1D.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP2.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP3.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP4.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP5.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6B.md
  - docs/audit/2026-09/review/evidence/REVIEW_LIVE_CRITICALS.md
---

# AUDIT_REVIEW_FINDINGS — verdiktbasiertes Findings-Register der Audit-Review

> **Rolle dieses Dokuments.** Reine **Aggregation und Konsistenzprüfung** der
> vorhandenen Review-Evidenz. Es wird **keine neue Fachanalyse** betrieben und
> **kein neues Finding erfunden**. Die Original-Schweregrade stammen wörtlich aus
> `AUDIT_FINDINGS.md` §3 (Spalte „Sev (orig)"), die Verdikte wörtlich aus den
> jeweiligen `REVIEW_*`-Evidenzdateien. Gegenbeweise sind auf `file:line` +
> Kurzzitat reduziert; Vollzitate stehen in den Evidenzdateien.

**Verdikt-Vokabular (exakt):** `BESTAETIGT | TEILWEISE | FALSCH | UEBERZOGEN |
UNTERSCHAETZT | NICHT VERIFIKABAR | KEIN REQOGNILOOM-BEZUG`.
Bei abweichendem Schweregrad ist die Korrektur Pflicht (Spalte „Korrigierter
Schweregrad").

**Hinweis zur Referenzbasis.** Die statischen Reviews prüften gegen
`HEAD 10dc620f` (WP-3 gegen `636de7d4`; WP-6b `bf49b0f`); der Auftrags-HEAD ist
`636de7d4`. Zwischen Audit-Basis `abd61aed` und HEAD existieren nur Doku-Commits,
für `backend/**`/`frontend/**` inhaltsgleich (siehe Einzelreviews).

---

## 1. Aggregat

### 1.1 Verdikt-Verteilung je Workpackage

`geprüft` zählt geprüfte Finding-Einträge; WP-1d enthält zusätzlich die Kontrolle
`AUD-070` (nicht in der Finding-Zahl). `UNTERSCHAETZT` trat als Primärverdikt nicht
auf; `AUD-002` trägt es als Zusatzattribut.

| WP | geprüft | BESTAETIGT | TEILWEISE | FALSCH | UEBERZOGEN | NICHT VERIFIKABAR | KEIN BEZUG | Schweregrad-Korrekturen |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WP-1a | 19 | 13 | 4 | 1 | 1 | 0 | 0 | 1 |
| WP-1b | 15 | 9 | 5 | 0 | 1 | 0 | 0 | 8 |
| WP-1c | 10 | 8 | 1 | 0 | 1 | 0 | 0 | 1 |
| WP-1c-Supp | 20 | 13 | 5 | 1 | 1 | 0 | 0 | 5 |
| WP-1d | 18 (+1 Kontrolle) | 10 | 7 | 0 | 1 | 0 | 0 | 1 |
| WP-2 | 22 | 16 | 2 | 0 | 3 | 0 | 1 | 3 |
| WP-3 / 3b | 27 | 14 | 12 | 0 | 0 | 1 | 0 | 0 |
| WP-4 | 33 | 24 | 6 | 0 | 1 | 2 | 0 | 3 |
| WP-5 | 32 | 21 | 10 | 1 | 0 | 0 | 0 | 2 |
| WP-6a | 18 | 9 | 7 | 0 | 1 | 0 | 1 | 1 |
| WP-6b | 19 | 15 | 1 | 1 | 2 | 0 | 0 | 2 |
| **Gesamt** | **233** (+1 Kontrolle) | **152** | **60** | **4** | **12** | **3** | **2** | **27** |

**Summenkontrolle:** 152 + 60 + 4 + 12 + 3 + 2 = **233** Finding-Einträge.
Zusätzlich 1 Kontrolle (`AUD-070`, WIDERLEGUNG bestätigt) = 234 Tabellenzeilen.

### 1.2 Abdeckung Critical/High

| Klasse | Register (Original-Sev) | geprüft | Abdeckung |
|---|---:|---:|---:|
| Critical | 14 (13 offen + 1 zurückgezogen `AUD-070`) | 14 | **100 %** |
| High | 76 | 76 | **100 %** |
| Medium/Low/Info | 189 | 143 | **~75,7 %** |
| **Summe** | **279** | **233** | **~83,5 %** |

Alle 13 offenen Criticals und alle 76 High-Findings wurden mindestens einmal
gegengeprüft; `AUD-070` (zurückgezogen) wurde als Kontrolle mitgeprüft.

### 1.3 Verteilung nach Fehlerklasse

**Nicht disjunkt** — ein Finding kann mehrere Klassen tragen. „Nennungen" =
Anzahl Findings, bei denen die Klasse in der Review-Evidenz belegt ist.

| Fehlerklasse | Nennungen | Belegte IDs (Auszug) |
|---|---:|---|
| Severity falsch eingestuft (auf-/abgestuft) | 27 | 034, 052, 056, 060, 061, 062, 063, 065, 066, 077, 101, 110, 117, 121, 122, 130, 134, 142, 147, 161, 180, 228, 273, 282, 327, 345, 346 |
| Sachkern falsch (Verdikt FALSCH) | 4 (+6 Teil-FALSCH) | FALSCH: 042, 121, 204, 283 · Teil-FALSCH: 006, 016, 021, 088, 153, 234 |
| Duplikat / Doppelführung / stale Referenz | 10 Beziehungen | 345→123, 346→052, 143=#1019, 241↔148, 121(b)↔125/270, 231↔055/063, 221↔030, 227↔184/185, 002/016/300, 349→070 |
| Fehlzitat (falscher `file:line`-Anker) | 12 | 032, 042, 053, 067, 074, 076, 080, 086, 139, 222, 280, 282 |
| Scope-Verfehlung (kein Produktbezug) | 2 (+2 Orts-/Sync-Hygiene) | 239, 152 · Hygiene: 204 (Register-Sync), 220 (Fundort am HEAD redigiert) |
| Zahlenfehler (Zahl nicht reproduzierbar/falsch) | 22 | 001, 002, 039, 085, 130, 132, 142, 147, 156, 160, 180, 188, 192, 193/195, 225, 234, 287, 300, 302, 303, 310, 311, 325 |

---

## 2. Gegenbeweis-Tabelle (je WP, innerhalb WP nach ID sortiert)

### WP-1a — MCP Server (`REVIEW_WP1A.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-030 | WP-1a | Critical | NEU | TEILWEISE | Critical (unverändert) | `settings.py:879-884` kein `OPTIONS`/`SOCKET_TIMEOUT`; `views.py:272,401,505,736`; `throttling.py:164` | Mechanik bestätigt; „13 Endpoints" sind Proben, nicht Endpunkte. Live: MCP hängt 8 s (REVIEW_LIVE_CRITICALS) |
| AUD-031 | WP-1a | Critical | NEU | BESTAETIGT | Critical (unverändert) | `health.py:118-315` (0 Cache-Treffer); `:312-315` | Kern-Gap (keine Cache/Worker/Beat-Probe). Live: Redis down → `/health/` 200 ok |
| AUD-032 | WP-1a | High | NEU | TEILWEISE | High (unverändert) | `views.py:291-304`/`:311-325` beide str; `protocol_handler.py:264-268` int | Kern stimmt; zitiertes Zeilenpaar beweist int/str nicht → Fehlzitat |
| AUD-033 | WP-1a | High | NEU | BESTAETIGT | High (unverändert) | `protocol_handler.py:536` außerhalb try; `:489` | bestätigt; nur nicht-leere Nicht-dicts |
| AUD-034 | WP-1a | High | NEU | UEBERZOGEN | **High → Medium** | `authentication.py:616`; `api_key_views.py:290-301` validiert | über API/MCP nicht erreichbar |
| AUD-035 | WP-1a | High | NEU | BESTAETIGT | High (unverändert) | `authentication.py:511-515`, `:562` | `ApiKey.tenant_id` im Auth-Pfad ungenutzt |
| AUD-036 | WP-1a | High | NEU | BESTAETIGT | High (unverändert) | `generic.py:512-515` vs `:496-499`; REST `_EXC_TO_CODE` | Transport-Paritätsbruch |
| AUD-037 | WP-1a | Medium | NEU | BESTAETIGT | Medium (unverändert) | `AGENTS.md:8`; `README.md:77,1191`; manifest 219 | 215/31 stale; 25-vs-35; stdio-Phantom |
| AUD-039 | WP-1a | Medium | NEU | BESTAETIGT | Medium (unverändert) | `protocol_handler.py:469`; `:229-241` | bestätigt |
| AUD-041 | WP-1a | Medium | NEU | BESTAETIGT | Medium (unverändert) | `views.py:176-190`; `grep redact` = 0 | statisch bestätigt; Live-Log-Repro blockiert (Docker down) |
| AUD-042 | WP-1a | Medium | NEU | **FALSCH** | — | `interview.py:85-95` `session_kind`; `:305-315,322`; Zitat `:181-202` = formalize | Multi startbar seit 2026-08-25; Zitat + Aussage falsch |
| AUD-043 | WP-1a | Medium | NEU | TEILWEISE | Medium (unverändert) | Manifest kein `workspace_id`; `workspace_scope.py:115,172` | Schema-Lücke bestätigt, Symptom unbelegt |
| AUD-045 | WP-1a | Low | NEU | BESTAETIGT | Low (unverändert) | `protocol_handler.py:226-241`, `:476` | `id`-Typ ungeprüft |
| AUD-046 | WP-1a | Low | NEU | BESTAETIGT | Low (unverändert) | `generic.py:493`; `glossary_service.py:166` | `AttributeError` → INTERNAL_ERROR |
| AUD-047 | WP-1a | Low | NEU | BESTAETIGT | Low (unverändert) | `glossary_service.py:156-167`; `models.py:2387` | keine Längengrenze für `definition` |
| AUD-048 | WP-1a | Low | NEU | BESTAETIGT | Low (unverändert) | `test_tool_manifest_drift.py:83`; `:23-26` | DB-Setup unnötig |
| AUD-049 | WP-1a | Info | NEU | BESTAETIGT | Info (unverändert) | `urls.py:52`, `:59`; Kommentar `:57-58` | bestätigt |
| AUD-050 | WP-1a | Info | WIDERLEGT | BESTAETIGT (Widerlegung) | Info (unverändert) | `authentication.py:562`; `tool_registry.py` | kein Cross-Tenant-Leak; Ursache = 035 |
| AUD-051 | WP-1a | Info | NEU | TEILWEISE | Info (unverändert) | `test_tool_manifest_drift.py:102-157` | Guard bestätigt; „12/12" nicht aus Produktcode ableitbar |

### WP-1b — LLM-Adapter (`REVIEW_WP1B.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-052 | WP-1b | Critical | NEU | TEILWEISE | **Critical → High** | `providers.py:1080,853,120-121,167-168`; `settings.py:704` mock | Kern bestätigt; „retired seit 2026-01-05" extern NICHT VERIFIKABAR; Trigger opt-in. Live: Shipped-Default mock |
| AUD-053 | WP-1b | High | NEU | TEILWEISE | High (unverändert) | `providers.py:1333` gpt-4; `.env.example:184,189` | Retirement extern; `.env.example:189` gpt-4o → Fehlzitat |
| AUD-054 | WP-1b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `providers.py:1549-1550` | `prompt_eval_count` verworfen |
| AUD-055 | WP-1b | High | NEU | BESTAETIGT | High (unverändert) | `providers.py:1100,1347,1689`; `resilient_transport.py:39,279-285`; `policy_engine.py:92-93` | 4 × 3 = 12 statisch exakt |
| AUD-056 | WP-1b | Medium | NEU | UEBERZOGEN | **Medium → Low** | `tasks.py:77`; `settings.py:850-851` | globales Hard-Limit 180 s → „kein Abbruch" falsch |
| AUD-057 | WP-1b | High | NEU | BESTAETIGT | High (unverändert) | `providers.py:1215,1407,1595,1749,1941`; `dispatcher.py:187-193` | verschärft: `decompose` ungehärtet |
| AUD-058 | WP-1b | High | NEU | BESTAETIGT | High (unverändert) | `providers.py:2014`; `models.py:2417-2421`; `llm-settings.ts:22` | Env-Pfad existiert; DB/UI fehlen |
| AUD-059 | WP-1b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `providers.py:1114-1118,1160-1164,1216-1220,1270-1274` | `usage=None` → AttributeError |
| AUD-060 | WP-1b | Medium | NEU | BESTAETIGT | **Medium → Low** | `providers.py:829` `json.dumps([])` | `purpose` entwickler-kontrolliert |
| AUD-061 | WP-1b | High | NEU | TEILWEISE | **High → Medium** | `providers.py:390,413,438,455`; `router.py:286-292` | Mock-Zahlen persistieren; kein realer Kostenpfad |
| AUD-062 | WP-1b | High | NEU | TEILWEISE | **High → Medium** | `router.py:286-292`; `tasks.py:166-172`; `token_tracking.py:194-204` | Provider-Attribution existiert; Input/Output fehlt |
| AUD-063 | WP-1b | Medium | NEU | BESTAETIGT | **Medium → Low** | `token_tracking.py:123-129,162-165,233-243` | Fail-open dokumentiert |
| AUD-065 | WP-1b | Medium | NEU | TEILWEISE | **Medium → Low** | `checks.py:40-50`; `health_rest.py:273-278,304-324` | Laufzeit-Check existiert → „ungedeckt" überzogen |
| AUD-066 | WP-1b | High | NEU | BESTAETIGT | **High → Medium** | `dispatcher.py:177-178,149-151` | Beobachtbarkeitslücke |
| AUD-067 | WP-1b | Info | NEU | BESTAETIGT (Sachverhalt) | Info (unverändert) | `resilient_transport.py:159-175,178-196` | Fehlzitat: `audit_logger.py:174-191` falsch |

### WP-1c — Infrastruktur (`REVIEW_WP1C.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-122 | WP-1c | Critical | NEU | UEBERZOGEN | **Critical → High** | `backup.sh:84-87`; `compose.yml:348-505` Sidecar; `UMSETZUNGSPLAN:152` | dead legacy code; kein Datenverlustpfad |
| AUD-123 | WP-1c | Critical | NEU | BESTAETIGT | Critical (unverändert) | `restore.sh:183,186,198-201` | Datei nie in Container kopiert |
| AUD-124 | WP-1c | High | NEU | BESTAETIGT | High (unverändert) | `restore.sh:49,116`; `compose.yml:372,405` | Format-/Ort-Mismatch |
| AUD-125 | WP-1c | High | NEU | BESTAETIGT | High (unverändert) | `archive.py:448`; kein `audit/tasks.py`; `celery.py:45` | Task nicht registriert |
| AUD-126 | WP-1c | High | NEU | BESTAETIGT | High (unverändert) | `settings.py:777-951` grep 0 | pre-ack ohne Retry |
| AUD-127 | WP-1c | High | NEU | BESTAETIGT | High (unverändert) | `restore.sh:183,198,206` | nicht atomar |
| AUD-128 | WP-1c | High | NEU | BESTAETIGT | High (unverändert) | `compose.yml:357,361,372` | 42 h, kein Off-Host |
| AUD-129 | WP-1c | High | NEU | TEILWEISE | High (unverändert) | `health.py:118-313`; `:134-135,160-161` 503 | Kern ja; „degraded → 200" falsch |
| AUD-137 | WP-1c | High | NEU | BESTAETIGT | High (unverändert) | `docker-publish.yml:26-27,102,168`; `ci.yml:4-7` | alle 3 Teilaussagen |
| AUD-149 | WP-1c | High | NEU | BESTAETIGT | High (unverändert) | keine Staging-Def.; `pages.yml:31,38` | Prozesslücke |

### WP-1c-Supp — Infrastruktur-Ergänzung (`REVIEW_WP1C_SUPP.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-120 | WP-1c | Critical | NEU | BESTAETIGT | Critical (unverändert) | `celery.py:31-37`; Live `_kombu.binding.default` = 4 Members | 4× Zustellung live bestätigt |
| AUD-121 | WP-1c | Critical | NEU | **FALSCH** | **Critical → Low** (Rest) | `compose.yml:947,817-830`; DB-Zähler; `archive.py:448` | Beat dispatcht doch (live); (b) = Duplikat 125/270 |
| AUD-130 | WP-1c | Medium | NEU | TEILWEISE | **Medium → Low** | `ai_derivation_service.py:396,500,373,2235,2433,481-506` | no-TTL = Versionszähler; invalidiert |
| AUD-131 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `compose.yml:543,545`; `settings.py:879-884`; Live `CONFIG GET` | noeviction 256 MB |
| AUD-132 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `settings.py:793`; Live db0 = 2425; TTL ≤ 86400 | Zahl 5914 nicht reproduziert (live 2425) |
| AUD-133 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `sse_pubsub.py:29-31,48,52,56`; `settings.py:792` | Sessions in db0 (Broker) |
| AUD-134 | WP-1c | Medium | NEU | UEBERZOGEN | **Medium → Low** | `cache_generation.py:80`; `ai_derivation_service.py:413` | UUID global eindeutig; nur Defense-in-Depth |
| AUD-135 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `compose.yml:1015,1030,1046,1108` | 4 honcho ohne `logging:` |
| AUD-136 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `compose.yml:1047,1109,1231`; `grep @sha256` = 0 | kein Digest-Pinning |
| AUD-138 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `build.sh:88-94`; `grep build:` = 0; Live exit 0 | falsche Erfolgsmeldung |
| AUD-139 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `compose.yml:641-642`; `urls.py:28` | getrennte livez/readyz fehlen. Fehlzitat `:139,147` |
| AUD-140 | WP-1c | Low | NEU | BESTAETIGT | Low (unverändert) | `test.yml:54-56` | `depends_on` ohne condition |
| AUD-141 | WP-1c | Medium | NEU | BESTAETIGT | Medium (unverändert) | `settings.py:899-953`; requirements grep 0; Live `/metrics/` 404 | kein Exporter/`LOG_LEVEL` |
| AUD-142 | WP-1c | Medium | NEU | TEILWEISE | **Medium → Low** | `.env.example:571`; 7 fehlende Variablen | 8 → 7; `CELERY_CONCURRENCY` doch dokumentiert |
| AUD-143 | WP-1c | Medium | DUPLIKAT | BESTAETIGT | Medium (unverändert) | `embedding_dimensions.py:84`; Live 4× `vector(384)` | Kontrolle: korrekt DUPLIKAT #1019 |
| AUD-144 | WP-1c | Low | NEU | TEILWEISE | Low (unverändert) | `pg_indexes pl_artifact`; `idx_artifact_parent_btree` | nur 1 exaktes Duplikat (nicht 4) |
| AUD-145 | WP-1c | Low | NEU | TEILWEISE | Low (unverändert) | `compose.yml:887`; `override.yml:131` | Ursache Dev-Override |
| AUD-146 | WP-1c | Low | NEU | BESTAETIGT | Low (unverändert) | `tasks.py:188-189` vs `settings.py:347` | stale Kommentar (60 statt 0) |
| AUD-147 | WP-1c | Medium | NEU | TEILWEISE | **Medium → Low** | Live `SHOW` 300 / shared_buffers 128 MB | Zahl 160 MB falsch |
| AUD-148 | WP-1c | Low | NEU | BESTAETIGT | Low (unverändert) | `compose.yml:73,1020,1053` | Klartext-Default; Duplikat 241 |

### WP-1d — REST API & Data Integration (`REVIEW_WP1D.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-070 | WP-1d | Critical → Info | WIDERLEGT | BESTAETIGT (Kontrolle) | Info (unverändert) | `import_service.py:341-344,347`; Export `:382` | Widerlegung korrekt |
| AUD-071 | WP-1d | Critical | NEU | BESTAETIGT | Critical (unverändert) | `reqif_import_service.py:482-489,273-287,688-703,429-441` | `success` hart; Savepoint unwirksam. Live NICHT VERIFIKABAR (Mutation) |
| AUD-072 | WP-1d | High | NEU | BESTAETIGT | High (unverändert) | `import_service.py:662,695,179-323` | keine Dedupe |
| AUD-073 | WP-1d | High | NEU | BESTAETIGT | High (unverändert) | `views.py:3111,8369,3249-3252,253-254,5335-5337` | 500 vs 404 Mechanik. Live bestätigt |
| AUD-074 | WP-1d | High | NEU | BESTAETIGT | High (unverändert) | `api_key_views.py:147-158`; `user_management_views.py:104-126`; `link_type_views.py:56-93` | 4 Listen ungepaggt. Live 200 Items/54451 B. Fehlzitate |
| AUD-075 | WP-1d | High | NEU | TEILWEISE | High (unverändert) | `openapi.py:71-98`; `test_openapi.py` | Struktur ja; 432/439 nicht nachzählbar |
| AUD-076 | WP-1d | High | NEU | TEILWEISE | High (unverändert) | `reqif_export_service.py:394-402,409` | Code setzt 1.2; XSD nicht prüfbar; Fehlzitat `:296` |
| AUD-077 | WP-1d | High | NEU | UEBERZOGEN | **High → Low/Medium** | `error_envelope.py:61-67`; `middleware.py:85` | `X-Request-ID`-Header existiert |
| AUD-078 | WP-1d | High | NEU | BESTAETIGT | High (unverändert) | `views.py:8265,8216-8217`; media_type `application/xml` | Asymmetrie + Schema-Lücke |
| AUD-079 | WP-1d | Medium | NEU | TEILWEISE | Medium (unverändert) | `import_service.py:380-411,610,300-314` | Rollback mit leerer `errors`-Liste belegt; Live offen |
| AUD-080 | WP-1d | Medium | NEU | TEILWEISE | Medium (unverändert) | `import_service.py:346-354`; Fehlzitat `:196` | „still" plausibel; Restzeile datenabhängig |
| AUD-081 | WP-1d | Medium | NEU | TEILWEISE | Medium (unverändert) | `export_service.py:372-376`; `settings_views.py:579-585`; `import_service.py:529` | Struktur gestützt; Live-Codes offen |
| AUD-083 | WP-1d | Medium | NEU | BESTAETIGT | Medium (unverändert) | `views.py:8018`; `import_service.py:347,396` | BOM-Ursache klar (`decode utf-8`) |
| AUD-085 | WP-1d | Medium | NEU | BESTAETIGT | Medium (unverändert) | `urls.py:51-52,59`; `settings.py:591` | 6 unbeabsichtigt statt 7 |
| AUD-086 | WP-1d | Medium | NEU | BESTAETIGT | Medium (unverändert) | `traceability/pdf_report_generator.py:220` | Defaultfonts; Fehlzitat Modulpfad |
| AUD-088 | WP-1d | Low | NEU | TEILWEISE | Low (unverändert) | `jwt_tokens.py:114-125`; `authentication.py:218` | Klammer „alle invalid_signature" falsch |
| AUD-090 | WP-1d | Low | NEU | BESTAETIGT | Low (unverändert) | `settings.py:523,593,597-621` | `cookieAuth` unreferenziert |
| AUD-092 | WP-1d | Low | NEU | TEILWEISE | Low (unverändert) | `models.py:1473-1482`; kein `*1005*` | `null=True`; Menge ~888 live offen |
| AUD-093 | WP-1d | Info | NEU | BESTAETIGT | Info (unverändert) | `workspace_service.py:187`; `audit_views.py:219` | zwei 404-Texte |

### WP-2 — Native Plugins (`REVIEW_WP2.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-100 | WP-2 | High | NEU | BESTAETIGT | High (unverändert) | `.gitignore:2`; `hermes-plugin.json:7`; `git ls-files` leer | `main` gitignored + keine Doku |
| AUD-101 | WP-2 | High | NEU | UEBERZOGEN | **High → Low** | Design-Spec `:44-74`; `dashboard/manifest.json:1-11` | Manifest-Typen verwechselt |
| AUD-102 | WP-2 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `hermes-plugin.json:14-20,36`; `activate.ts:60-75` | Command nie registriert |
| AUD-103 | WP-2 | Low | NEU | BESTAETIGT | Low (unverändert) | `hermes-plugin.json:40-46` | `engines`/`permissions` ungenutzt |
| AUD-104 | WP-2 | Low | NEU | BESTAETIGT | Low (unverändert) | `hermes-plugin.json` (gesamtes Dokument) | kein `capabilities`/`tools`/`minHostVersion` |
| AUD-105 | WP-2 | Low | NEU | BESTAETIGT | Low (unverändert) | `hermes-plugin.json` kein `auth`; `ConnectScreen.tsx:19,55` | Token nur UI |
| AUD-106 | WP-2 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `plugin.yaml:2`; `manifest.json:6`; `build_hermes_plugin.py:20,28-43` | Versions-Drift |
| AUD-107 | WP-2 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `protocol_handler.py:503-505`; `views.py:431` | serverInfo 1.0.0 hart |
| AUD-108 | WP-2 | Low | NEU | BESTAETIGT | Low (unverändert) | `version.py:89-103`; Live `unknown` | Version nicht belegbar |
| AUD-109 | WP-2 | High | NEU | BESTAETIGT | High (unverändert) | `api.ts:149-152`; `reqogniloom_client.py:136-139`; `serializers.py:360` | 25 von 401 live; Ziel Rang 400 |
| AUD-110 | WP-2 | High | NEU | UEBERZOGEN | **High → Medium** | `__init__.py:62`; `interview_service.py:180-183` | 400 VALIDATION_ERROR sichtbar |
| AUD-111 | WP-2 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `__init__.py:138`; `interview_service.py:1292`; `mcpClient.ts:168-176` | `artifact_id` existiert nicht |
| AUD-112 | WP-2 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `interview_views.py:207-209`; `reqogniloom_client.py:54-60,197-204` | kein `count` |
| AUD-113 | WP-2 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `SKILL.md:20-42`; agents 0 Treffer | 10 interview-Tools ungewhitelistet |
| AUD-114 | WP-2 | High | NEU | TEILWEISE | High (unverändert) | `test_slash_command.py:40`; `api.test.ts:8-9` | Py-Fixture verdeckt 115; TS schwächer |
| AUD-115 | WP-2 | Critical | NEU | BESTAETIGT | Critical (unverändert) | `__init__.py:79,77-78,110,120,127,162`; `interview_service.py:392,428` | `TypeError` nicht gefangen |
| AUD-116 | WP-2 | Low | NEU | BESTAETIGT | Low (unverändert) | `api.ts:113`; `state.ts:140`; `mcpClient.ts:60` | Timeout ≡ Connection failed |
| AUD-117 | WP-2 | High | NEU | UEBERZOGEN | **High → Medium** | `state.ts:196-198`; `ReqogniLoomPanel.tsx:56-59`; `ConnectedView.tsx:6-24` | ErrorBanner fehlt in `connected` |
| AUD-150 | WP-2 | Info | NEU | BESTAETIGT | Info (unverändert) | `.env.example:511,515`; `override.yml:196`; `loader.ts:58` | Layer hart-off |
| AUD-151 | WP-2 | Info | NEU | BESTAETIGT | Info (unverändert) | Live `/bluepencil/api/notes` 200 ohne Credential | globaler Store |
| AUD-152 | WP-2 | Info | WIDERLEGT | **KEIN REQOGNILOOM-BEZUG** | Info (unverändert) | `AUDIT_FINDINGS.md:462`; `AUDIT_NATIVE_PLUGINS.md:108` | Audit-Prozessgegenstand |
| AUD-153 | WP-2 | Info | NEU | TEILWEISE | Info (unverändert) | `dist/plugins/hermes/` nur Builder; `test_full_regeneration.py:150` | „nirgends aufgelöst" falsch |

### WP-3 / WP-3b — UI (`REVIEW_WP3.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-001 | WP-3 | High (P1) | NEU | TEILWEISE | High (unverändert) | `useDashboardData.ts:47-53`; `AUDIT_UI_BROWSER.md:413` | N+1 ja; 453 nicht rekonstruierbar (401+5=406) |
| AUD-002 | WP-3 | High (P1) | NEU | TEILWEISE | High (unverändert) | `i18n-parity.test.ts:186`; eigener Scan | 112 → 116; 41 → 34 Dateien. Attribut UNTERSCHAETZT |
| AUD-003 | WP-3 | High (P1) | NEU | BESTAETIGT | High (unverändert) | `NavigationShell.tsx:122-127`; `SidebarNavigation.tsx:74-138` | kein Skip-Link; 26 deklariert/25 sichtbar |
| AUD-004 | WP-3 | Medium (P2) | NEU | BESTAETIGT | Medium (unverändert) | `AiPromptsSection.tsx:69-73,304-308` | Roh-Key-Fallback |
| AUD-005 | WP-3 | Medium (P2) | NEU | BESTAETIGT | Medium (unverändert) | `ThemeManagementSection.tsx:275-295` | 2 combobox ohne accessible name |
| AUD-006 | WP-3 | Medium (P2) | NEU | TEILWEISE | Medium (unverändert) | `ApiKeysSection.tsx:224`; `:276-288` ConfirmDialog | Widerruf-Teil FALSCH (ConfirmDialog existiert) |
| AUD-008 | WP-3 | Medium (P2) | NEU | BESTAETIGT | Medium (unverändert) | `SidebarNavigation.tsx:570-576,502` | kein `scrollIntoView` |
| AUD-009 | WP-3 | Low (P3) | NEU | **NICHT VERIFIKABAR** | Low (unverändert) | `RequirementList.tsx:124` | Render-Clipping; Browser-Messung fehlt |
| AUD-014 | WP-3 | Low (P3) | NEU | TEILWEISE | Low (unverändert) | `WorkspaceContext.tsx:232-234` | Mechanik ja; ~10 s live |
| AUD-015 | WP-3 | Low (P3) | NEU | TEILWEISE | Low (unverändert) | siehe 014 | Skalierung ja; Dauer nicht statisch |
| AUD-016 | WP-3 | Medium (P2) | NEU | TEILWEISE | Medium (unverändert) | `i18n-parity.test.ts:202-222` | Code→Locale existiert; Ceiling 116. Mechanik-Beschreibung FALSCH |
| AUD-017 | WP-3 | Medium (P2) | NEU | BESTAETIGT | Medium (unverändert) | 54 Specs; `/attributes` 0 | alle Teilzahlen |
| AUD-018 | WP-3 | Low (P3) | BESTAETIGT | BESTAETIGT | Low (unverändert) | `GraphCanvas.tsx:183`; `WorkflowCanvas.tsx:246` | `hideAttribution` |
| AUD-020 | WP-3 | Low (P3) | NEU | BESTAETIGT | Low (unverändert) | `IdentifiersSection.tsx:25,94-96` | `localStorage` |
| AUD-021 | WP-3 | Low (P3) | WIDERLEGT | TEILWEISE / UEBERZOGEN | Low (unverändert) | eigener Scan: 37 Hex in 5 Dateien | „0 Hex" FALSCH; 0 inline bestätigt |
| AUD-022 | WP-3 | Low (P3) | WIDERLEGT | BESTAETIGT (statisch) | Low (unverändert) | `Dialog.tsx`; AuthGate; ConfirmDialog | statisch konform |
| AUD-300 | WP-3b | High (P1) | NEU | TEILWEISE | High (unverändert) | `MISSING_KEY_BASELINE` 116; 34 Dateien | 41 Dateien nicht reproduziert |
| AUD-301 | WP-3b | High (P1) | NEU | BESTAETIGT | High (unverändert) | `i18n-parity.test.ts:186,214-219` | Ceiling-Ratchet |
| AUD-302 | WP-3b | Medium (P2) | NEU | BESTAETIGT | Medium (unverändert) | eigener Scan 26/53; `NeedsEditors.tsx:264` | ±1; Zitatzeile 263 → 264 |
| AUD-303 | WP-3b | Medium (P2) | NEU | BESTAETIGT | Medium (unverändert) | eigener Scan 535/2120 | 536/25,3 % im Rundungsbereich |
| AUD-305 | WP-3b | Medium (P2) | NEU | BESTAETIGT | Medium (unverändert) | `requirements.ts:156` | `while pageCount < 100` |
| AUD-310 | WP-3b | Medium (P2) | NEU | TEILWEISE / UEBERZOGEN | Medium (unverändert) | `user-profile.spec.ts:23,24,31,41`; frontend 0 Treffer | ≥6 → 3; Phantom-Namen |
| AUD-311 | WP-3b | Medium (P2) | NEU | TEILWEISE | Medium (unverändert) | eigener Scan 615/759 = 81 % | Quote 93,5 %/52 nicht reproduziert |
| AUD-312 | WP-3b | Low (P3) | NEU | BESTAETIGT | Low (unverändert) | `GlossaryView.tsx:598,607`; `ReqTraceLinkPanel.tsx:649,713`; `CustomFieldsEditor.tsx:154,166`; `TransitionDialog.tsx:143,151` | 4 Dubletten |
| AUD-319 | WP-3b | Low (P3) | NEU | BESTAETIGT | Low (unverändert) | `design-system-ratchet.baseline.json:6-7` | 324 |
| AUD-320 | WP-3b | Low (P3) | NEU | BESTAETIGT | Low (unverändert) | `package.json:34-35`; `AGENTS.md` | React 19 vs 18 |
| AUD-321 | WP-3b | Low (P3) | NEU | BESTAETIGT | Low (unverändert) | eigener Scan 44 in 26 Dateien | exakt |

### WP-4 — Datenmodell (`REVIEW_WP4.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-154 | WP-4 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `types.py:79,75-78`; `services.py:65,472`; `reqif_import_service.py:886` | alle Zitate |
| AUD-156 | WP-4 | Low | NEU | **NICHT VERIFIKABAR** | Low (unverändert) | `link_types/migrations/0008:83` in `unseed()`; Kopf `:5-8` | 401/402 nicht ableitbar |
| AUD-157 | WP-4 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `trace_link_manager.py:372-377`; `pg_constraint` kein CHECK | Self-Link nirgends abgelehnt |
| AUD-158 | WP-4 | Info | PASS → Kontrolle | BESTAETIGT | Info (unverändert) | Live 7 distinkte Typen | 4 ohne Link |
| AUD-159 | WP-4 | Info | PASS → Kontrolle | BESTAETIGT | Info (unverändert) | Live `lt_workspace_definition` 11 | konsistent |
| AUD-160 | WP-4 | High | NEU | BESTAETIGT | High (unverändert) | `registry.py:13` vs `definition_store.py:714-733` u. a. ≥ 6 Module | Zahl „7/5+" unscharf |
| AUD-161 | WP-4 | High | NEU | TEILWEISE | **High → Medium** | `stage_matrix.py:41-45,887,907,921,926` | bewusster Aufschub, kein Defekt |
| AUD-162 | WP-4 | High | NEU | BESTAETIGT | High (unverändert) | `presets/gate.py:536-549` `except: pass` | fail-open |
| AUD-164 | WP-4 | Low | NEU | BESTAETIGT | Low (unverändert) | `stage_matrix.py:41-45` (#940) | Issue-Status offline nicht prüfbar |
| AUD-165 | WP-4 | Info | PASS → Kontrolle | TEILWEISE | Info (unverändert) | Live `we_engine_definition`: standard 5/5, extended 8/9; minimal 0 | Minimal-Zweig live ungetestet |
| AUD-166 | WP-4 | Info | WIDERLEGT | BESTAETIGT (WIDERLEGT bleibt) | Info (unverändert) | `workflow/services.py:306,308,318,334-350,362` | Validierung nach Lock |
| AUD-167 | WP-4 | High | NEU | BESTAETIGT | High (unverändert) | `import_service.py:714-722,610` | `current_state` ohne Transition |
| AUD-168 | WP-4 | High | NEU | BESTAETIGT | High (unverändert) | `reqif_import_service.py:789-793` | kein `version`-Bump |
| AUD-169 | WP-4 | High | NEU | BESTAETIGT | High (unverändert) | `interview_views.py:245-257`; `interview_service.py:395,269-293,336-344,354,367-369` | GET mutiert |
| AUD-170 | WP-4 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `lifecycle_manager.py:416-477,452-454` | kein Gate |
| AUD-171 | WP-4 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `pg_constraint we_item_state` | kein CHECK/Workspace-FK |
| AUD-174 | WP-4 | Info | PASS → Kontrolle | BESTAETIGT | Info (unverändert) | Live `cross_tenant=0`, `cross_ws=0` | sauber |
| AUD-175 | WP-4 | Low | NEU | BESTAETIGT | Low (unverändert) | `presets/registry.py:129` | hartkodierte `known_scopes` |
| AUD-176 | WP-4 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `bootstrap_attribute_definitions.py:309,1248-1251` | dreifach gesperrt |
| AUD-180 | WP-4 | High | NEU | TEILWEISE | **High → Medium** | Live 42 Tabellen mit `workspace_id`, 16 FK; `pl_artifact` FK `models.py:1212` | Beispiele falsch; Nenner 42 |
| AUD-181 | WP-4 | High | NEU | BESTAETIGT | High (unverändert) | `migrations/0093:76-78`; `mcp_server/tools/tests.py:206` | 99 Tags, 30 in Links |
| AUD-182 | WP-4 | Low | NEU | BESTAETIGT | Low (unverändert) | `pg_constraint pl_tracelink` | kein CHECK `link_type` |
| AUD-184 | WP-4 | Medium | NEU | TEILWEISE | Medium (unverändert) | `application/models.py:44,147,170,204`; `bl_delta_index_entry` RLS mig 0010 | 4 von 5 ohne RLS, nicht 5 |
| AUD-185 | WP-4 | Info | PASS → Kontrolle | BESTAETIGT | Info (unverändert) | Live 29/31 RLS; `rg .raw(` = 0 | hält |
| AUD-186 | WP-4 | Medium | NEU | TEILWEISE | Medium (unverändert) | `rg .unscoped` = 263; `pl_artifact`/`pl_requirement` FK | „0 Constraints an 5" falsch |
| AUD-187 | WP-4 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `schema.py:22-34`; `search_service.py:182-246`; Live 13 | 11/10/13 |
| AUD-188 | WP-4 | Info | NEU | BESTAETIGT | Info (unverändert) | Live 99/3442 = 2,9 % | Snapshot-Drift |
| AUD-189 | WP-4 | Low | NEU | BESTAETIGT | Low (unverändert) | `artifactRoutes.ts:17-44,50-52` | kein `TestCase:*`-Key |
| AUD-190 | WP-4 | Info | BLOCKED | **NICHT VERIFIKABAR** | Info (unverändert) | `baseline/diff_engine.py` nicht ausgeführt | BLOCKED korrekt |
| AUD-325 | WP-4 | High | NEU | TEILWEISE | High (unverändert) | `hierarchy.py:172-186`; `baseline/services.py:430`; `delta_index_builder.py:288`; `traceEndpoints.ts:72-75` | 4 statt 3 |
| AUD-326 | WP-4 | High | NEU | BESTAETIGT | High (unverändert) | `reqif_import_service.py:886-897`; `trace_link_service.py:365,388` | Katalog umgangen |
| AUD-327 | WP-4 | High | NEU | UEBERZOGEN | **High → Medium** | `icd/traceability_connector.py:82-87`; `builtin.py:123-126` | legaler Pair |
| AUD-328 | WP-4 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `services.py:227`; `exceptions.py:18-23`; `trace_link_manager.py:356` | 8/10/11 |

### WP-5 — Traceability (`REVIEW_WP5.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-191 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `protocol_handler.py:345`; `views.py:425` | stdio |
| AUD-192 | WP-5 | High | NEU | TEILWEISE | High (unverändert) | 358/835 = 42,9 %; 366 unique REQ in Tests | Sub-Zahl „3,6 %" Etiketten-Verwechslung |
| AUD-193 | WP-5 | High | NEU | TEILWEISE | High (unverändert) | `ci.yml:44-55`; 443 reproduziert | 511 → 443 |
| AUD-194 | WP-5 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `.woodpecker.yml:61`; `rg pytest` = 0 | kein pytest |
| AUD-195 | WP-5 | High | NEU | TEILWEISE | High (unverändert) | `RELEASE_beta.17:12-13,171` | Selbstwiderspruch; 511 überholt |
| AUD-196 | WP-5 | High | NEU | TEILWEISE | High (unverändert) | `RELEASE_beta.17:17`; `useNotificationFeed.test.ts:57` | 65 nicht ausgeführt |
| AUD-197 | WP-5 | Medium | NEU | TEILWEISE | Medium (unverändert) | 11 Dateien 0 REQ-IDs; TESTPLAN Checkboxen 3/3/10 | „keine Checkboxen" falsch |
| AUD-198 | WP-5 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `test_e2e_sse_transport.py:349,353` | `skipif CI` |
| AUD-199 | WP-5 | Medium | NEU | TEILWEISE | Medium (unverändert) | `useNotificationFeed.test.ts:57`; 4 Dateien | 65 nicht ausgeführt |
| AUD-200 | WP-5 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `test_llm_settings.py:248,255` | fixiert Modell |
| AUD-201 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `SN:763,793`; `matrix:59,60` | 031 fehlt |
| AUD-202 | WP-5 | Medium | NEU | BESTAETIGT | Medium (unverändert) | 121 Dateien, 17 Frontmatter → 104 | exakt |
| AUD-203 | WP-5 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `matrix:724,728` | 20 doppelte IDs |
| AUD-204 | WP-5 | Medium | NEU | **FALSCH** | — | `AUDIT_FINDINGS.md:366` vs `AUDIT_TRACEABILITY.md:148-161`; `settings.py:822` | Registerzeile stale |
| AUD-205 | WP-5 | Low | BLOCKED | BESTAETIGT | Low (unverändert) | `health_rest.py:72,434,459-461` | BLOCKED korrekt |
| AUD-330 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | 324 = 24 + 300 | exakt |
| AUD-331 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `rg REQ-L3` = 0; `matrix:701` | 0/354 |
| AUD-332 | WP-5 | Medium | NEU | BESTAETIGT | Medium (unverändert) | `matrix:721`; `import_service.py` u. a. | 15 IDs |
| AUD-333 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `rg open_adrs` nur Audit-Docs | 0 in `docs/se` |
| AUD-334 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | L1 15 `arch_impact:true`; nur REQ-L1-100 → ADR-DS-02 | Stichprobe |
| AUD-335 | WP-5 | Medium | NEU | BESTAETIGT | Medium (unverändert) | ADR-001/-002/-003/-DS-02 ohne `---` | 4/10 |
| AUD-339 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | L1 clarifications true; L2 files false | exakt |
| AUD-340 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `matrix:103,310-312,331` | Stichprobe |
| AUD-342 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `L2_McpServerSystem:97-107`; `rg semantic_search` 1 Testname | stärkster Fund |
| AUD-343 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `matrix:231,311,390,433,483,512-513` | Code + Tests vorhanden |
| AUD-344 | WP-5 | High | NEU | TEILWEISE | High (unverändert) | `matrix:131,304-309,120,241,134,257` | 036 nur 1/2 |
| AUD-345 | WP-5 | Critical | NEU | TEILWEISE | **Critical → Medium** (eigenständig) | `matrix:331`; `Dockerfile:154`; `restore.sh` außerhalb | Duplikat 123 |
| AUD-346 | WP-5 | Critical | NEU | TEILWEISE | **Duplikat von 052** (kein eigener Schweregrad) | `providers.py:1080` identisch | Duplikat 052 |
| AUD-347 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `llm-settings.ts:22` | azure fehlt |
| AUD-348 | WP-5 | High | NEU | TEILWEISE | High (unverändert) | `matrix:114`; `i18n-parity.test.ts:186` 116 | 112 vs. 116 |
| AUD-349 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `import_service.py:226-234,317,149` | Link auf 070 stale |
| AUD-350 | WP-5 | High | NEU | BESTAETIGT | High (unverändert) | `matrix:521`; Cross-Ref 120 | zulässiger Cross-Ref |

### WP-6a — Security (`REVIEW_WP6A.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-220 | WP-6a | Critical | NEU | TEILWEISE | Critical (unverändert) | `git cat-file 3dcc80d8`; `git grep HEAD docs/audit` = 0; `merge-base` exit 1 | Leak-Fakten bestätigt; Widerruf unbelegt |
| AUD-221 | WP-6a | Critical | NEU | BESTAETIGT | Critical (unverändert) | `views.py:272` vs `:307`; `settings.py:879-884`; `throttling.py:164` | 4/4 statisch. Live bestätigt |
| AUD-222 | WP-6a | High | NEU | BESTAETIGT | High (unverändert) | `workspace_scope.py:114,79-86,89-111`; `rest.py:259-277`; `requirement_service.py:754-757`; `auth_enforcer.py:112-120` | Mechanik belegt; 311/269 aufgebläht → 163/198. Live blockiert (Scoped-User) |
| AUD-223 | WP-6a | High | NEU | TEILWEISE | High (unverändert) | `urls.py:33`; `settings.py:181`; `rg axes` = 0 | Exposition + kein Lockout; 500 live offen; Settingname falsch |
| AUD-224 | WP-6a | High | NEU | BESTAETIGT | High (unverändert) | `.pre-commit-config.yaml` fehlt; `rg Scanner` = 0; `.woodpecker.yml:76-80` | kein Secret-Scan |
| AUD-225 | WP-6a | High | NEU | TEILWEISE | High (unverändert) | 34 `uses` / 15 Aktionen / 1 gepinnt (`ci.yml:343`) | 27/28 nicht reproduziert |
| AUD-226 | WP-6a | Medium | NEU | BESTAETIGT | Medium (unverändert) | `settings.py:143-160`; `INSTALLED_APPS:180-235`; `MIDDLEWARE:240-273` | CORS tote Konfiguration |
| AUD-227 | WP-6a | Medium | NEU | TEILWEISE | Medium (unverändert) | `migrations/0011:43-64`; `test_rls_coverage.py:75-276` | benannte Ausnahmen; 29/100 live offen; „unkontrolliert" überzogen |
| AUD-228 | WP-6a | Medium | NEU | UEBERZOGEN | **Medium → Low** | `models.py:501-514,68-101`; `user_management_views.py:110` | dokumentierte Design-Entscheidung |
| AUD-229 | WP-6a | Medium | NEU | BESTAETIGT | Medium (unverändert) | `throttling.py:391,404-408`; `rg NUM_PROXIES` nur Kommentare | latent ohne Proxy |
| AUD-231 | WP-6a | Medium | NEU | BESTAETIGT | Medium (unverändert) | `settings.py:764-766`; `token_tracking.py:233-243` | Budget fail-open |
| AUD-232 | WP-6a | Low | NEU | BESTAETIGT | Low (unverändert) | `urls.py:31,35`; `version.py:124-125,130` | Schema + Version öffentlich; SHA gekürzt |
| AUD-234 | WP-6a | Low | NEU | TEILWEISE | Low (unverändert) | `serializers.py:328-356`; `views.py:3447,3628` | Silent clamp, nicht 404; Widerspruch zur Empfehlung |
| AUD-236 | WP-6a | Low | NEU | TEILWEISE | Low (unverändert) | `.env` (untracked); `.env.example:33,52` | lokal; „still übernommen" spekulativ |
| AUD-238 | WP-6a | Medium | NEU | BESTAETIGT | Medium (unverändert) | `prompt_resolver.py:92-94`; `ai_derivation_service.py:671,672,787-788,901-902` | kein Escaping |
| AUD-239 | WP-6a | High | NEU | **KEIN REQOGNILOOM-BEZUG** | — | `AUDIT_EVIDENCE wp1d-…:2237-2246`; cleanup §2 | Audit-Prozess |
| AUD-240 | WP-6a | Medium | NEU | TEILWEISE | Medium (unverändert) | `models.py:160,162`; `tool_registry.py:1592-1601`; `authentication.py:569-571` | Fence nur MCP; 9 Keys live offen |
| AUD-241 | WP-6a | Low | NEU | BESTAETIGT | Low (unverändert) | `verify-backup-command.sh:90,103`; `compose.yml:73,1053` | Duplikat 148 |

### WP-6b — Reliability/Concurrency/Observability (`REVIEW_WP6B.md`)

| Original-ID | WP | Orig-Schweregrad | Orig-Klassifikation | REVIEW_VERDICT | Korrigierter Schweregrad | Gegenbeweis (file:line, kurz) | Anmerkung |
|---|---|---|---|---|---|---|---|
| AUD-270 | WP-6b | High | BESTAETIGT | BESTAETIGT | High (unverändert) | `celery.py:45`; `apps.py:36`; `archive.py:448`; Live 6 Tasks | Task nicht registriert |
| AUD-271 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `version_reconstructor.py:191,210,227,244,295` | 5× `except: pass` |
| AUD-272 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `settings_service.py:661-663,718-722` | Preset-Tier None |
| AUD-273 | WP-6b | Medium | NEU | UEBERZOGEN | **Medium → Low** | `attribute_migration_service.py:969-978` | `get_field` In-Memory, kein I/O |
| AUD-274 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `tool_registry.py:1382,1412,1520`; `settings.py:929` | DEBUG unterdrückt |
| AUD-275 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `health.py:4` vs `urls.py:28`; 0 ready/live Routen | Docstring-Lüge |
| AUD-276 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `settings.py:899-953`; `rg LOG_LEVEL` = 0 | hartkodiert INFO |
| AUD-277 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `metrics_views.py:29-46`; `rg prometheus` = 0 | kein Telemetrie-Exporter |
| AUD-278 | WP-6b | Medium | BESTAETIGT | BESTAETIGT | Medium (unverändert) | `serializers.py:241-257`; `middleware.py:42-91`; `rg trace_id` = 0 | kein `request_id` im Body |
| AUD-279 | WP-6b | Low | NEU | BESTAETIGT | Low (unverändert) | `signature_gate.py:140-157` | fail-closed ohne Log |
| AUD-280 | WP-6b | Low | NEU | TEILWEISE | Low (unverändert) | `icd_views.py:274`; `base.py:147,167`; `workflow_transitions.py:281` Fehlzitat | 1/3 Fundstellen falsch |
| AUD-281 | WP-6b | High | NEU | BESTAETIGT | High (unverändert) | `models.py:3376-3381`; `goal_service.py:134-149`; Live kein UNIQUE | `max+1` ohne Lock |
| AUD-282 | WP-6b | High | NEU | UEBERZOGEN | **High → Medium** | `goal_service.py:659-668` (Fehlzitat); `workflow_transitions.py:482-491`; `views.py:6063,7471` | 1/6 Zitate falsch; Impact überzogen |
| AUD-283 | WP-6b | Medium | NEU | **FALSCH** | — | `audit/writer.py:31,256`; `audit/events.py:100-123`; `services.py:178-190`; `context_graph/apps.py:27-31` | Bus-Namensverwechslung; kein Duplikat |
| AUD-284 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `tasks.py:31-38`; Live `total_run_count=223773` | Exception verschluckt |
| AUD-285 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `audit_entry` Live 8167, 7979 NULL; `writer.py:197` | 97,70 % |
| AUD-286 | WP-6b | Medium | NEU | BESTAETIGT | Medium (unverändert) | `health.py:124-261`; `health_rest.py:96-200`; `compose.yml:642` | 5/10 Abhängigkeiten |
| AUD-287 | WP-6b | Medium | BESTAETIGT | BESTAETIGT | Medium (unverändert) | `audit/query.py:146-148`; Live 4050 rows | Deep-Offset |
| AUD-288 | WP-6b | Low | NEU | BESTAETIGT | Low (unverändert) | `pg_stat_user_tables` Live; `n_live_tup=0` | Zähler wertlos |

---

## 3. Widerspruchs- und Duplikat-Liste

### 3.1 Widersprüche innerhalb des Registers (Register-Sync-Fehler)

1. **AUD-031 vs. AUD-129 (HTTP-200-Behauptung).** Register §3 `:228` behauptet für
   AUD-129 „`degraded` liefert HTTP **200**". Quellcode: `health.py:134-135,160-161`
   setzt bei `status="degraded"` **immer** HTTP 503. AUD-031 (§3 `:191`) und
   §5-K-3 (`:525`) beschreiben den Fehlfall korrekt als **Cache-/Redis-Ausfall ohne
   Probe**. Es gibt **keinen** Widerspruch innerhalb von AUD-031; der Widerspruch ist
   AUD-129/`AUDIT_INFRASTRUCTURE.md` gegen den Code. → **AUD-129 TEILWEISE**, AUD-031
   BESTAETIGT.
2. **AUD-121 (Beat).** Register/`AUD-121` behauptet „Beat dispatcht nie". Live:
   `django_celery_beat_periodictask`-Zähler schreiten voran, Worker führt
   `dispatch-outbox-events` alle 5 s aus. Die Register-Evidenz „0× `Sending due task`"
   ist ein **Log-Artefakt**. → **AUD-121 FALSCH (Headline)**; nur Teile (a) und (b)
   bleiben.
3. **Registerzeile AUD-204 (veraltet).** `AUDIT_FINDINGS.md:366` trägt weiter „nicht
   reproduzierbar", obwohl `AUDIT_TRACEABILITY.md:148-161` die Aussage zurücknimmt
   und AUD-121/270 bestätigt. → **AUD-204 FALSCH (Registerzeile stale)**.
4. **AUD-071 §5-Überschrift** trägt noch die alte Ursache (`pl_artifact_pkey`),
   während §3 und der K-3-Vermerk die korrigierte Savepoint-Ursache führen.
   (Register-Hygiene, kein Verdiktwechsel; AUD-071 bleibt BESTAETIGT.)
5. **AUD-002 vs. AUD-300 (i18n doppelt).** Register §3 nennt für AUD-002 „112"
   und für AUD-300 „116" — beide „P1/High". Der Ratchet
   (`i18n-parity.test.ts:186`) führt **116**. → 112 ist eine Unterzählung
   (AUD-002 TEILWEISE/UNTERSCHAETZT), AUD-300 TEILWEISE (41 Dateien statt 34).
6. **AUD-193 Registerzeile** nennt noch **511**, obwohl die kanonische Zahl **443**
   ist (Review repro). (Stale-Zahl, kein Verdiktwechsel.)
7. **AUD-345 = AUD-123** und **AUD-346 = AUD-052.** Beide WP-5-Criticals sind
   Duplikate bereits erfasster Criticals; die Register-Critical-Zählung ist damit um
   zwei überhöht. → 345 TEILWEISE (Critical → Medium eigenständig), 346 TEILWEISE
   (Duplikat 052).
8. **AUD-241 = AUD-148** (dieselben Compose-Defaults); **AUD-231 ↔ 055/063**,
   **AUD-221 ↔ 030**, **AUD-227 ↔ 184/185**, **AUD-121(b) ↔ 125/270.**
   Register-Doppelführungen, die die Gesamtzählung verzerren.
9. **AUD-349 → AUD-070 (stale Link).** WP-5 verlinkt den am 2026-09-30
   widerlegten Round-Trip-Befund; der CSV-`success`-Kern bleibt, der Link ist tot.
10. **AUD-150/151 Register NEU vs. Report BESTAETIGT** (WP-2): Register §3
    (`:460-461`) führt `NEU`, `AUDIT_NATIVE_PLUGINS.md:106-107,130` führt
    `BESTAETIGT`. → Die Review stützt BESTAETIGT.

### 3.2 WIDERLEGT-Kontrollen (geprüft und bestätigt)

`AUD-070` (CSV-Round-Trip, `import_service.py:341-344`), `AUD-143` (korrekt als
DUPLIKAT #1019 geführt; 4× `vector(384)`), `AUD-021` (nur „0 inline Styles"
bestätigt, „0 Hex" widerlegt), `AUD-022` (Fokuspfade statisch konform),
`AUD-050` (kein Cross-Tenant-Leak), `AUD-152` (Audit-Prozessgegenstand),
`AUD-166` (Transition validiert nach dem Lock). Diese Kontrollen wurden nicht in
die Finding-Zählung eingerechnet bzw. als Kontrolle markiert.

---

## 4. Quellen- und Abgrenzungshinweis

- **Keine neue Fachanalyse.** Dieses Dokument aggregiert ausschließlich die
  Verdikte der 12 Review-Evidenzdateien; es wurden keine Produktdateien geändert.
- **Live-Nachtest** (`REVIEW_LIVE_CRITICALS.md`, Stack up) deckt die Criticals
  030, 031, 052, 071, 073, 074, 120, 121, 221, 222 ab. Er ist **Querschnittsevidenz**
  zu den WP-Zeilen, kein eigenständiger WP; die Verdikte sind dort eingearbeitet.
- **Original-Severities** wurden wörtlich aus `AUDIT_FINDINGS.md` §3 übernommen
  (inkl. P-Skalen-Originalwerte der WP-3/3b-Findings).
- **Keine Secrets.** Enthalten ausschließlich maskierte/belegte Befundreferenzen.
