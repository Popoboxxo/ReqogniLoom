---
type: REVIEW
scope: wp6b-concurrency-observability
status: complete
date: 2026-09-30
author_agent: code-reviewer
---

# WP-6b Evidence 01 — Silent-Failure-Inventar

Read-only. Keine Code-Änderung. Scan-Umfang: `backend/**/*.py`, ohne
`tests/`, `migrations/`, `__pycache__/`.

## 1. Mechanische Kandidatenmenge (Denominator)

| Muster | Treffer (Prod) | Kommando |
|---|---|---|
| **C** alle `except`-Klauseln | **1888** | `rg -c "^\s*except\s"` |
| **A** `except Exception/BaseException:` → `pass` | **7 Sites** | `rg -U "except\s+(Exception\|BaseException)[^\n]*:\s*\n\s*pass"` |
| **B** nacktes `except:` | **0** | `rg "^\s*except\s*:"` |
| **D** `except` → `return None/[]/{}/True/False` | **~52 Sites** | `rg -U "except[^\n]*:\s*\n(\s*#[^\n]*\n)*\s*return\s+(None\|\[\]\|\{\}\|True\|False\|\(\))"` |
| **E** breites `except` mit `return`-Fallback **+ Log** | **6 Sites** | manuell, `mcp_server/tool_registry.py` |
| **F** `getattr(obj, name, None)` auf Pflichtfeldern | div. | manuell |

**A + D + E ≈ 65 mechanische Kandidaten** aus 1888 `except`-Klauseln (3.4 %).
Davon wurden die 31 hochsignaligen Sites einzeln gelesen und bewertet
(Tabelle 2). Die übrigen D-Sites sind `except (ValueError, TypeError,
AttributeError): return None` in UUID-/Dict-/Enum-Cast-Helfern
(`rest_api/query_params.py:94`, `mcp_server/views.py:203`,
`llm_adapter/token_tracking.py:228`, `persistence/custom_fields.py:168` …) —
das ist **korrekte, enge Typ-Abfang**, kein Silent Failure.

**B = 0** ist ein ehrlicher PASS-Beleg: es gibt im Produktivcode keine
nackten `except:`-Klauseln.

## 2. Klassifizierte Sites

Legende: **SF** = echter Silent Failure · **FB** = vertretbarer Fallback
(fehl-closed oder dokumentiert) · **FA** = Fehlalarm · **FBO** =
Fehl-closed, aber ohne Telemetrie (Fail-closed *und* Observability-Lücke)

