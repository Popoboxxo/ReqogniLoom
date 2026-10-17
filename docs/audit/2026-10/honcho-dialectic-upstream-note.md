# Upstream-Befund: Honcho-Dialektik sendet `x-opencode-session` nicht — `memory.ask` bleibt degraded

**Status:** Faktendokumentation (kein Fix, kein ADR) — erstellt 2026-10-17 im Auftrag der
Runde-5-Entscheidungsspur D6 (`docs/audit/2026-10/bugfix-round-5-plan.md`); zugehörige
Richtungsentscheidung: `docs/se/ADR/ADR-023_honcho_produktpfad.md`.
**Basis:** QS-Messungen aus #1153/#1247 (QS 172.20.5.120, beta.18/beta.20, Commit
`0ee47d25`) + Repo-Verifikation am 2026-10-17 (`origin/main @ 12cce237`, Branch
`docs/round5-decision-prep-d5-d7`; kein Commit). Nicht verifizierte Angaben sind als
„laut Issue/QS" markiert.
**Operativer Eskalationspfad (bleibt gültig):** `docs/DEPLOY_RUNBOOK.md` §3.1
(„Upstream boundary: the Honcho dialectic header is not provable in-repo (#1153, #1247)")
inkl. Schritte 3a–3d und Step 1/2; `deploy/README.md` (Stale-Image-/Pin-Abschnitt).

---

## 1. Der exakte Defekt

**Der Dialektik-LLM-Call der Honcho-Engine wendet die Provider-Parameter-Overrides
(`MODEL_CONFIG__OVERRIDES__PROVIDER_PARAMS__EXTRA_HEADERS`) nicht an — der Pflicht-Header
`x-opencode-session` erreicht den Provider (Zen/OpenCode Go) daher nicht.**

Belegkette (laut #1153/#1247, QS):

- Die Konfiguration **ist** vorhanden: Container-Env `reqogniloom-honcho-1` trägt
  `DIALECTIC_LEVELS__{minimal,low,medium,high,max}__MODEL_CONFIG__OVERRIDES__PROVIDER_PARAMS__EXTRA_HEADERS__x-opencode-session`
  sowie dieselbe Kette für `DERIVER_…` (Sandbox-Override `deploy/docker-compose.sandbox.yml`
  als Fix für #1050/#1051 dokumentiert).
- **Gegenprobe:** Der **Deriver-Pfad** mit identischer Konfiguration kommt beim Provider an
  (Antwort: `429 GoUsageLimitError` — eine Provider-Antwort, d. h. der Header hat gewirkt).
  Der **Dialektik-Pfad** erhält stattdessen
  `400 MissingSessionID` → Honcho antwortet HTTP 500.
- **Schluss:** Es liegt nicht an der Konfiguration, sondern daran, dass der Dialektik-Resolver
  `…PROVIDER_PARAMS__EXTRA_HEADERS` nicht durchreicht (Traceback:
  `src/dialectic/chat.py:129` → `src/dialectic/core.py:576` →
  `src/llm/backends/openai.py::complete`; laut #1247 ist der `extra_headers`-Escape-Hatch in
  genau diesem Complete-Pfad nicht durchgereicht, während er in anderen Modulen greift).
- **Abgrenzung:** Das generelle „OpenCode Go braucht einen Session-Header"-Thema ist upstream
  adressiert (Upstream-Issue #1171, **geschlossen** 2026-09-11) und in-repo über den
  `LLM_OPENCODE_SESSION`-Shim verdrahtet (#1050/#1051). **Offen ist ausschließlich der
  Dialektik-Pfad.** Der in-repo Preflight (#1186) beweist nur die *Ableitung* der neun
  Modul-Namen, nicht den tatsächlichen Complete-Aufruf (Runbook §3.1).

## 2. Betroffene Flows

| Flow | Wirkung |
|---|---|
| MCP `memory.ask` (`MEMORY_BACKEND=honcho`) | `degraded:true`, `detail:"engine_error:ServerError"` — keine inhaltliche Antwort (#1247) |
| REST `POST /api/v1/workspaces/<id>/memory/ask/` (Spiegel von `memory.ask`) | identisch degradiert |
| UI „Frag das Gedächtnis" (`MemoryAskPanel`) | zeigt die degradierte Antwort (ehrlich, aber ohne Inhalt) |
| Deriver/Summary/Dream (Hintergrund) | **nicht** betroffen — Deriver-Pfad nachweislich funktionsfähig (Provider antwortet); Dream läuft allerdings aus einem anderen Grund nie (#1336) |
| `memory.query`/`memory.digest`/`memory.write` | nicht betroffen (eigene Pfade) |

## 3. Degradiertes Verhalten (dokumentiert, code-verifiziert)

`backend/memory/honcho_backend.py`: Ein Engine-/Transportfehler erzeugt
`MemoryAnswer(degraded=True)` mit `detail = "engine_error:<ExceptionClass>"`
(`_degraded_detail:328`, `ask:1364+`). Das ist **kein stilles Leer**: „down" und „nichts
erinnert" bleiben getrennt (F9). Auf der QS erscheint konkret
`{"answer": "", "degraded": true, "backend": "honcho", "detail": "engine_error:ServerError"}`.
Der Zustand ist damit sichtbar und diagnostizierbar — er ist die korrekte Darstellung eines
Fremd-Defekts, nicht selbst ein Bug.

## 4. Pin-Status (W15d, #1315)

| Stand | Image-Referenz (alle drei Services: `honcho`, `honcho-deriver`, `honcho-migrate`) |
|---|---|
| `origin/main @ 12cce237` (dieser Branch) | `ghcr.io/plastic-labs/honcho:latest@sha256:350b778a…` — **Digest-gepinnt, aber beweglicher `latest`-Tag** |
| PR **#1414** (`fix/w15-release-dx`, **offen** am 2026-10-17) | `ghcr.io/plastic-labs/honcho:v3.3.0@sha256:5bb8cf7a…` — stabiler **Tag + Digest**; zieht Guard-Test, `deploy/README.md` und Compose-Kommentare mit |

Der Guard `backend/memory/tests/test_honcho_deploy_contract.py` prüft heute Digest-Gleichheit
der drei Services (und nach #1414 zusätzlich „release tag, nicht `latest`"). **Wichtig:**
Ob der Dialektik-Defekt in **v3.3.0** behoben ist, ist **unverifiziert** — der Pin allein
behebt nichts; der Retest gehört zu den nächsten Schritten.

## 5. Upstream-Stand

- Gezielte Suche im Upstream-Repo `plastic-labs/honcho` am 2026-10-17: **kein offenes Issue**
  zum Dialektik-/`extra_headers`-Defekt (Suchbegriffe: `MissingSessionID`, `dialectic`,
  Session-Header; Treffer: nur das geschlossene #1171 zur generellen Header-Anforderung).
  → **Das Upstream-Issue steht noch aus.**
- Thematisch benachbart, aber nicht Ersatz: offenes Upstream-#1358 („Optional time-of-day
  window for automatic dreams") — betrifft #1336 (Dream-Auslösung), nicht den Header-Defekt.

## 6. Nächste Schritte

1. **PR #1414 landen** (Tag+Digest-Pin) — Voraussetzung für reproduzierbare Diagnose.
2. **Retest gegen `v3.3.0`** über den Runbook-§3.1-Pfad: Step 1 (SDK-Kwarg-Auflösung im
   gepinnten Image) und Step 2 (`memory.ask` live). Ergebnis = Trigger-Nachweis T1 aus ADR-023.
3. **Upstream-Issue stellen** (`plastic-labs/honcho`) mit: exakter Konfiguration, Deriver-
   Gegenprobe (429 vs. 400), Traceback der Dialektik-Kette, Repro-Kommando; Bitte, den
   Dialektik-Pfad dieselbe `provider_params.extra_headers`-Durchreichung nutzen zu lassen wie
   den Deriver-Pfad.
4. **Degradation laut halten** (kein stilles Leer) und `#1153` erst schließen, wenn der
   Wire-Nachweis existiert.
5. **SDK-Drift klären:** `backend/requirements.txt:169` `honcho-ai==2.5.1` vs.
   `backend/requirements.lock:66` `honcho-ai==2.3.0` — vor weiteren Diagnosen feststellen,
   welche Version der laufende Backend-Container importiert; Lock nachziehen oder Ausnahme
   begründen.

## 7. Querverweise

- Issues: #1153 (Dialektik 500, wieder geöffnet), #1247 (Regression `memory.ask`), #1186
  (Preflight — prüft nur Ableitung), #1315 (Pin), #1336 (Dream), #1337 (Fähigkeiten), #1155
  (RFC), #1050/#1051 (Header-Shim, geschlossen).
- Repo: `docs/DEPLOY_RUNBOOK.md` §3.1 · `deploy/README.md` (Stale-Image-Abschnitt) ·
  `backend/memory/honcho_backend.py` · `backend/memory/tests/test_honcho_deploy_contract.py` ·
  `backend/llm_adapter/tests/test_opencode_session_check_1050.py`.
- Entscheidung: `docs/se/ADR/ADR-023_honcho_produktpfad.md` (Option B: Pin + Upstream jetzt;
  Dream/#1337 erst nach T1/T2).

---

*Erstellt durch `concept-specifier` am 2026-10-17 (Runde-5-Entscheidungsspur D6). Enthält
keinen Produktcode, keine Config-Änderung und keinen Commit.*
