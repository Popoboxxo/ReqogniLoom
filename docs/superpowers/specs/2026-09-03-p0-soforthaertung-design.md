# P0-Soforthärtung — Design

**Datum:** 2026-09-03
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md` Kapitel O (Priorisierung: Rang P0/0/0a), Kapitel R (Live-Audit), T1, U2, H5.
**Gruppe:** 1 von 15 aus `docs/SYSTEMAUDIT_2026-09-02_GRUPPIERUNG.md`.
**Klassifizierung:** Bounded (sechs unabhängige, kleine Fixes an bestehendem Code, kein neues Subsystem). Spec-Dokument trotzdem geschrieben, da für alle 15 Audit-Gruppen einheitlich gewünscht.
**Warum diese Gruppe zuerst:** R2 blockiert jeden Schreibzugriff aus der UI auf einer Live-Instanz — ohne diesen Fix ist kein Live-Test einer der anderen 14 Gruppen sinnvoll möglich.

---

## Scope

Alle sechs Punkte sind vom Audit selbst als P0/0/0a eingestuft (Kapitel O). Nichts davon braucht Konzeptarbeit — jeder Punkt hat im Audit bereits einen konkreten Fix-Vorschlag mit Dateireferenz.

**Explizit außerhalb dieser Gruppe:**
- T2/T3 (Leser/Autor/Experte-Rollenkonzept, `audience`-Feld auf Attribut-Definition) — eigene, spätere Gruppe (Rollen & Sichtbarkeit).
- U1/U3 (Erlaubt-Matrix-Lücken, drei Hierarchiemechanismen, 15→8-Typen-Reduktion) — eigene, spätere Gruppe (Traceability-Reduktion).
- R3-Restbefunde ohne P0/0a-Kennzeichnung (z. B. Validierungsfehler ohne Werteliste, `derive`/`decompose-next-level`-Doppelung) — nicht in dieser Gruppe.
- Alles aus R5/R7-Fix-Vorschlägen jenseits der P0-Zeile in Kapitel O (Async-ifizierung aller KI-Calls, `llm-usage`-Endpoint, Interview-Titel-Extraktion) — spätere Gruppen.

---

## Änderungen

### 1. R2 — CSRF-Cookie blockiert jeden Schreibzugriff über HTTP

**Problem:** `backend/reqogniloom/settings.py:79` setzt `CSRF_COOKIE_SECURE = not DEBUG`. Auf einer Instanz mit `DEBUG=False` über Plain-HTTP verwirft der Browser das Cookie, jeder POST/PUT/PATCH/DELETE aus der UI endet mit 403.

**Fix:**
- `CSRF_COOKIE_SECURE = AUTH_COOKIE_SECURE` (bestehendes Pattern wiederverwenden, keine neue Env-Variable — `AUTH_COOKIE_SECURE` löst exakt dasselbe Problem bereits für den Access-Cookie, siehe `.env.example`).
- Frontend-Startup-Check: `location.protocol === "http:"` und nach Login kein lesbares `csrftoken`-Cookie → Banner "Diese Instanz ist ohne TLS erreichbar, Schreibzugriffe sind blockiert. Admin: AUTH_COOKIE_SECURE=false setzen oder TLS aktivieren."
- `/health/` bekommt Feld `csrf_cookie_reachable`.
- `deploy/README.md`: Hinweis als erste Stolperfalle dokumentieren.

**Dateien:** `backend/reqogniloom/settings.py`, `frontend/src/App.tsx` (oder Init-Stelle), `backend/.../health` View, `deploy/README.md`.
**Testing:** Settings-Test, der `AUTH_COOKIE_SECURE=False` setzt und `CSRF_COOKIE_SECURE is False` erwartet (und umgekehrt).

### 2. T1 — Viewer-Rolle sieht Schreib-UI, nur Server lehnt ab

**Problem:** Navigation zeigt Viewer-Rolle alle 26 Einträge inkl. Admin-Seiten. Requirement-Formulare zeigen Speichern/Bearbeiten/Löschen. Erst der Server lehnt ab (403).

**Fix:**
- `NAV_ITEMS` bekommt `requires: "admin" | "editor" | null`. Einträge ohne passende Rolle werden nicht gerendert (nicht nur deaktiviert).
- `ArtifactForm`/Detail-Views leiten `mode: "read" | "edit"` aus `roles` (schon im Login-Response vorhanden) und Workflow-Zustand ab. Buttons, die die Rolle nicht ausführen darf, werden nicht gerendert.

**Dateien:** Sidebar-Navigationskonfiguration, `ArtifactForm` und verwandte Detail-Views (React).
**Testing:** Component-Test: Viewer-Rolle rendert Sidebar → keine Admin-Einträge, keine Edit-Buttons im Formular.

### 3. U2 — Suspect-Propagation tot

**Problem:** Änderung an einem Upstream-Requirement macht Kind-Requirement, Testfall, Architekturelement, Bedarf nicht `suspect`. Der Requirement-Serializer liefert `suspect` gar nicht aus.

**Fix:**
- `suspect`-Feld im `RequirementSerializer` (und Analog bei verwandten Artefakttypen, sofern das Modell das Feld führt) ergänzen.
- Prüfen, ob die Propagationslogik im Service existiert und nur nicht rausgereicht wird, oder komplett fehlt — Audit belegt nur das Serializer-Symptom, nicht die Ursache. Klärung erfolgt beim Implementieren (kein offener Design-Punkt, reine Code-Recherche).

**Dateien:** Serializer(s) in `backend/rest_api/`, ggf. Propagationslogik in `backend/application/` oder `backend/traceability/`.
**Testing:** Serializer-Test (Feld im Output), Service-Test (Upstream-Änderung → Downstream `suspect=True`).

### 4. H5.1-3 — Claude Code / OpenCode nicht verdrahtet

**Problem:** `.claude/settings.json` enthält einen `mcpServers`-Block, den Claude Code nicht liest (nur `.mcp.json`/`~/.claude.json`). GET `/mcp/` liefert bei `Accept: text/event-stream` 200 statt 405, was das MCP-SDK in eine Reconnect-Schleife treibt. `opencode.json` hat literale `{...}`-Klammern statt `{env:...}`-Syntax, Auth schlägt fehl.

**Fix:**
- `.mcp.json`: ReqogniLoom als `type: http`, URL `${MCP_REQOGNILOOM_URL}/mcp/`, Bearer aus `${MCP_REQOGNILOOM_API_KEY}`. `mcpServers`-Block aus `.claude/settings.json` löschen.
- Backend: GET `/mcp/` bei `Accept: text/event-stream` → 405 statt 200.
- `opencode.json`-Doku/Beispiel: `{env:REQOGNILOOM_API_KEY}` statt literaler Klammern.

**Dateien:** `.mcp.json`, `.claude/settings.json`, `backend/mcp_server/views.py` (o.ä.), OpenCode-Doku.
**Testing:** View-Test für den 405-Fall. Rest ist Konfiguration, kein automatisierter Test nötig.

### 5. R3 — REST-API-Hygiene-Batch

**Problem (P0/0a-Teilmenge):** Unbekannte Felder werden bei Create still verworfen (kein 400). `?page=99` liefert 500 statt einer sinnvollen Antwort. Batch-JSON-RPC liefert 500. Parse-Error liefert HTTP 401 statt 400.

**Fix:**
- Serializer/View-Validierung: unbekannte Felder → 400 mit Feldname (betrifft u. a. Requirement `parent_id`, ICD `contract_spec`/`icd_type`).
- Pagination: `page` außerhalb des gültigen Bereichs → leere Liste oder 404, nicht 500.
- MCP-Server: Batch-JSON-RPC-Request korrekt verarbeiten statt 500.
- MCP-Server: Parse-Error (`-32700`) → HTTP 400, nicht 401.

**Dateien:** betroffene Serializer/Views in `backend/rest_api/`, `backend/mcp_server/protocol_handler.py`.
**Testing:** Je ein View-/Protocol-Test pro Fall (unbekanntes Feld, ungültige Page, Batch-Request, Parse-Error).

### 6. R5/R7 — KI-Robustheit (volle P0-Fassung)

**Problem:** Von 11 live getesteten KI-Pfaden sind 4 tot — nicht wegen des Modells, sondern wegen Parser-/Pipeline-Fehlern: `LlmResult.score` akzeptiert nur 0.0-1.0, das Modell liefert eine Zehnerskala. Konsistenzprüfung stirbt an nicht-JSON-Antworten ohne Repair/Retry. Der 180s-Retry-Wrapper wartet auch bei sofortigen, nicht-retrybaren Fehlern (z. B. 401) die volle Zeit aus. Requirements/Needs/Architecture bekommen beim Anlegen kein Embedding, wodurch "Ähnliche" und "Grounding" leer bleiben. Der Health-Endpoint meldet `llm_provider: ok` und `memory_backend: ok`, ohne einen echten Call zu machen — beides war während des gesamten Audits falsch. KI-Antworten kommen auf Englisch, obwohl der Workspace `language=de` gesetzt hat.

**Fix:**
1. `LlmResult.score`-Normalisierung: Werte >1 durch 10 teilen, >10 durch 100 teilen, sonst Parse-Fehler mit Rohtext ins Log. Prompt-Template `validate_artifact` um "score between 0.0 and 1.0" ergänzen.
2. Konsistenz-Task: JSON-Repair (ersten `{`…letzten `}` extrahieren) + ein Retry mit "answer with JSON only". Nutzer-Fehlertext statt Exception-Klassenname.
3. Retry-Wrapper: non-retryable Fehler (z. B. 401 Auth) verlassen die 180s-Schleife sofort statt sie auszuwarten.
4. Embedding-Erzeugung als Celery-Task bei Create/Update von Requirement, Need, Architecture. Backfill-Command für bestehende Artefakte ohne Embedding.
5. Health-Endpoint: echter Probe-Call (kleinster Prompt, 5s Timeout) statt reiner "API-Key konfiguriert"-Prüfung; Honcho-404 ist nicht `ok`.
6. `{language}`-Variable aus Workspace-Sprache in alle relevanten Prompt-Templates, Default Deutsch.

**Dateien:** `backend/llm_adapter/` (Parser, Retry-Wrapper, Prompt-Templates), Celery-Task für Embeddings (`backend/application/` oder `backend/memory/`), Health-View.
**Testing:** Unit-Test für Score-Normalisierung (Zehnerskala, Hunderterskala, Fehlerfall), Unit-Test für JSON-Repair, Retry-Wrapper-Test (non-retryable bricht sofort ab), Celery-Task-Test für Embedding-on-Create, Health-View-Test mit gemocktem fehlschlagendem Provider.

---

## Reihenfolge

1. R2 (blockiert Live-Tests aller anderen Punkte, auch innerhalb dieser Gruppe)
2. H5.1-3 (macht MCP-Clients überhaupt nutzbar für weitere Live-Verifikation)
3. R3, T1, U2 (unabhängig voneinander, parallelisierbar)
4. R5/R7 (größter Einzelblock dieser Gruppe, zuletzt)

## Risiken

- U2: Ursache (Serializer-Symptom vs. fehlende Propagationslogik) unbekannt bis zur Code-Recherche — kann den Umfang dieses einen Punkts verschieben, ändert aber nichts an den anderen fünf.
- R5/R7 Punkt 4 (Embedding-Backfill): Laufzeit bei großem Artefaktbestand nicht abgeschätzt — als eigener, beobachtbarer Celery-Task ausführen, nicht synchron.

## Nicht-Ziele

- Keine Änderung an den 15 Trace-Link-Typen oder der Erlaubt-Matrix (gehört zu U3, spätere Gruppe).
- Kein Rollen-Redesign über das Rendering-Gate hinaus (T2/T3, spätere Gruppe).
- Keine Async-ifizierung aller KI-Calls (R5-Fix-Vorschlag 6, spätere Gruppe).