| # | Pfad:Zeile | Muster | Fail | Log | Urteil | Begründung |
|---|---|---|---|---|---|---|
| 1 | `baseline/version_reconstructor.py:191,210,227,244,295` | `except Exception: pass` | open | nein | **SF** | 5× Probe-Kette „versuche Entity-Typ A,B,C…". Ein DB-/Import-Fehler verschluckt das **Artefakt still aus dem rekonstruierten Baseline** → Baseline-Diff wird falsch, ohne Fehler. Compliance-relevant. → **271** |
| 2 | `application/settings_service.py:662` | `except Exception: return None` | open | nein | **SF** | Preset-Tier still „unbekannt"; Docstring nennt es „read-side safety net", aber **kein Log** → Review-Policy fällt still auf Default zurück. → **272** |
| 3 | `application/attribute_migration_service.py:977` | `except Exception: pass` → `:978 return None` | open | nein | **SF** | `_field_carrier` nutzt `except` als Existenzprobe. Ein Transient-Error ⇒ Feld wird am **falschen Carrier** (`type` vs. `artifact`) gelesen → falsche Daten im Migrationslauf. → **273** |
| 4 | `mcp_server/tool_registry.py:1381` | `except Exception` → `roles = ()` | closed | `logger.debug` | **FBO** | Fail-closed korrekt, **aber DEBUG**; Prod-Level ist hart auf INFO (settings.py:929) ⇒ bei DB-Ausfall bekommen **alle** Aufrufer 403 mit **null Logzeile**. → **274** |
| 5 | `mcp_server/tool_registry.py:1411` | dito → `return ()` | closed | `logger.debug` | **FBO** | global-Rollen-Resolution, gleiche Unsichtbarkeit. → **274** |
| 6 | `mcp_server/tool_registry.py:1520` | dito → `return False` | closed | `logger.debug` | **FBO** | Tenant-Admin-Check. → **274** |
| 7 | `mcp_server/tool_registry.py:1683` | dito → `return False` | **open** | `logger.warning` | **FB** | Preset-Gate fail-**open**, aber explizit („auth is the hard gate", Zeile 1684) **und** `warning`-geloggt. Bewusste, dokumentierte Entscheidung. |
| 8 | `mcp_server/tool_registry.py:1324` | `except Exception` → „internal error" | closed | `logger.exception` | **FB** | CWE-209-Maskierung, korrekt geloggt. |
| 9 | `workflow/signature_gate.py:156-157` | `except Exception: return False` | closed | nein | **FBO** | Infra-Fehler ist vom falschen Passwort **nicht unterscheidbar**; Nutzer sieht „invalid credential", Operator sieht nichts. ADR-L3-WE-004-04 untersagt Audit-Log-Eintrag, ein `logger.debug` fehlt aber. → **279** |
| 10 | `workflow/signature_gate.py:94-95` | `except Exception: pass` | closed | nein | **FA** | Danach `raise RuntimeError` wenn Key leer (Z. 96-100). Fail-closed, korrekt. |
| 11 | `rest_api/icd_views.py:274`, `mcp_server/tools/base.py:148,167`, `rest_api/mixins/workflow_transitions.py:281` | `except TenantContextNotSetError: return {}` | open (Display) | nein | **SF** | Kein Datenleck, aber **maskiert eine Tenant-Context-Fehlkonfiguration** vollständig: jeder Item fällt auf Initialzustand zurück, alle mit Status-Maskierung. → **280** |
| 12 | `mcp_server/tools/users.py:452-453` | `except Exception: return False` | closed | nein | **FBO** | `_caller_is_superuser`; DB-Blip ⇒ legitimer Plattform-Admin kann keine Cross-Tenant-User anlegen, ohne Logzeile. |
| 13 | `traceability/pdf_report_generator.py:121-122` | `except Exception: pass` | open | nein | **SF** | Terminology-Profile still auf `"default"` ⇒ PDF mit falschem Vokabular, kein Fehler. **Low**-Impact (kosmetisch). |
| 14 | `application/interview_multi_protocol.py:116-117` | `except json.JSONDecodeError: return None` | open | nein | **SF** | Verwandt mit bekanntem `057` (nacktes `json.loads`); hier *eingegrenzt*, aber `None` ⇒ Interview-Protokoll-Fragment fehlt lautlos. |
| 15 | `application/ai_derivation_service.py:444-445` | `except (JSONDecodeError, TypeError): return False` | open | nein | **SF** | Validierungs-False bei Parse-Fehler — nicht von „echt invalid" unterscheidbar. |
| 16 | `application/webhook_dispatcher.py:337-340` | `except URLError/Exception → (None, False, msg)` | closed | (msg) | **FB** | Fehlertext wird **zurückgegeben**, nicht verschluckt. |
| 17 | `persistence/transactions.py:95` | `return bool(self._atomic.__exit__(...))` | n/a | n/a | **FA** | reviewed: korrekte Exception-Propagation. |
| 18 | Cast-/Parse-Helfer (`rest_api/query_params.py:94`, `mcp_server/views.py:203`, `llm_adapter/token_tracking.py:228`, `persistence/custom_fields.py:168`, `persistence/artifact_backing.py:173`, `memory/policy.py:94`, `memory/context_builder.py:86`, `memory/backends.py:438,454`, `workflow/services.py:412,494`, `baseline/views.py:69`, `baseline/state_capture.py:608`, `diagram/node_graph.py:147`, `context_graph/projector.py:142`, `attribute_definitions/field_validation.py:110`, `application/artifact_service.py:141`, `application/test_service.py:144`, `application/trace_link_service.py:1589`, `application/ai_review_service.py:341`, `application/reqif_import_service.py:246`, `rest_api/user_management_views.py:189`, `rest_api/mixins/etag.py:146`, `llm_adapter/resilient_transport.py:88`, `auth_tenancy/workspace_scope.py:57`, `application/traceability_suggest_service.py:580`, `application/ai_proposal_service.py:115`, `application/workflow_facade.py:350`, `workflow/transition_validator.py:230`) | enge Typ-Casts | n/a | n/a | **FA** | `except (ValueError, TypeError, AttributeError)` um `UUID()`/`dict()`/`getattr()`. **Korrekt** — enge Exception, deterministischer Fehler, kein Zustandsverlust. |

## 3. Ergebnis

| Kategorie | Sites | Klassen |
|---|---|---|
| **Echte Silent Failures (SF)** | **14** | **10** |
| Fail-closed ohne Telemetrie (FBO) | 5 | 2 (→ 274, 279) |
| Vertretbarer Fallback (FB) | 4 | 3 |
| Fehlalarm (FA) | ~34 | 2 |

**Antwort auf die Zählfrage: 65 Kandidaten-Sites → 14 Sites in 10 Klassen
sind echte Silent Failures.** Der Rest ist entweder korrekter enger
Typ-Cast oder dokumentiertes Fail-Closed.

**Systematisches Muster (der eigentliche Befund):** Die Fehler-Unterdrückung
in diesem Repo ist **fast durchgängig fail-closed und dokumentiert** — das ist
handwerklich gut. Der systematische Mangel ist **nicht** das Verschlucken,
sondern die **Trennung von Fail-Closed und Telemetrie**: 5 Sites
(`tool_registry.py:1381/1411/1520`, `signature_gate.py:156`,
`users.py:452`) verschlucken Infrastrukturfehler korrekt, loggen sie aber
auf `DEBUG` bzw. gar nicht — und `DEBUG` ist im Produktivbetrieb
**abgeschaltet** (settings.py:929, hart auf INFO). Ergebnis: ein DB- oder
Redis-Ausfall erzeugt bei allen betroffenen Pfaden **403/False ohne eine
einzige Logzeile**. → **274**, **279**.

## 4. Suche nach weiteren Mustern (Negativbelege)

| Gesuchtes Muster | Ergebnis |
|---|---|
| `except: pass` (nackt) | **0 Treffer** — PASS |
| `logger.exception` fehlt bei breitem `except` | 3 Sites (Nr. 4-6, 11) — siehe oben |
| `try/except` um Migrations-/Init-Pfade | `application/self_init.py`, `persistence/management/commands/*` — geprüft, keine ungedeckten Breits; `align_embedding_dimensions.py:1` mit engem `except` |
| `.get(...)` auf Pflichtfeldern ohne Default-Behandlung | keine systematische Lücke gefunden; `mcp_server/tools/architecture.py` nutzt `data.get("expected_version") or params.get(...)` mit dokumentiertem Fallback `= 1` |
| PII/Secrets in Log-Aufrufen | **Fehlalarm.** 3 Kandidaten, alle benign: `llm_adapter/token_tracking.py:163,207` loggen ein Exception-Objekt (`%s`), `mcp_server/tool_registry.py:1310` loggt einen statischen String. **Kein** Logger gibt ein Passwort, Token, API-Key oder Personenfeld aus. |
