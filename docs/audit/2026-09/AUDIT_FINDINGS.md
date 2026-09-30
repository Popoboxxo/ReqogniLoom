---
type: REVIEW
scope: canonical-findings
status: final
date: 2026-09-30
author_agent: validator
baseline_ref: main @ abd61aed
branch: chore/system-audit-2026-09
---

# AUDIT_FINDINGS — Kanonisches Finding-Register Systemaudit 2026-09

> **Rolle dieses Dokuments.** Es ist das ** formale Konsistenz-Gate** über neun
> Workpackage-Reports. Es führt **keine neue Fachanalyse** durch, **erfindet und
> entfernt keine Findings** und **bewertet nicht neu**. Es vereinheitlicht IDs,
> Schweregrade, Klassifikationen und Cross-Referenzen, adjudiziert Widersprüche
> zwischen den Agenten und macht die Belegbarkeit stichprobenartig prüfbar.
> Die **inhaltliche Bewertung** eines Findings bleibt beim jeweiligen Audit-Agenten
> und steht im WP-Report. Dieses Register ist der **Index**, nicht der Report.

---

## 1. Kopfangaben

| Aspekt | Wert |
|---|---|
| **Audit-Basis** | `main` @ `abd61aed` (= `chore/system-audit-2026-09` bei Start des Gates) |
| **Branch** | `chore/system-audit-2026-09` (8 Commits über `main`) |
| **Zeitfenster** | 2026-09-29 (WP-Läufe) bis 2026-09-30 (Gate + Sicherheits-Nachtrag) |
| **Beteiligte WPs** | WP-1a, WP-1b, WP-1c, WP-1d, WP-2, WP-3, WP-3b, WP-4, WP-5, WP-6a, WP-6b |
| **Reports** | 9 Dateien unter `docs/audit/2026-09/` |
| **Evidenz** | `docs/audit/2026-09/AUDIT_EVIDENCE/` (≈ 60 Dateien + Screenshots) |
| **Findings gesamt** | **280 Befunde** (+ 5 bestätigte Kontrollen = 285 Zeilen) / **260 eindeutige IDs** (25 IDs doppelt vergeben → §9) |
| **Gate-Agent** | `validator` |

### 1.1 Vor-Audit-Bezug und seine Grenzen

| Aspekt | Wert |
|---|---|
| **Vor-Audit** | `docs/se/reports/deep_audit/system-audit-2026-09/` |
| **Register** | `09-evidence-register.md`, gültige Tracks **`CR-01` … `CR-47`** |
| **Issue-Referenzbasis** | `AUDIT_EVIDENCE/issue-inventory.md` — **608 Issues**, davon **40 offen**, Quelle GitHub `Popoboxxo/ReqogniLoom` @ `abd61aed` |

**Grenzen des Vor-Audit-Bezugs** (bewusst nicht aufgelöst):

1. **Kein 1:1-Mapping.** `CR-NN` ist ein *Vor-Audit-Track*, `AUD-2026-09-NNN` ist ein
   *Befund*. Viele CR-Tracks sind mehrere Befunde wert (z. B. `CR-20` → 15 Findings
   in WP-1b allein). Die Spalte „CR-Track" in der Master-Tabelle ist daher
   **eine Zuordnung, keine Identität**.
2. **Issue-Basis ist ein Schnappschuss.** Das Inventar wurde am 2026-09-29 via `gh`
   read-only gezogen. Issues, die seither neu entstanden oder geschlossen wurden,
   fehlen. Es wurde **kein** Issue angelegt, kommentiert oder geschlossen.
3. **Codeberg verworfen.** Der Sekundär-Remote (`dduchrow/ai-native-reqflow-POC`)
   steht auf `c4cb7ea8` (2026-07-23) und ist **veraltet**; nicht als Quelle genutzt.
4. **„Bestätigt" heißt nicht „behoben".** `BESTAETIGT` bedeutet: der Vor-Audit-Befund
   wurde am aktuellen Code erneut bestätigt. Ein geschlossenes GitHub-Issue bei
   weiter bestehender Wirkung ist als `BESTAETIGT (geschlossen, Wirkung besteht fort)`
   geführt (Beispiel `AUD-2026-09-121`, Issue #171).

---

## 2. Legende

### 2.1 Kanonische Schweregrad-Skala (5-stufig)

| Kanonisch | Bedeutung | Wirkung |
|---|---|---|
| **Critical** | Betriebs-/Datenverlust, Sicherheitsvorfall, oder Kernfunktion fällt aus | sofort |
| **High** | Funktionsverlust oder Vertragsbruch unter Realbedingungen | vor Release |
| **Medium** | Korrektheits-, Drift- oder Messlücke ohne akuten Ausfall | geplant |
| **Low** | Hygiene, Struktur, Dokumentation | Backlog |
| **Info** | Beobachtung, Präzisierung, Negativbefund | keine |

### 2.2 Abbildungstabelle P-Skala → kanonische Skala (**offengelegt**)

WP-3 und WP-3b verwendeten eine **P-Skala**; alle übrigen WPs die 5-stufige Skala.
Diese Abbildung wurde für **alle 50 Findings** aus WP-3 und WP-3b angewandt:

| Original | Kanonisch | Anwendung |
|---|---|---|
| `P0` | **Critical** | in keinem WP verwendet |
| `P1` | **High** | WP-3: 3 · WP-3b: 2 |
| `P2` | **Medium** | WP-3: 7 · WP-3b: 11 (+1 Querschnitts-Finding `324`) |
| `P3` | **Low** | WP-3: 12 · WP-3b: 12 |
| `Info` | **Info** | WP-3: 3 |

**Grundsatz:** Die Abbildung ist rein formal. **Kein Finding wurde dadurch
auf- oder abgestuft.** Das Original bleibt in der Spalte „Sev (orig)" der
Master-Tabelle und im jeweiligen WP-Report unverändert erhalten, damit die
Einstufung des jeweiligen Audit-Agenten nachvollziehbar bleibt.
Einzelheiten pro Finding stehen in §5.

### 2.3 Klassifikations-Vokabular (geschlossen)

| Wert | Bedeutung | Zählung in Findings? |
|---|---|---|
| `NEU` | vom jeweiligen WP erstmals erhoben | **ja** |
| `DUPLIKAT` | bereits an anderer Stelle erfasst | **ja** |
| `BESTAETIGT` | Vor-Audit-/Fremd-Befund am aktuellen Code bestätigt | **ja** |
| `WIDERLEGT` | Vor-Audit-/Fremd-Aussage am aktuellen Code widerlegt | **ja** |
| `BLOCKED` | nicht verifizierbar; **ausdrücklich kein PASS** | **ja** |

**Abgebildete Fremdwerte** (explizit, kein Wert wurde stillschweigend umgedeutet):

| Fremdwert | → kanonisch | Begründung |
|---|---|---|
| `PASS` | `BESTAETIGT` **+ Verweis auf §6** | Negativbefund, **kein Finding** |
| `i18n`, `Design-Token`, `a11y-Fokus`, … (WP-3b, 25 Werte) | `NEU` | Domänenlabel, keine Klassifikation |
| `TRACE-DRIFT`, `ADR-KASKADE`, `SOLL-STALE`, `TEST-CI`, `REQ-CODE-WIDERSPRUCH`, … (WP-5, 21 Werte) | `NEU` | Domänenlabel, keine Klassifikation |
| `SEC-02 Hardcoded Secret`, `Celery / Message-Semantik`, … (WP-1c/6a/6b) | `NEU` | Domänenlabel in der CR/Issue-Spalte |
| `NEU (BLOCKED-Anteil)` | `NEU` + BLOCKED-Vermerk | Teilbefund, Rest bleibt offen |
| `BESTAETIGT (Severity relativiert)` | `BESTAETIGT` | Einstufung relativiert, Klasse bleibt |
| `verwandt, nicht dupliziert` | `NEU` | Abgrenzung, kein Duplikat |
| `—` (keine Angabe) | `NEU` | Default; in 1 Fall `BLOCKED` |

### 2.4 **PASS-Regel** (Negativbefunde sind keine Findings)

> **Regel:** Eine als `PASS` klassifizierte Zeile ist **kein Befund**, sondern eine
> **bestätigte Kontrolle**. Sie wird **getrennt** in §6 geführt und **nicht** in die
> Finding-Zählung eingerechnet. `BLOCKED` ist ausdrücklich **kein PASS**.

**Begründung:** Würden Negativbefunde mitgezählt, stiege die Gesamtzahl um 5 und die
Verteilung würde systematisch zu Gunsten eines WP-Reports verschoben — WP-4 hätte
5 „Findings", von denen keines ein Defekt ist. Die Regel hält die Kennzahl
aussagekräftig: **280 ist die Zahl der Befunde**, die Kontrollen stehen daneben.

### 2.5 ID-Bereiche und reservierte Blöcke

Finding-IDs werden in **Blöcken pro Workpackage** vergeben. Stand nach dem Gate:

| Block | Anzahl | WP / Status |
|---|---:|---|
| `001–025` | 25 | WP-3 (Browser) |
| **`026–029`** | 4 | **RESERVIERT** — nicht vergeben |
| `030–067` | 38 | WP-1a/1b/1d (MCP, LLM-Adapter, REST) |
| **`068–069`** | 2 | **RESERVIERT** |
| `070–093` | 24 | WP-1a/1d (Round-Trip, Schema-Drift) |
| **`094–099`** | 6 | **RESERVIERT** |
| `100–119` | 20 | WP-2 (Native Plugins) |
| `120–149` | 30 | WP-1c (Infrastruktur) |
| `150–153` | 4 | WP-2 (Native Plugins) — **behalten** nach Regel „früherer Commit" |
| `154–169` | 16 | WP-4 (Datenmodell) |
| `170–190` | 21 | WP-4 (Datenmodell) — **behalten** nach Regel „früherer Commit" |
| `191–206` | 16 | WP-5 (Traceability) |
| **`207–219`** | 13 | **RESERVIERT** |
| `220–241` | 22 | WP-6a (Security) |
| **`242–269`** | 28 | **RESERVIERT** |
| `270–288` | 19 | WP-6b (Reliability) |
| **`289–299`** | 11 | **RESERVIERT** |
| `300–324` | 25 | WP-3b (Frontend statisch) |
| **`325–328`** | 4 | WP-4 — **in diesem Gate vergeben** (früher `150–153`) |
| **`329`** | 1 | **RESERVIERT** (Trenner) |
| `330–350` | 21 | WP-5 (Traceability) — **in diesem Gate vergeben** (früher `170–190`) |
| **`351+`** | — | **FREI** — nächster freier Block für Folge-Arbeit |

**Belegung:** 285 IDs, **jede genau einmal** (verifiziert, §12.2).

**Regel für Folge-Arbeit:** Neue Findings erhalten IDs **ausschließlich** aus einem
oben als **RESERVIERT** markierten Block (`026–029`, `068–069`, `094–099`, `207–219`,
`242–269`, `289–299`, `329`, ab `351`). Das gilt insbesondere für **parallele Agenten**:
Bereiche müssen **vor dem Dispatch** festgelegt werden, sonst entstehen erneut
Kollisionen (siehe §14, P-3/P-4).

> **Keine Kollisionen mehr.** Die zuvor doppelt vergebenen Blöcke `150–153` und
> `170–190` sind aufgelöst; jeder Block gehört jetzt **genau einem** WP.

**Regel für Folge-Arbeit:** Neue Findings erhalten IDs **ausschließlich** aus einem
oben als **RESERVIERT** markierten Block. `026–029`, `068–069`, `094–099`,
`207–219`, `242–269`, `289–299` sowie alles ab `325` sind unbelegt und dürfen
vergeben werden, **ohne** einen bestehenden Block zu berühren.
**Die beiden Kollisionsblöcke `150–153` und `170–190` sind gesperrt**, bis der User
entscheidet (§9, offene Punkte).

> **Hinweis zur Auftragsannahme:** Die im Auftrag genannte Lückenliste war teilweise
> ungenau. `044–049`, `118–119`, `130–149` und `191–206` sind **keine** Lücken,
> sondern belegte Findings. Maßgeblich ist die Tabelle oben.

---

## 3. Master-Finding-Tabelle

**285 Zeilen** (280 Befunde + 5 bestätigte Kontrollen), sortiert nach Schweregrad
(kanonisch), dann WP, dann ID.
Spalte **Sev (orig)** = Originalwert des jeweiligen WP-Agents,
**Sev (kanon.)** = normalisiert. Klassifikation **PASS → Kontrolle** verweist auf §6.


| ID | Sev (orig) | Sev (kanon.) | WP | Klassifikation | CR-Track / Issue | Ort | Kurztitel | Status |
|---|---|---|---|---|---|---|---|---|
| AUD-2026-09-030 | **Critical** | **Critical** | WP-1a/1b/1d | NEU | — | `backend/reqogniloom/settings.py:879`; `backend/mcp_server/views.py:272`; `backend/mcp_server/throttling.py:164` | Redis-Ausfall hängt alle 13 MCP-Endpoints unbegrenzt (kein Timeout) | offen |
| AUD-2026-09-031 | **Critical** | **Critical** | WP-1a/1b/1d | NEU | — | `backend/reqogniloom/health.py:118-190` | `/health/` meldet „ok", während App+Auth+Schema unbenutzbar hängen | offen |
| AUD-2026-09-052 | **Critical** | **Critical** | WP-1a/1b/1d | NEU | **BESTAETIGT** (CR-20-Nachbar; #118) | `backend/llm_adapter/providers.py:1080` | Anthropic-Default `claude-3-opus-20240229` ist seit 2026-01-05 retired — jeder Aufruf ohne `LLM_MODEL` schlägt fehl | offen |
| AUD-2026-09-070 | **Critical** | **Critical** | WP-1a/1b/1d | NEU | CR-11, CR-42, CR-12 | `application/import_service.py:196-232` ↔ `views.py:8085` | CSV-Round-Trip des eigenen Exporters unbrauchbar: `# terminology_profile`-Kommentarzeile wird als Header gelesen → **HTTP 201 `success:true` bei 0 importierten Zeilen** | offen |
| AUD-2026-09-071 | **Critical** | **Critical** | WP-1a/1b/1d | NEU | CR-11, CR-42 | `application/reqif_import_service.py:697`, `:681`, `:415` | ReqIF-Import liefert `success:true` mit 915 × „internal error"; Ursache `pl_artifact_pkey`-UniqueViolation, weil `SPEC-OBJECT/@IDENTIFIER` die globale `Artifact.id` ist | offen |
| AUD-2026-09-120 | **Critical** | **Critical** | WP-1c | NEU | **NEU** (kein Vor-Audit-Track; CR-35-Nähe) | `backend/reqogniloom/celery.py:31-36` | Alle 4 Queues identisch gebunden → **jede Task läuft 4×** | offen |
| AUD-2026-09-121 | **Critical** | **Critical** | WP-1c | NEU | **BESTAETIGT** Klasse #171 (geschlossen 2026-07-29, Wirkung besteht fort) | `Live: `celery-beat`-Log 0× `Sending due task`; `settings.py:817-830` | Beat dispatcht **nie** — gesamter 5-s/60-s/Monats-Schedule tot | offen |
| AUD-2026-09-122 | **Critical** | **Critical** | WP-1c | NEU | **NEU** (CR-37) | `scripts/backup.sh:84-87` | `backup.sh` ist permanent nicht ausführbar (`exit 1`) | offen |
| AUD-2026-09-123 | **Critical** | **Critical** | WP-1c | NEU | **NEU** (CR-37) | `scripts/restore.sh:183,186,198-213` | Backup-Datei wird nie in den Container kopiert; `psql -f` liest Datei statt stdin | offen |
| AUD-2026-09-115 | **Critical** | **Critical** | WP-2 | NEU | — (CR-24 verwandt) | `integrations/hermes-agent-plugin/__init__.py:79` (via `:110,:120,:127`)` | `_handle_slash` wirft `TypeError` — dokumentiert „never raises"; `start`/`status`/`answer` brechen live | offen |
| AUD-2026-09-345 | Critical | **Critical** | WP-5 | NEU | — | `matrix:331`, `backend/Dockerfile:154` | Backup/Restore als `Implemented/Covered`, Restore-Skript nie im Image | offen |
| AUD-2026-09-346 | Critical | **Critical** | WP-5 | NEU | — | `backend/llm_adapter/providers.py:1080` | Default-Modell `claude-3-opus-20240229` abgeschaltet; jeder Anthropic-Call scheitert | offen |
| AUD-2026-09-220 | **CRITICAL** âš ï¸* | **Critical** | WP-6a | NEU | — | `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2246` | Live `reqlo_`-API-Key im Klartext committet â€” **Key widerrufen 2026-09-30, Arbeitsbaum redigiert, Historie offen** | TEILWEISE BEHOBEN |
| AUD-2026-09-221 | **CRITICAL** | **Critical** | WP-6a | NEU | — | `backend/mcp_server/views.py:272` + `backend/reqogniloom/settings.py:879-884` | Unauthentifizierter Rate-Limit-Check vor AuthN + Cache ohne `SOCKET_TIMEOUT` = DoS-VerstÃ¤rker | offen |
| AUD-2026-09-032 | **High** | **High** | WP-1a/1b/1d | NEU | **CR-22** | `backend/mcp_server/views.py:291-304` vs. `:311-325` | Zwei inkompatible Fehler-Hüllen (`code` int vs. `error_code` str) auf demselben Endpunkt | offen |
| AUD-2026-09-033 | **High** | **High** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/protocol_handler.py:536` | Nicht-dict `params` ⇒ HTTP 500 statt `-32600`/`-32602` (AttributeError außerhalb jedes try) | offen |
| AUD-2026-09-034 | **High** | **High** | WP-1a/1b/1d | NEU | — | `backend/auth_tenancy/services/authentication.py:616` | `create_api_key` persistiert beliebige Scope-Strings für User-Keys; Key ist stumm schreibunfähig | offen |
| AUD-2026-09-035 | **High** | **High** | WP-1a/1b/1d | NEU | — | `backend/auth_tenancy/services/authentication.py:562` | `ApiKey.tenant_id` ist dekorativ — `validate_api_key` nutzt `api_key.user.tenant_id` | offen |
| AUD-2026-09-036 | **High** | **High** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/tools/generic.py:512-515` | Domänen-`ValidationError`/`NotFoundError` als „internal error" maskiert; REST mappt dieselbe Exception auf 400 | offen |
| AUD-2026-09-053 | **High** | **High** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/providers.py:1333` | OpenAI-Default `gpt-4` → Alias `gpt-4-0613`, API-Shutdown 2026-10-23; `.env.example:184,189` nennt ebenfalls retired Modelle | offen |
| AUD-2026-09-055 | **High** | **High** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/providers.py:1100,1347,1689` | SDK-eigenes `max_retries=2` läuft zusätzlich zum 4er-`PolicyEngine`-Loop → **12 HTTP-Requests** pro logischem Aufruf bei 429/5xx | offen |
| AUD-2026-09-057 | **High** | **High** | WP-1a/1b/1d | NEU | #576 (teilgewirkt) | `backend/llm_adapter/providers.py:1215,1407,1595,1749,1941` + `dispatcher.py:187-193` | `decompose_requirement` nutzt nackten `json.loads` in allen 5 HTTP-Providern → `JSONDecodeError` mit Roh-Parsertext durch `get_task_status` ins Client | offen |
| AUD-2026-09-058 | **High** | **High** | WP-1a/1b/1d | NEU | CR-12/CR-42 (Vertragsdrift) | `backend/llm_adapter/providers.py:1663,2014` vs. `models.py:2411`, `llm-settings.ts:24` | `azure` implementiert und in Doku beworben, aber in DB-Enum, REST-ChoiceField und UI-Liste **nicht wählbar** | offen |
| AUD-2026-09-061 | **High** | **High** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/providers.py:390,413,438,455` | Mock liefert 4 feste Token-Konstanten (42/100/200/120), prompt-unabhängig, die als exakte API-Nutzung in Budget + Aggregation einfließen | offen |
| AUD-2026-09-062 | **High** | **High** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/router.py:286-292` + `tasks.py:166-172` | Gesamtsumme wird als `input_tokens` gebucht, `output_tokens` ist konstruktionsbedingt 0 → keine Kosten-Attribution nach Modell/Provider | offen |
| AUD-2026-09-066 | **High** | **High** | WP-1a/1b/1d | NEU | CR-36 (Nachbar) | `backend/llm_adapter/dispatcher.py:149-152,177-178` | Ausgefallener Celery-Worker ist für den Aufrufer nicht von „läuft noch" unterscheidbar — `pending` ohne ETA/Ablauf | offen |
| AUD-2026-09-072 | **High** | **High** | WP-1a/1b/1d | NEU | CR-11 | `live `POST /workspaces/B/import/csv/` | CSV-Import **nicht idempotent**: dreifacher Import derselben Datei erzeugt 3 Duplikate; keine Duplikaterkennung | offen |
| AUD-2026-09-073 | **High** | **High** | WP-1a/1b/1d | NEU | CR-14 | `live `GET /trace-links/?page=0\/abc\/99999999`, `GET /glossary/?page=0\/abc` | **HTTP 500** auf ungültiges `page` (5 Werte je Endpunkt), während `/workspaces/` korrekt 404 liefert | offen |
| AUD-2026-09-074 | **High** | **High** | WP-1a/1b/1d | NEU | CR-11 | `rest_api/api_key_views.py:81`, `user_management_views.py:81`, `link_type_views.py:90` | 4 Listen-Endpunkte ohne Pagination: `/api-keys/` (200 Items, 54 KB), `/users/`, `/link-type-defaults/`, `workspaces/{id}/link-type-definitions/`; `page`/`page_size` werden komplett ignoriert | offen |
| AUD-2026-09-075 | **High** | **High** | WP-1a/1b/1d | NEU | CR-12, CR-21 | `rest_api/openapi.py:71-98`; `GET /api/schema/` | **432 von 439 Operationen deklarieren keinen Fehler-Fall**, 0 deklarieren 5xx; `COMMON_ERROR_RESPONSES` ist tote Deklaration (nirgends verwendet) | offen |
| AUD-2026-09-076 | **High** | **High** | WP-1a/1b/1d | NEU | CR-11, CR-42 | `application/reqif_export_service.py:296` | ReqIF-Export ist **nicht ReqIF-1.2-konform**: `REQ-IF-HEADER/@reqIFVersion` fehlt, `THE-VERSION` fehlt, 0 von 915 `SPEC-OBJECT` enthalten das Pflicht-Element `SPEC-OBJECT-CONTENT` | offen |
| AUD-2026-09-077 | **High** | **High** | WP-1a/1b/1d | NEU | CR-11 | `rest_api/error_envelope.py:48-68` | Fehlerhülle enthält **kein `trace_id`/`request_id`**, obwohl die App durchgängig eine `request_id` loggt — 500er sind für Clients nicht korrelierbar | offen |
| AUD-2026-09-078 | **High** | **High** | WP-1a/1b/1d | NEU | CR-12 | `views.py:8176-8216` (Export) vs. `ReqifImportView` | ReqIF-Import akzeptiert nur `multipart/form-data`; Export liefert `application/xml` — asymmetrisch und im OpenAPI-Schema **ohne** `requestBody` dokumentiert | offen |
| AUD-2026-09-124 | High | **High** | WP-1c | NEU | **NEU** (CR-37) | `scripts/restore.sh:49,116` vs. `deploy/docker-compose.yml:372` | Format-/Ort-Inkompatibilität: `.sql.gz` im Volume vs. `*.dump\/*.sql` in `./backups` | offen |
| AUD-2026-09-125 | High | **High** | WP-1c | NEU | — | `backend/audit/archive.py:448` vs. `celery.py:45` | `audit.archive_lifecycle_manager` beim Worker **nicht registriert** | offen |
| AUD-2026-09-126 | High | **High** | WP-1c | NEU | **NEU** (kein Vor-Audit-Track; CR-35-Nähe) | `live `app.conf.task_acks_late=False`; 7 Task-Dateien` | pre-ack + kein Retry ⇒ Worker-Kill = **endgültiger** Task-Verlust | offen |
| AUD-2026-09-127 | High | **High** | WP-1c | NEU | **NEU** (CR-37) | `scripts/restore.sh:183` | Restore nicht atomar (`--clean --if-exists` in-place auf der Live-DB) | offen |
| AUD-2026-09-128 | High | **High** | WP-1c | NEU | **NEU** (CR-37) | `deploy/docker-compose.yml:357,361,372` | 42-h-Horizont, kein Off-Host, keine Verschlüsselung, keine Medien/Uploads | offen |
| AUD-2026-09-129 | High | **High** | WP-1c | NEU | — | `backend/reqogniloom/health.py:118-313`; `deploy/docker-compose.yml:642` | `/health/` prüft weder Cache **noch Worker/Beat**; `degraded` liefert HTTP **200** | offen |
| AUD-2026-09-137 | High | **High** | WP-1c | NEU | **BESTAETIGT** `CR-32`, `CR-38` | `.github/workflows/docker-publish.yml:102,145,168,183`; `ci.yml:4-7` | Kein Test-vor-Image-Vertrag; Scan≠Push-Artefakt; **kein** SBOM/Cosign/Provenance | offen |
| AUD-2026-09-149 | High | **High** | WP-1c | NEU | — | `keine Staging-Definition; `ci.yml`/`docker-publish.yml` 0× `environment:`/`concurrency:` | **Keine Staging-Stufe** zwischen CI und Produktion; keine Approval-Gate | offen |
| AUD-2026-09-100 | **High** | **High** | WP-2 | NEU | — | `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:7` + `.gitignore:2` | `main: dist/plugin.js` ist gitignored; Hermes-Installation komplett undokumentiert | offen |
| AUD-2026-09-101 | **High** | **High** | WP-2 | NEU | CR-24 | `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:8-46` | Manifest ist VS-Code-Schema, nicht der Hermes-`manifest.json {name, api}`-Vertrag | offen |
| AUD-2026-09-109 | **High** | **High** | WP-2 | NEU | — | `…/src/api.ts:143-153`; `integrations/hermes-agent-plugin/reqogniloom_client.py:136-139` | Beide Plugins lesen nur `results[]`, ignorieren `next` → Ziel-Workspace live unerreichbar (25 von 401) | offen |
| AUD-2026-09-110 | **High** | **High** | WP-2 | NEU | — | `integrations/hermes-agent-plugin/__init__.py:62,105-107` | Hilfetext-Beispiel `start requirement` wird live mit 400 abgelehnt (nur PascalCase gültig) | offen |
| AUD-2026-09-114 | **High** | **High** | WP-2 | NEU | — | `…/__tests__/api.test.ts:8-9,31,42-43,62-63`; `…/tests/test_slash_command.py:40` | 210 grüne Tests, zwei Live-Bugs: Fixtures kodieren einen Vertrag, den der Server nicht erfüllt | offen |
| AUD-2026-09-117 | **High** | **High** | WP-2 | NEU | — | `…/src/state.ts:196-198` + `ConnectedView.tsx:6-24` | MCP-Fehler wird nie angezeigt — `interviewError` nur in Views gerendert, die `view==="connected"` nicht baut | offen |
| AUD-2026-09-001 | **P1** | **High** | WP-3 | NEU | NEU (verwandt #1115, #711 ⚠️ beide geschlossen) | `/` — `DashboardViews/*` | 453 Requests für einen Dashboard-Load: 1× `/requirements/` pro Workspace (401 Workspaces ⇒ 401 Requests), keine Pagination, keine Virtualisierung | offen |
| AUD-2026-09-002 | **P1** | **High** | WP-3 | NEU | **BESTAETIGT CR-40/FEA-005** (7 geschlossene Issues: #676, #421, #595, #610, #651, #653, #654) | `/settings`, `/import`, `/system-settings`, `/profile`; 112 Stellen in 41 Dateien` | 112 `t()`-Keys fehlen in **beiden** Locales, maskiert durch Inline-Default ⇒ in DE englisch, in EN deutsch | offen |
| AUD-2026-09-003 | **P1** | **High** | WP-3 | NEU | **BESTAETIGT CR-40/FEA-001** (verwandt #449/#592/#608/#720, alle geschlossen) | `AppShell global` | Kein Skip-Link; 25 Sidebar-Einträge ⇒ 50+ Tabs pro Hauptbereichswechsel | offen |
| AUD-2026-09-300 | P1 | **High** | WP-3b | NEU | #619 | `components/BaselinesView/BaselinesPanels.tsx:57` | 116 Keys fehlen in BEIDEN Locales (41 Dateien) | offen |
| AUD-2026-09-301 | P1 | **High** | WP-3b | NEU | #619 | `frontend/src/test/i18n-parity.test.ts:186` | Ratchet-Obergrenze 116 macht die Lücke unsichtbar | offen |
| AUD-2026-09-160 | High | **High** | WP-4 | NEU | — | `presets/registry.py:13` vs. 6 Module` | SSOT-Behauptung falsch; 7 datengetrieben / 5+ hartkodiert | offen |
| AUD-2026-09-161 | High | **High** | WP-4 | NEU | — | `attribute_definitions/stage_matrix.py:40-47` | `stage_mandatory` geseedet, **null** Produktionskonsumenten | offen |
| AUD-2026-09-162 | High | **High** | WP-4 | NEU | — | `presets/gate.py:536-549` | Downgrade-Blocker ist **fail-open** (`except Exception: pass`) | offen |
| AUD-2026-09-167 | High | **High** | WP-4 | NEU | — | `application/import_service.py:714-722` | CSV-Import schreibt `current_state` ohne Transition, History, Version | offen |
| AUD-2026-09-168 | High | **High** | WP-4 | NEU | — | `application/reqif_import_service.py:791-793` | ReqIF-Import ändert `current_state` **ohne `version`-Bump** → CAS-Blindstelle | offen |
| AUD-2026-09-169 | High | **High** | WP-4 | NEU | **BESTAETIGT (CR-07) + NEU** | `application/interview_service.py:337-344, 354-369` | GET mutiert Zustand; `except Exception`; Status nie persistiert; `version` ohne State-Änderung | offen |
| AUD-2026-09-180 | High | **High** | WP-4 | NEU | — | `26 von 44 Tabellen` | `workspace_id` **ohne FK** — inkl. `pl_artifact`, `pl_requirement` | offen |
| AUD-2026-09-181 | High | **High** | WP-4 | NEU | #1093 (geschlossen) | `persistence/migrations/0093_…py:76-78` + 99 Live-Zeilen` | Datenmigration nicht nachgelaufen; Tag-Rückstände in 30 lebenden Links | offen |
| AUD-2026-09-325 | High | **High** | WP-4 | NEU | — | `traceability/audit/hierarchy.py:172-186`, `baseline/services.py:430`, `baseline/delta_index_builder.py:288`, `frontend/src/utils/traceEndpoints.ts:72-75` | `refines` (Built-in, Hierarchiekante) fehlt in **allen 3** Hierarchie-Definitionen | offen |
| AUD-2026-09-326 | High | **High** | WP-4 | NEU | — | `application/reqif_import_service.py:886-897` | ReqIF-Import umgeht Workspace-Katalog komplett | offen |
| AUD-2026-09-327 | High | **High** | WP-4 | NEU | — | `icd/traceability_connector.py:82-87` → `traceability/trace_link_manager.py:334` | ICD-Connector ohne Paar-Validierung | offen |
| AUD-2026-09-191 | High | **High** | WP-5 | NEU | — | `protocol_handler.py:345` vs. `views.py:425` | stdio-Handler existiert, stdio-Transport nicht exponiert; Doku nennt 3 Transporte | offen |
| AUD-2026-09-192 | High | **High** | WP-5 | NEU | CR-30 | `backend`, `frontend/src`, `e2e` | Nur 42.9 % der REQ-IDs haben einen Test-Bezug (3.6 % der Tests) | offen |
| AUD-2026-09-193 | High | **High** | WP-5 | NEU | CR-30 | `.github/workflows/ci.yml:44-55` | 511 von 10 052 Testdefinitionen laufen in keinem CI-Job (`memory`, `link_types`, `tests`) | offen |
| AUD-2026-09-195 | High | **High** | WP-5 | NEU | CR-43 | `RELEASE_v1.8.0-beta.17.md:12` | „Regression-Suite ist vollständig grün" bei 511 nie ausgeführten Tests + 4 eigenen Errors | offen |
| AUD-2026-09-196 | High | **High** | WP-5 | NEU | — | `RELEASE_v1.8.0-beta.17.md:17` | „W1–W4 implementiert, dokumentiert und getestet" — W4-Tests sind rot (65 FE-Fehler) | offen |
| AUD-2026-09-201 | High | **High** | WP-5 | NEU | — | ``SN_Stakeholder_Needs.md`` | Nummerierungslücke: 031 existiert nirgends; Matrix springt 030 → 032 | offen |
| AUD-2026-09-330 | High | **High** | WP-5 | NEU | CR-09, CR-47 | `docs/se/traceability-matrix.md` | 324 Quell-REQ-IDs fehlen in der SOLL-Matrix (24× L2, 300× L3) | offen |
| AUD-2026-09-331 | High | **High** | WP-5 | NEU | CR-09 | `traceability-matrix.md:649-655` | Matrix publiziert 0 von 354 REQ-L3-Zeilen; behauptete 369 vs. gemessene 354 | offen |
| AUD-2026-09-333 | High | **High** | WP-5 | NEU | — | `docs/se/**` | `open_adrs` existiert repo-weit nicht (0/835 REQs) | offen |
| AUD-2026-09-334 | High | **High** | WP-5 | NEU | — | `L1_Gesamtsystem_Requirements.md:37…2522` | 14 von 15 `arch_impact:true` ohne ADR; kein akzeptiertes ADR deckt L1/L2 | offen |
| AUD-2026-09-339 | High | **High** | WP-5 | NEU | — | ``L2_{ReqIF,Comment,VectorSearch}…_Requirements.md`` | `arch_impact` bei L2-Ableitung von `true` auf `false` umgeschrieben, ohne ADR | offen |
| AUD-2026-09-340 | High | **High** | WP-5 | NEU | — | `traceability-matrix.md` §2/§3` | 17 `Implemented`-REQ-L1 mit nicht-implementiertem Kind (3 vollständig) | offen |
| AUD-2026-09-342 | High | **High** | WP-5 | NEU | — | `L2_McpServerSystem_Requirements.md:97-107` | MCP-Tool `semantic_search` als `Implemented/Covered` dokumentiert, existiert nicht | offen |
| AUD-2026-09-343 | High | **High** | WP-5 | NEU | — | `REQ-L2-RQ-001/-002`, `REQ-L2-AT-018`, `REQ-L2-CM-001`, `REQ-L2-RF-015` | 7/29 Stichproben-REQs als nicht umgesetzt markiert, obwohl Code + Tests existieren | offen |
| AUD-2026-09-344 | High | **High** | WP-5 | NEU | — | `REQ-L1-022/-033/-036` | 3 REQ-L1 `Not Implemented` mit vollständig implementierten Kindern | offen |
| AUD-2026-09-347 | High | **High** | WP-5 | NEU | — | `frontend/src/api/llm-settings.ts:22` | Azure implementiert und beworben, aber nicht wählbar | offen |
| AUD-2026-09-348 | High | **High** | WP-5 | NEU | — | `traceability-matrix.md:114` | i18n `Implemented/Covered`; 112 Keys fehlen in beiden Locales, Lint-Regel wirkungslos | offen |
| AUD-2026-09-349 | High | **High** | WP-5 | NEU | — | `backend/application/import_service.py:149,226-233` | CSV-Import meldet Datenverlust als `success: true` | offen |
| AUD-2026-09-350 | High | **High** | WP-5 | NEU | — | `REQ-L2-RO-001/-AS-029/-LA-008` | Asynchronie `Covered`, jede Celery-Task läuft 4× | offen |
| AUD-2026-09-222 | **HIGH** | **High** | WP-6a | NEU | Reopen-Rest zu **#103** (geschlossen) | `backend/auth_tenancy/workspace_scope.py:114`, `backend/auth_tenancy/rest.py:259-271`, `backend/application/requirement_service.py:755` | Workspace-Fence greift auf 269/311 mutierenden Routen nicht | offen |
| AUD-2026-09-223 | **HIGH** | **High** | WP-6a | NEU | — | `backend/reqogniloom/urls.py` (`/admin/`), `settings.py` (kein `ADMIN_ATTEMPTS_BEFORE_LOCKOUT`)` | Django-Admin exponiert, 500-er, ohne Brute-Force-Schutz | offen |
| AUD-2026-09-224 | **HIGH** | **High** | WP-6a | NEU | — | `.github/workflows/*.yml`, `.woodpecker.yml`, `.agents/hooks/` | Kein Secret-Scanning-Gate (weder pre-commit noch CI) | offen |
| AUD-2026-09-225 | **HIGH** | **High** | WP-6a | NEU | **CR-45 verschÃ¤rft** | `.github/workflows/docker-publish.yml:42-185`, `ci.yml:15-343`, `playwright.yml:50-216`, `pages.yml:43-55`, `version-drift-check.yml:49` | 27 von 28 Actions nur Tag-gepinnt bei `packages: write` | offen |
| AUD-2026-09-239 | **HIGH** | **High** | WP-6a | NEU | — | `AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2237-2246`, `AUDIT_EVIDENCE/wp1d-cleanup-verification.md` Â§2` | **Der Audit erzeugte den Secret-Leak selbst**: kein Evidenz-Redactor + Cleanup prÃ¼fte User-LÃ¶schung, aber nie Key-Widerruf | offen |
| AUD-2026-09-270 | **High** | **High** | WP-6b | BESTAETIGT | **#125 (BESTÄTIGT)** · CR-10 | `audit/archive.py:448`, `reqogniloom/celery.py:45`, `audit/apps.py:36`, `settings.py:822` | `audit.archive_lifecycle_manager` ist **nicht** im Worker-Task-Set — monatliche Retention läuft nie, `audit_entry` wächst unbegrenzt | offen |
| AUD-2026-09-281 | **High** | **High** | WP-6b | NEU | CR-06 (neu) | `application/goal_service.py:134-149`, `persistence/models.py:3342-3381` | `as_goal` ohne `UNIQUE(lineage_id, sequence_number)` und ohne `version` → `max+1` unter keinem Lock forkt die Lineage | offen |
| AUD-2026-09-282 | **High** | **High** | WP-6b | NEU | CR-08 (Rest) | `application/adr_service.py:562`, `risk_service.py:686`, `issue_service.py:726`, `change_request_service.py:638`, `main_goal_service.py:556`, `goal_service.py:659` | 6 Transition-Wrapper reichen `expected_version` nicht weiter ⇒ REST-Transitions bleiben last-writer-wins, obwohl dieselben Services `update_*` schützen | offen |
| AUD-2026-09-037 | Medium | **Medium** | WP-1a/1b/1d | NEU | **CR-21** | `AGENTS.md:8,30,58`; `README.md:482,1060,1072,1163,1182,1191,1291` | Stale Zahlen (215/31), interner README-Widerspruch (25 vs. 35), stdio-Phantom | offen |
| AUD-2026-09-038 | Medium | **Medium** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/protocol_handler.py:239` vs. `:515` | Nur `notifications/initialized` ist von der `id`-Pflicht befreit; mit `id` ⇒ 202 ohne Antwort | offen |
| AUD-2026-09-039 | Medium | **Medium** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/protocol_handler.py:469` | Top-Level `null` ⇒ `-32700`; `str`/`int`/`bool` ⇒ 500 statt `-32600` | offen |
| AUD-2026-09-040 | Medium | **Medium** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/protocol_handler.py:572-577` | `tools/call` mit `arguments: null/str/list` oder `name: <int>` ⇒ `-32603` statt `-32602` | offen |
| AUD-2026-09-041 | Medium | **Medium** | WP-1a/1b/1d | NEU | **CR-28** (verwandt) | `backend/mcp_server/views.py:176-190` | Klartext-API-Key im uvicorn-Access-Log; die Ablehnungs-Begründung ist damit unvollständig | offen |
| AUD-2026-09-042 | Medium | **Medium** | WP-1a/1b/1d | NEU | **CR-05** | `backend/mcp_server/tools/interview.py:181-202` | `interview.start` mit `mode: "multi"` ignoriert; verlangt `artifact_type` — Multi-Interview über MCP nicht startbar | offen |
| AUD-2026-09-043 | Medium | **Medium** | WP-1a/1b/1d | NEU | — | `docs/agent-templates/tool-manifest.json` (`comment.*`)` | `comment.create/list/resolve` deklarieren kein `workspace_id`; Create auf gültiges Artefakt ⇒ „Artifact not found" | offen |
| AUD-2026-09-044 | Medium | **Medium** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/protocol_handler.py:264` | Fehlermeldung `bearer_not_supported` widerspricht dem Verhalten und legt einen internen Code offen | offen |
| AUD-2026-09-054 | Medium | **Medium** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/providers.py:1550` | Ollama verwirft `prompt_eval_count` — nur `eval_count` (Output) wird erfasst, Input systematisch verloren | offen |
| AUD-2026-09-056 | Medium | **Medium** | WP-1a/1b/1d | NEU | CR-33 (Nachbar) | `backend/llm_adapter/tasks.py:77,155` | Celery-Task ohne `time_limit`/`soft_time_limit`; `run_capability` ruft `method(**kwargs)` ohne Timeout → 30-s-Default, kein Abbruch | offen |
| AUD-2026-09-059 | Medium | **Medium** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/providers.py:1160-1164` (+4 Pendants)` | `hasattr(message, "usage")` ist `True` bei `usage=None` → `AttributeError` statt sauberem `None` | offen |
| AUD-2026-09-060 | Medium | **Medium** | WP-1a/1b/1d | NEU | CR-05 (Vertragsparität) | `backend/llm_adapter/providers.py:829` | Mock fällt bei unbekanntem `purpose` **stumm** auf `[]` zurück — Tippfehler wird als fachliches „leeres Ergebnis" gemeldet | offen |
| AUD-2026-09-063 | Medium | **Medium** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/token_tracking.py:123-129,162-165,233-243` | Fail-open des Budgets ist vollständig laut: DB-/RLS-Ausfall deaktiviert das Tagesbudget ohne Health-Signal | offen |
| AUD-2026-09-064 | Medium | **Medium** | WP-1a/1b/1d | NEU | — | `backend/application/ai_derivation_service.py:2066-2082` + `settings.py:704` | L4-Mock-Degradation ist markiert, aber es gibt keinen Feature-Gate, der „LLM nicht konfiguriert" **vor** dem Klick sichtbar macht | offen |
| AUD-2026-09-065 | Medium | **Medium** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/checks.py` (fehlt) vs. `:150-212` | Kein System-Check für fehlenden `LLM_API_KEY` — obwohl #1050 und #794 genau solche Checks für seltenere Fehlkonfigurationen gebaut haben | offen |
| AUD-2026-09-079 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-11 | `live `POST /workspaces/B/import/csv/` | Enum-Validierung **inkonsistent**: ungültiger `status` wird still akzeptiert (201 success), ungültiger `type`/`level` dagegen mit 400 `status:"rollback"` und **leerer** `errors`-Liste quittiert | offen |
| AUD-2026-09-080 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-11 | `live, `import_service.py:196` | Kaputtes CSV-Quoting wird **still importiert** (201 success), Restzeile landet im Titel | offen |
| AUD-2026-09-081 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-12 | `views.py:8085` (`CsvExportView`), `views.py:7951` (`CsvImportView`), `settings_views.py:579` | Workspace-fremde Operationen ohne Tenant-Prüfung: CSV-Export liefert **200** (nur wegen RLS leer), CSV-Import **400 validation_error**, `review-policy` **200** — drei Geschwister, drei Verhaltensweisen | offen |
| AUD-2026-09-082 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-14, CR-11 | `link_type_views.py:31-43`, `baseline/views.py:101`, `mcp_server` | **5 Fehlerformate** über 3 Transportformen; `{"detail": …}`-Pfade umgehen `reqogniloom_exception_handler`; `error_envelope.py:8-9` behauptet ein gemeinsames Format, das es nicht gibt | offen |
| AUD-2026-09-083 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-42, CR-21 | `CSV-Import: BOM nicht erkannt, kein Delimiter-Sniffing, und beide Fälle werden mit `title is missing or empty` quittiert — die Meldung beschreibt die Daten statt der Ursache` | CSV-Import: BOM nicht erkannt, kein Delimiter-Sniffing, und beide Fälle werden mit `title is missing or empty` quittiert — die Meldung beschreibt die Daten statt der Ursache | offen |
| AUD-2026-09-084 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-21 | ``AGENTS.md` (Projektbeschreibung + Besondere Patterns)` | `AGENTS.md` nennt „67 APIViews", real **76**; „27 ViewSets" ist exakt korrekt (zählt man `BaseEntityViewSet` mit, kommt man auf die 28 des Auftrags) | offen |
| AUD-2026-09-085 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-12 | `GET /api/schema/`, `reqogniloom/urls.py:35,51-52` | 7 geroutete Pfade fehlen im Schema, darunter der komplette MCP-Ingress (`/api/v1/mcp{,/sse,/messages}`), der DRF-API-Root und das Schema selbst | offen |
| AUD-2026-09-086 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-11 | `application/pdf_report_generator` (reportlab)` | PDF-Report nutzt nur `Helvetica`/`Helvetica-Bold` mit `WinAnsiEncoding`, **ohne eingebetteten Font** — Emoji/CJK/Kyrillisch sind nicht darstellbar | offen |
| AUD-2026-09-087 | **Medium** | **Medium** | WP-1a/1b/1d | NEU | CR-11 | `live `GET /workspaces/A/export/csv/`, `…/reports/pdf/` | CSV-Export ohne `charset=utf-8`; PDF-`Content-Disposition` mit `Zahnbürste…` ohne RFC-5987-`filename*` → Ersatzzeichen im Dateinamen bei Nicht-UTF-8-Clients | offen |
| AUD-2026-09-130 | Medium | **Medium** | WP-1c | NEU | **NEU** (CR-35) | `backend/application/ai_derivation_service.py:396,500` | 648/831 Cache-Keys **ohne TTL** (`timeout=None`), nie invalidiert | offen |
| AUD-2026-09-131 | Medium | **Medium** | WP-1c | NEU | **NEU** (CR-35) | `deploy/docker-compose.yml:543,545`; `settings.py:879-884` | `noeviction`@256 MB ⇒ Cache-Writes scheitern mit OOM; kein `TIMEOUT`-Handling | offen |
| AUD-2026-09-132 | Medium | **Medium** | WP-1c | NEU | — | `live: 5914 `celery-task-meta-*` Keys` | 24-h-Ergebnisaufbewahrung im Broker-DB, ungebremstes Wachstum | offen |
| AUD-2026-09-133 | Medium | **Medium** | WP-1c | NEU | **NEU** (CR-36-Nähe) | `live: `mcp:session:*` in db0` | MCP-Sessions teilen die Broker-DB ⇒ `FLUSHDB` zerstört laufende Sessions | offen |
| AUD-2026-09-134 | Medium | **Medium** | WP-1c | NEU | — | `settings.py:879-884` | Kein `KEY_PREFIX`/`KEY_FUNCTION` ⇒ Tenant-Trennung nur *zufällig* über UUIDs | offen |
| AUD-2026-09-135 | Medium | **Medium** | WP-1c | NEU | — | `deploy/docker-compose.yml:1015-1194` | 4 honcho-Services **ohne** `logging:` ⇒ unbegrenzte Logs | offen |
| AUD-2026-09-136 | Medium | **Medium** | WP-1c | NEU | **BESTAETIGT** `CR-38` | `deploy/docker-compose.yml:567,953,1109` | Kein Image per Digest gepinnt; `honcho:latest` | offen |
| AUD-2026-09-138 | Medium | **Medium** | WP-1c | NEU | — | `scripts/build.sh:88-92`; `deploy/docker-compose.yml` (0× `build:`)` | `build.sh` meldet „Build completed" bei **exit 0** und 0 gebauten Images | offen |
| AUD-2026-09-139 | Medium | **Medium** | WP-1c | NEU | — | `deploy/docker-compose.yml:139,147,933` | Keine getrennten Liveness-/Readiness-Checks; ein Endpoint ist beides und taugt für keines | offen |
| AUD-2026-09-141 | Medium | **Medium** | WP-1c | NEU | **NEU** (CR-35) | `settings.py:899-955`; `rest_api/urls.py:237`; kein OTel/Prometheus in `requirements` | Kein Exporter, kein Tracing, `LOG_LEVEL` nicht konfigurierbar | offen |
| AUD-2026-09-142 | Medium | **Medium** | WP-1c | NEU | — | `**NEU** (Nachfolger zu `fix/deploy-compose-env-drift`)` | 8 referenzierte Variablen fehlen in `.env.example` (u. a. `CELERY_CONCURRENCY`) | offen |
| AUD-2026-09-143 | Medium | **Medium** | WP-1c | DUPLIKAT | **DUPLIKAT #1019** (geschlossen 2026-09-21) | `persistence/embedding_dimensions.py:84`; 4× `vector(384)` gemessen` | Keine Laufzeitfehler möglich (Prämisse **WIDERLEGT**); Nicht-Default-Provider ⇒ stille Degradation | offen |
| AUD-2026-09-147 | Medium | **Medium** | WP-1c | NEU | **NEU** (CR-35) | `deploy/docker-compose.yml:247-295`; `postgresql.auto.conf:3` | `max_connections=300` nur im Volume, nicht versioniert; `shared_buffers` 160 MB in 384 MB cgroup | offen |
| AUD-2026-09-102 | Medium | **Medium** | WP-2 | NEU | — | `…/hermes-plugin.json:16` vs `src/activate.ts:60-75` | Deklarierte `contributes.commands`/`statusBarItems.command` werden nie registriert | offen |
| AUD-2026-09-106 | Medium | **Medium** | WP-2 | NEU | — | `integrations/hermes-agent-plugin/plugin.yaml:2`; `dashboard/manifest.json:6` | Python-Plugin-Version `0.1.0` statt `VERSION`; von `build_hermes_plugin.py` nicht erfasst | offen |
| AUD-2026-09-107 | Medium | **Medium** | WP-2 | NEU | CR-21 (Klasse) | `backend/mcp_server/protocol_handler.py:505`; `backend/mcp_server/views.py:431` | MCP `serverInfo.version` hart `1.0.0`, unabhängig von `VERSION` (live bestätigt) | offen |
| AUD-2026-09-111 | Medium | **Medium** | WP-2 | NEU | — | `integrations/hermes-agent-plugin/__init__.py:138` | `formalize` gibt rohes Response-Dict aus statt der Artefakt-ID (`artifact_id` existiert nicht) | offen |
| AUD-2026-09-112 | Medium | **Medium** | WP-2 | NEU | — | `integrations/hermes-agent-plugin/reqogniloom_client.py:54-60,197-204` | `/interviews/` hat kein `count` → `open interviews` dauerhaft `None`, ohne Diagnose | offen |
| AUD-2026-09-113 | Medium | **Medium** | WP-2 | NEU | — | `dist/plugins/*/reqogniloom/skills/interview-management/SKILL.md` + `dist/plugins/claude-code/reqogniloom/agents/*.md` | Mitgelieferter Skill ist unbenutzbar: alle 10 `interview.*`-Tools außerhalb jeder Rollen-Whitelist | offen |
| AUD-2026-09-118 | Medium | **Medium** | WP-2 | NEU | — | `…/src/state.ts:157-158` (+ `:101-118`)` | API-Key wird im Klartext in den Host-Storage geschrieben und ohne Ablauf wiederhergestellt | offen |
| AUD-2026-09-004 | **P2** | **Medium** | WP-3 | NEU | **BESTAETIGT #420, #925** (geschlossen) | `/settings` LLM-Tab` | Rohe i18n-Keys als sichtbare Abschnittstitel (`architecture_decompose_tree`, `bundle_compression`, `interview.grounding_rank`) | offen |
| AUD-2026-09-005 | **P2** | **Medium** | WP-3 | NEU | **BESTAETIGT #425, #741** (geschlossen) | `/system-settings` Design-Paletten` | 2 `combobox` ohne accessible name (Tenant-Standard) | offen |
| AUD-2026-09-006 | **P2** | **Medium** | WP-3 | NEU | — | `/profile` | ~190 API-Keys ungepaginiert, ohne Filter/Suche; Widerruf **ohne** Bestätigungsdialog | offen |
| AUD-2026-09-007 | **P2** | **Medium** | WP-3 | NEU | — | `SidebarNavigation.tsx:150-160` | 25 NavLinks ohne `data-testid`; nur über übersetzten Text selektierbar (derzeit durch `goto()` kaschiert) | offen |
| AUD-2026-09-008 | **P2** | **Medium** | WP-3 | NEU | **BESTAETIGT CR-40** (verwandt #449 ff.) | ``SidebarNavigation`` | Bei Deep-Link/Reload startet die Sidebar mittig; der aktive Nav-Eintrag ist außerhalb des Sichtbereichs | offen |
| AUD-2026-09-016 | **P2** | **Medium** | WP-3 | NEU | **BESTAETIGT #619** (geschlossen, **Ratchet unwirksam**) | `frontend/src/i18n/locales.test.ts` | i18n-Paritäts-Ratchet prüft Key-Menge, nicht Code→Locale-Nutzung ⇒ 112 maskierte Fehl-Keys unsichtbar | offen |
| AUD-2026-09-017 | **P2** | **Medium** | WP-3 | NEU | — | `e2e/tests/*` (54 Specs)` | Abdeckungslücken: `/attributes` 0 Specs; `/goals` `/workflows` `/audit` `/impact` `/glossary` nur generisch; `/interviews` nur Visual-Regression; i18n in 1 von 54 Specs | offen |
| AUD-2026-09-302 | P2 | **Medium** | WP-3b | NEU | CR-41 | `components/NeedsEditors/NeedsEditors.tsx:263` | 27 Count-Keys ohne Pluralform | offen |
| AUD-2026-09-303 | P2 | **Medium** | WP-3b | NEU | #619 | `i18n/locales/de.json:1` | 536 tote Locale-Keys (25,3 %) | offen |
| AUD-2026-09-304 | P2 | **Medium** | WP-3b | NEU | #619 | `components/RequirementEditors/RequirementList.tsx:247` | 76 dynamische Keys ungeprüft | offen |
| AUD-2026-09-305 | P2 | **Medium** | WP-3b | NEU | — | `api/requirements.ts:156` | 100-Seiten-Paginierungsschleife im Client | offen |
| AUD-2026-09-306 | P2 | **Medium** | WP-3b | NEU | CR-42 | `utils/asilUtils.ts:62` | 21 Hex-Literale in `.ts` außerhalb des Ratchets | offen |
| AUD-2026-09-307 | P2 | **Medium** | WP-3b | NEU | CR-43 | `api/memory.ts:277` | 7 Roh-`fetch()` ohne Refresh/Timeout/Fehlertyp | offen |
| AUD-2026-09-308 | P2 | **Medium** | WP-3b | NEU | CR-41/QUICK-05 | `components/TestRuns/TestRunsList.tsx:236` | Doppel-Autofokus `initialFocusRef` + `autoFocus` | offen |
| AUD-2026-09-309 | P2 | **Medium** | WP-3b | NEU | CR-31 | `components/UserProfileSettings/ApiKeysSection.tsx:224` | API-Key-Liste ohne Paginierung/Filter/Virtualisierung | offen |
| AUD-2026-09-310 | P2 | **Medium** | WP-3b | NEU | CR-31 | `e2e/tests/artifact-diff.spec.ts:95` | ≥6 verifiziert stale E2E-Selektoren (WP-3 widerlegt) | offen |
| AUD-2026-09-311 | P2 | **Medium** | WP-3b | NEU | CR-31 | `components/shared/ArtifactForm/ArtifactForm.tsx:1168` | 52 interaktive Elemente ohne TID (93,5 % Abdeckung) | offen |
| AUD-2026-09-324 | P2 (Querschnitt zu AUD-2026-09-058/187) | **Medium** | WP-3b | NEU | — | `api/llm-settings.ts:22` | `azure` fehlt bereits im TS-Union-Typ, nicht nur im ChoiceField | offen |
| AUD-2026-09-154 | Medium | **Medium** | WP-4 | NEU | — | `traceability/types.py:76`, `trace_link_manager.py:62-73`, `traceability/services.py:65,472` | `VALID_LINK_TYPES` als Nicht-Autorität deklariert, als API re-exportiert, im ReqIF-Import **benutzt** | offen |
| AUD-2026-09-155 | Medium | **Medium** | WP-4 | NEU | CR-09 (anderer Store) | ``lt_workspace_definition` (live)` | Orphan-Workspace mit 8 statt 11 Keys | offen |
| AUD-2026-09-157 | Medium | **Medium** | WP-4 | NEU | CR-15 (anderer Punkt) | `traceability/trace_link_manager.py:372-392` | Zyklusprüfung **pro** Link-Typ; Self-Link nirgends abgelehnt | offen |
| AUD-2026-09-163 | Medium | **Medium** | WP-4 | NEU | — | `live gemessen` | 0 Workspaces auf `minimal` → alle `minimal`-Zweige ungetestet | offen |
| AUD-2026-09-170 | Medium | **Medium** | WP-4 | NEU | — | `workflow/lifecycle_manager.py:416-477` | `force_transition` ohne Rolle/Signatur/Reason-Gate; 2 veraltete Docstrings | offen |
| AUD-2026-09-171 | Medium | **Medium** | WP-4 | NEU | — | ``we_item_state` (live)` | Kein `CHECK (current_state ∈ states(definition))`, kein FK auf `workspace_id` | offen |
| AUD-2026-09-172 | Medium | **Medium** | WP-4 | NEU | — | `workflow/definition_store.py:660-662`, `transition_validator.py:350-357` | `state_meta` modelliert nur `is_outdated_equivalent`, **keine** Terminal-Semantik | offen |
| AUD-2026-09-173 | Medium | **Medium** | WP-4 | NEU | — | `global`-Scope: 0 Snapshots live → Codepfad unverifiziert` | `global`-Scope: 0 Snapshots live → Codepfad unverifiziert | offen |
| AUD-2026-09-176 | Medium | **Medium** | WP-4 | NEU | **BESTAETIGT #1112** | `bootstrap_attribute_definitions.py:309, 1247-1252` | Ohne `--reset` wird `kind` **nie** geändert — **dreifach** gesperrt | offen |
| AUD-2026-09-177 | Medium | **Medium** | WP-4 | NEU | — | `attribute_definitions/schema.py:15` vs. `stage_matrix.py:48-53` | `ATTRIBUTE_KINDS` = 2 Werte, Docstring beschreibt 5 Carrier | offen |
| AUD-2026-09-178 | Medium | **Medium** | WP-4 | BLOCKED | — | `live gemessen` | 3/11 Item-Types materialisieren nie; 134/401 Workspaces ohne Attribut-Katalog | offen – BLOCKED |
| AUD-2026-09-179 | Medium | **Medium** | WP-4 | NEU | CR-10 (anderer Store) | `bootstrap_attribute_definitions.py:994-1034` | Kein `--dry-run`, kein Undo für einen destruktiven Befehl | offen |
| AUD-2026-09-183 | Medium | **Medium** | WP-4 | NEU | CR-36 (Nachbar) | `Migrationskette` | Kein Mechanismus erkennt „Datenmigration lief, Daten wurden zurückgesetzt" | offen |
| AUD-2026-09-184 | Medium | **Medium** | WP-4 | NEU | **BESTAETIGT (CR-17)** | `application/models.py:44,147,170,204`, `baseline/models.py:116` | 5 Modelle ohne `tenant_id` **und** ohne RLS (Vor-Audit nannte 2) | offen |
| AUD-2026-09-186 | Medium | **Medium** | WP-4 | NEU | — | `263 Verwendungen` | `.unscoped` gegen 0 Constraints an 5 zentralen Tabellen | offen |
| AUD-2026-09-187 | Medium | **Medium** | WP-4 | NEU | — | `search_service.py:183-250`, `attribute_definitions/schema.py:22`, `pl_artifact` | Drei parallele, auseinanderlaufende Entity-Typ-Registries (11 / 10 / 13) | offen |
| AUD-2026-09-328 | Medium | **Medium** | WP-4 | NEU | #1104 (verwandt) | `traceability/services.py:227`, `traceability/exceptions.py:19-24`, `trace_link_manager.py:356` | Link-Typ-Zahlen 6/8/10/11 im **Code** | offen |
| AUD-2026-09-194 | Medium | **Medium** | WP-5 | NEU | — | ``.woodpecker.yml`` | Zweites CI-System führt überhaupt kein `pytest` aus (nur `manage.py check`) | offen |
| AUD-2026-09-197 | Medium | **Medium** | WP-5 | NEU | — | `docs/se/reports/RELEASE_*.md`, `TESTPLAN_*.md` | 0 REQ-IDs in 11 Abnahmeberichten; keine Checkbox-Struktur | offen |
| AUD-2026-09-198 | Medium | **Medium** | WP-5 | NEU | CR-30 | `mcp_server/tests/test_e2e_sse_transport.py:349,353` | SSE-Live-Redis-Pfad in **jedem** CI-Lauf per `skipif` übersprungen | offen |
| AUD-2026-09-199 | Medium | **Medium** | WP-5 | NEU | — | `useNotificationFeed.test.ts:57` u. a.` | Bare-Global-`localStorage` in 4 FE-Testdateien → 65 umgebungsgekoppelte Fehlschläge | offen |
| AUD-2026-09-200 | Medium | **Medium** | WP-5 | NEU | — | `backend/rest_api/tests/test_llm_settings.py:248` | Test fixiert das abgeschaltete Anthropic-Modell als Erwartungswert | offen |
| AUD-2026-09-202 | Medium | **Medium** | WP-5 | NEU | CR-09 | `docs/se/**/*Requirements*.md` | 104 von 121 Requirement-Dokumenten ohne YAML-Frontmatter (Pflichtverstoß) | offen |
| AUD-2026-09-203 | Medium | **Medium** | WP-5 | NEU | — | `Matrix `:724,728` | 20 doppelt vergebene REQ-IDs; Marker „letzter gewinnt" = positionsabhängig | offen |
| AUD-2026-09-204 | Medium | **Medium** | WP-5 | NEU | — | `settings.py:822`, DB-Row live` | Parallelbefund „Archivierung nie registriert" **nicht reproduzierbar** | offen |
| AUD-2026-09-206 | Medium | **Medium** | WP-5 | NEU | — | ``AGENTS.md`` | APIView-/Tool-Zahlen im AGENTS.md weichen vom gemessenen Stand ab (durch WP-1 belegt) | offen |
| AUD-2026-09-332 | Medium | **Medium** | WP-5 | NEU | — | `traceability-matrix.md:721` | 15 als „nicht existent" gelistete IDs, die im Code referenziert werden | offen |
| AUD-2026-09-335 | Medium | **Medium** | WP-5 | NEU | — | ``ADR-001,-002,-003,-DS-02`` | 4 von 10 ADRs ohne YAML-Frontmatter | offen |
| AUD-2026-09-336 | Medium | **Medium** | WP-5 | NEU | — | `docs/se/ADR/` | 4 Dateinamen nicht konform (3× CamelCase, `ADR-DS-02` nicht 3-stellig) | offen |
| AUD-2026-09-337 | Medium | **Medium** | WP-5 | NEU | — | `Statuswerte `PROPOSED`/`ACCEPTED` verlassen das lowercase-Enum` | Statuswerte `PROPOSED`/`ACCEPTED` verlassen das lowercase-Enum | offen |
| AUD-2026-09-338 | Medium | **Medium** | WP-5 | NEU | — | `ADR-005…009` | Lifecycle-Sprung `proposed → accepted` ohne `review` (5×) | offen |
| AUD-2026-09-341 | Medium | **Medium** | WP-5 | NEU | — | `traceability-matrix.md:140,191,192` | 3 `Implemented`-REQ-L1 ohne jede L2-Zerlegung | offen |
| AUD-2026-09-226 | MEDIUM | **Medium** | WP-6a | NEU | — | `backend/reqogniloom/settings.py:143-160`, `INSTALLED_APPS:180-235`, `MIDDLEWARE:240-273` | `django-cors-headers` fehlt komplett â€” CORS-Settings sind tote Konfiguration | offen |
| AUD-2026-09-227 | MEDIUM | **Medium** | WP-6a | NEU | — | `Postgres `pg_class` (29/100 ohne RLS), u. a. `at_api_key`, `at_user_role`, `audit_entry`, `pl_user` | 29 Tabellen ohne RLS; Raw-SQL-Pfade sind dort unkontrolliert cross-tenant | offen |
| AUD-2026-09-228 | MEDIUM | **Medium** | WP-6a | NEU | — | `backend/persistence/models.py:501-524` (`User`, `UserManager`)` | `pl_user` global + unskopiert + ohne RLS â†’ Cross-Tenant-User-Lexikon auf DB-Ebene | offen |
| AUD-2026-09-229 | MEDIUM | **Medium** | WP-6a | NEU | — | `backend/rest_api/throttling.py:391,404-408` (kein `NUM_PROXIES` in `settings.py`)` | `get_ident()` = `REMOTE_ADDR`; hinter Proxy kollabieren alle IP-Buckets â†’ globaler Login-DoS | offen |
| AUD-2026-09-230 | MEDIUM | **Medium** | WP-6a | NEU | **CR-45 fÃ¼r diese Datei bestÃ¤tigt** | `.github/workflows/docker-publish.yml:134` | `${{ steps.meta.outputs.tags }}` direkt im `run:`-Block interpoliert | offen |
| AUD-2026-09-231 | MEDIUM | **Medium** | WP-6a | NEU | — | `backend/reqogniloom/settings.py:764` (unset), `backend/llm_adapter/token_tracking.py:233-243` | `TENANT_TOKEN_LIMIT_PER_DAY` unset + fail-open Budget-Gate | offen |
| AUD-2026-09-238 | MEDIUM | **Medium** | WP-6a | NEU | — | `backend/application/prompt_resolver.py:82-94`, `backend/application/ai_derivation_service.py:669-675,785-790,899-904` | Artefakt-Titel ungefiltert/ungekÃ¼rzt in LLM-Prompts; `render_template` ohne Delimitation | offen |
| AUD-2026-09-240 | MEDIUM | **Medium** | WP-6a | NEU | — | `Postgres `at_api_key`: 9 aktive Keys des `admin` | 9 aktive `admin`-Keys, **alle** ohne `expires_at` und **alle** ohne Workspace-Fence | offen |
| AUD-2026-09-271 | Medium | **Medium** | WP-6b | NEU | — | `baseline/version_reconstructor.py:191,210,227,244,295` | 5× `except Exception: pass` in der Entity-Probe ⇒ Artefakte verschwinden **still** aus rekonstruierten Baselines ⇒ falscher Diff | offen |
| AUD-2026-09-272 | Medium | **Medium** | WP-6b | NEU | — | `application/settings_service.py:661-663` | Preset-Tier still `None` bei jedem Fehler, **ohne Log** ⇒ Review-Policy fällt lautlos auf Default | offen |
| AUD-2026-09-273 | Medium | **Medium** | WP-6b | NEU | — | `application/attribute_migration_service.py:966-978` | Breiter `except` als Existenzprobe ⇒ Transient-Error liest Feld am **falschen Carrier** ⇒ falsche Migrationsdaten | offen |
| AUD-2026-09-274 | Medium | **Medium** | WP-6b | NEU | — | `mcp_server/tool_registry.py:1381,1411,1520` | 3 Fail-closed-Sites loggen auf `DEBUG`, das in Produktion hart abgeschaltet ist ⇒ DB-Ausfall ⇒ 403 für alle, **null Logzeilen** | offen |
| AUD-2026-09-275 | Medium | **Medium** | WP-6b | NEU | — | `reqogniloom/health.py:4` vs. `reqogniloom/urls.py:28` | Docstring verspricht `/health/ready` + `/health/live` — **beide existieren nicht**; Liveness/Readiness nicht trennbar | offen |
| AUD-2026-09-276 | Medium | **Medium** | WP-6b | NEU | — | `reqogniloom/settings.py:899-953` | Log-Level und Format hartkodiert, **keine** Env-Steuerung; Level je Umgebung nicht konfigurierbar | offen |
| AUD-2026-09-277 | Medium | **Medium** | WP-6b | NEU | CR-33 (Teil) · WP-6a **relativiert** | `repo-weit; `rest_api/metrics_views.py:29` | **Keine Telemetriemetriken existieren** (kein Prometheus/OTel). `/api/v1/metrics/` ist ein authentifizierter Domänen-Proxy, **kein** Scraper-Endpunkt | offen |
| AUD-2026-09-278 | Medium | **Medium** | WP-6b | BESTAETIGT | **#077 (bestätigt+verschärft)** | `rest_api/serializers.py:241-257`, `reqogniloom/middleware.py:42-91`, `audit/*` | Korrelations-ID endet nach dem Log — Fehlerkörper ohne ID, **kein `request_id` in Audit-Einträgen**, `trace_id` repo-weit 0 Treffer | offen |
| AUD-2026-09-283 | Medium | **Medium** | WP-6b | NEU | CR-06 (neu) · REQ-072 | `audit/writer.py:207`, `application/event_bus.py:314,477-479` | Outbox ist at-least-once, der **einzige** Abonnent ist nicht idempotent: nackter INSERT, `audit_entry` ohne `event_id` | offen |
| AUD-2026-09-284 | Medium | **Medium** | WP-6b | NEU | — | `application/tasks.py:31-38` | Outbox-Task verschluckt `Exception` und gibt `0` zurück ⇒ Celery verbucht **Erfolg**; live 222 863 Läufe, 0 Fehlschläge | offen |
| AUD-2026-09-285 | Medium | **Medium** | WP-6b | NEU | neu (Bereich #169) | `audit_entry` (live), `audit/writer.py:190-215` | `entity_version` in **97.7 %** von 8167 Audit-Zeilen `NULL`; `delete`/`transition`/`user.*` zu 100 % ⇒ Trail nennt keine resultierende Revision | offen |
| AUD-2026-09-286 | Medium | **Medium** | WP-6b | NEU | **#031/#129 (verschärft)** | `reqogniloom/health.py:100-315`, `admin_ops/health_rest.py:113-198`, `deploy/docker-compose.yml:642` | Orchestrator-Probe prüft 5 von 10 Abhängigkeiten; Redis/Worker/Beat/Outbox fehlen, während die **vollständige** Prüfung admin-authentifiziert existiert | offen |
| AUD-2026-09-287 | Medium | **Medium** | WP-6b | BESTAETIGT | **#074/#234 (bestätigt+quantifiziert)** | `audit/query.py:142-150` | Deep-Offset liest **4050** Zeilen für 50 (1,25 ms) + `COUNT(*)`-Seq-Scan pro Seitenaufruf (1,03 ms) — **komponiert mit #270** | offen |
| AUD-2026-09-045 | Low | **Low** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/protocol_handler.py:226-241` | `id: bool/array/object` akzeptiert und echoed (Spec: String/Number/null) | offen |
| AUD-2026-09-046 | Low | **Low** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/tools/generic.py:493`; `backend/application/glossary_service.py:166` | Falsch typisierte Felder ⇒ `AttributeError` ⇒ „internal error" statt Validierungsfehler | offen |
| AUD-2026-09-047 | Low | **Low** | WP-1a/1b/1d | NEU | — | `backend/application/glossary_service.py:166` | Keine Längenbegrenzung: 20 000-Zeichen-Strings werden persistiert | offen |
| AUD-2026-09-048 | Low | **Low** | WP-1a/1b/1d | NEU | **CR-30** | `backend/mcp_server/tests/test_tool_manifest_drift.py:83` | Guard im laufenden Stack nicht ausführbar (DB-Rolle ohne `CREATEDB`), obwohl `build_manifest()` keine DB braucht | offen |
| AUD-2026-09-088 | **Low** | **Low** | WP-1a/1b/1d | NEU | CR-26 | `live, `auth_tenancy/services/authentication.py` (Claim-Reihenfolge)` | Fehlercode-Granularität: abgelaufen, `aud`-fremd, `iss`-fremd und unbekannter `user_id` sind **nicht unterscheidbar** (alle `invalid_signature`) | offen |
| AUD-2026-09-089 | **Low** | **Low** | WP-1a/1b/1d | NEU | — | `rest_api/urls.py:263`, `reqogniloom/urls.py:51-52` | MCP-Server-Deskriptor auf `/mcp/` und `/api/v1/mcp/` **ohne Credential** öffentlich (Versions-Disclosure, MCP-Spec-konform) | offen |
| AUD-2026-09-090 | **Low** | **Low** | WP-1a/1b/1d | NEU | CR-12 | `GET /api/schema/` → `components.securitySchemes.cookieAuth` | `cookieAuth` (`sessionid`) ist deklariert, wird aber von **keiner** Operation referenziert — toter Auth-Pfad im Schema | offen |
| AUD-2026-09-091 | **Low** | **Low** | WP-1a/1b/1d | NEU | CR-12 | `GET /api/schema/` → `auth/login`, `auth/refresh`, `public/banners/login` | Öffentliche Endpunkte nutzen `security: [{BearerAuth: []}, {}]` statt des kanonischen `security: []` | offen |
| AUD-2026-09-092 | **Low** | **Low** | WP-1a/1b/1d | NEU | CR-42 | `live: `GET /requirements/?workspace_id=A` | `uid` ist bei ~888 vorbestehenden Seed-Artefakten `null` → ReqIF-Export schreibt `ATTR-UID THE-VALUE=""`; Backfill-Lücke nach `#932` (Issue) / `#1005` (PR) (nicht der `#1003`-Fix, der ist gemergt und wirksam) | offen |
| AUD-2026-09-140 | Low | **Low** | WP-1c | NEU | — | `testing/docker-compose.test.yml:54-56` | `depends_on` ohne `condition: service_healthy` | offen |
| AUD-2026-09-144 | Low | **Low** | WP-1c | NEU | **TEILWEISE** `CR-35` | ``EXPLAIN` auf `pl_artifact`; `pg_indexes`` | `created_at` unindiziert (Sort nötig), Composite-Index ungenutzt, 4 Duplikat-Indizes | offen |
| AUD-2026-09-145 | Low | **Low** | WP-1c | NEU | — | `Release-Compose `:887` `--concurrency=4` vs. live `concurrency: 2` | Worker-Konfiguration Release-Compose ≠ laufender Stack | offen |
| AUD-2026-09-146 | Low | **Low** | WP-1c | NEU | — | `backend/llm_adapter/tasks.py:188-189` vs. `settings.py:347` | Stale Kommentar: „CONN_MAX_AGE is unset (Default 0)" — tatsächlich 60 | offen |
| AUD-2026-09-148 | Low | **Low** | WP-1c | NEU | — | `deploy/docker-compose.yml:73,1020,1053` | Klartext-Default `honcho-dev-password` im Compose | offen |
| AUD-2026-09-103 | Low | **Low** | WP-2 | NEU | — | `…/hermes-plugin.json:40-46` | `engines.hermes` und `permissions` werden von keinem Code gelesen — dekorativ | offen |
| AUD-2026-09-104 | Low | **Low** | WP-2 | NEU | — | `…/hermes-plugin.json` (gesamtes Dokument)` | Kein `capabilities`/`tools`/`minHostVersion`-Feld; deklarierte Oberfläche nur im Quelltext | offen |
| AUD-2026-09-105 | Low | **Low** | WP-2 | NEU | — | `…/hermes-plugin.json` (kein `auth`-Feld)` | Keine Auth-Spezifikation im Manifest; Tokenquelle rein implizit (UI-Formular) | offen |
| AUD-2026-09-108 | Low | **Low** | WP-2 | NEU | — | `backend/reqogniloom/version.py:78-105` | `GET /api/v1/version/` liefert live `{"app_version":"unknown"}` — Version zur Laufzeit nicht verifizierbar | offen |
| AUD-2026-09-116 | Low | **Low** | WP-2 | NEU | — | `…/src/state.ts:140`; `api.ts:113` | Timeout (exakt 15005 ms) und Connection-Refused ergeben dieselbe Meldung „Connection failed."; keine Diagnose, kein Log | offen |
| AUD-2026-09-119 | Low | **Low** | WP-2 | NEU | — | `integrations/hermes-agent-plugin/reqogniloom_client.py:95` vs `docs/agent-templates/INSTALL.md:130-158` | Undokumentierte zweite Auth-Konvention (`Bearer reqlo_…`) neben `X-API-Key` | offen |
| AUD-2026-09-009 | **P3** | **Low** | WP-3 | NEU | — | `/requirements` Zeile; `RequirementTreeNode.module.css` | Datum visuell auf „27.9.202" abgeschnitten (DOM korrekt `27.9.2026`) ⇒ irreführende Datumsanzeige | offen |
| AUD-2026-09-010 | **P3** | **Low** | WP-3 | NEU | **BESTAETIGT CR-41/FEA-009** (verwandt #986, #595, geschlossen) | `/settings` | „Save" (EN) und „Speichern" (DE) auf **derselben** Seite | offen |
| AUD-2026-09-011 | **P3** | **Low** | WP-3 | NEU | NEU (verwandt #453, #690, geschlossen) | `/test-runs` | Status-Badge rendert unmaskiertes Enum `Failed` neben deutschen Filter-Labels | offen |
| AUD-2026-09-012 | **P3** | **Low** | WP-3 | NEU | **BESTAETIGT #420-Klasse** (geschlossen) | `de.json:752` | „Probleme erfassen Defekte, Verbesserungen …" — fehlender Doppelpunkt | offen |
| AUD-2026-09-013 | **P3** | **Low** | WP-3 | NEU | — | `de.json:952, 968, 2110, 2120` | Denglish „User" in deutschen Sätzen (4 Stellen) | offen |
| AUD-2026-09-014 | **P3** | **Low** | WP-3 | NEU | **BESTAETIGT CR-31** (verwandt #692, geschlossen) | `/test-runs` | Route hängt ~10 s im Vollbild-„Laden…"; Ursache: Workspace-Pagination (5 Seiten) blockiert den Workspace-Kontext | offen |
| AUD-2026-09-015 | **P3** | **Low** | WP-3 | NEU | **BESTAETIGT #692** (geschlossen, **reproduziert**) | `/test-runs`, `/traceability` | Loading-Stall > 10 s — die als „flaky" markierte Ursache ist deterministisch und skaliert mit der Workspace-Anzahl | offen |
| AUD-2026-09-018 | **P3** | **Low** | WP-3 | BESTAETIGT | — | `/workflows` (React Flow)` | Attribution entfernt ohne Pro-Abo ⇒ Lizenz-/Compliance-Risiko (Console-Warnung bestätigt) | offen |
| AUD-2026-09-019 | P3 | **Low** | WP-3 | NEU | — | `/settings`, `/system-settings` | `prefers-color-scheme` wird nicht ausgewertet (nur App-Toggle) — bewusste Entscheidung, aber ohne Dokumentation | offen |
| AUD-2026-09-020 | P3 | **Low** | WP-3 | NEU | **BESTAETIGT #1096** (**OFFEN**) | `/profile` | „Sichtbarkeit lesbarer IDs" persistiert nur lokal; die UI nennt die fehlende Server-Persistenz selbst | offen |
| AUD-2026-09-021 | P3 | **Low** | WP-3 | WIDERLEGT | Design-Token-Disziplin: 0 harte Hex-Werte, 0 Inline-Styles ⇒ #674/#876 wirksam | `frontend/src/styles/*` | Design-Token-Disziplin: 0 harte Hex-Werte, 0 Inline-Styles ⇒ #674/#876 wirksam | geschlossen (WIDERLEGT) |
| AUD-2026-09-022 | P3 | **Low** | WP-3 | WIDERLEGT | — | `/login`, `/requirements` Dialog` | Auth- und Dialog-Fokuspfade vollständig konform | geschlossen (WIDERLEGT) |
| AUD-2026-09-312 | P3 | **Low** | WP-3b | NEU | CR-31 | `components/shared/CustomFieldsEditor.tsx` | 4 datei-lokale TID-Dubletten | offen |
| AUD-2026-09-313 | P3 | **Low** | WP-3b | NEU | CR-42 | `frontend/src/test/ui-ratchet.test.ts:747` | `STYLE_BRACE_BASELINE=3` ist reines Kommentar-Rauschen | offen |
| AUD-2026-09-314 | P3 | **Low** | WP-3b | NEU | CR-42 | `frontend/src/test/ui-ratchet.test.ts:955` | Hex-Baseline 17/3 um 1 Fehlpositiv zu hoch | offen |
| AUD-2026-09-315 | P3 | **Low** | WP-3b | NEU | CR-42 | `components/NavigationShell/ErrorBoundary.tsx:45` | Nur 1 Boundary, nur `console.error`, keine Telemetrie | offen |
| AUD-2026-09-316 | P3 | **Low** | WP-3b | NEU | CR-41 | `components/shared/ArtifactRow/ArtifactRow.tsx:198` | `<span onClick>` ohne Rolle/Tabindex (1× im Baum) | offen |
| AUD-2026-09-317 | P3 | **Low** | WP-3b | NEU | CR-41 | `components/AttributeEditor/AttributeCatalogDialog.tsx:157` | 7 weitere `autoFocus` trotz `initialFocusRef`-API | offen |
| AUD-2026-09-318 | P3 | **Low** | WP-3b | NEU | CR-31 | `frontend/src/test/` (fehlt)` | Kein Test für TID↔e2e-Selektor-Drift | offen |
| AUD-2026-09-319 | P3 | **Low** | WP-3b | NEU | #954/#797 | `frontend/src/test/design-system-ratchet.baseline.json:6` | 324 Buttons ohne `btn-*`-Klasse eingefroren | offen |
| AUD-2026-09-320 | P3 | **Low** | WP-3b | NEU | — | `frontend/package.json:31` | Doku-Drift React 18 vs. 19 im Manifest | offen |
| AUD-2026-09-321 | P3 | **Low** | WP-3b | NEU | — | `frontend/src` (44 Stellen)` | 44 `console.*` in Produktion | offen |
| AUD-2026-09-322 | P3 | **Low** | WP-3b | NEU | #619 | `components/BaselinesView/BaselinesPanels.tsx:425` | `baselines.fieldChangesCount` fehlt komplett + Plural | offen |
| AUD-2026-09-323 | P3 | **Low** | WP-3b | NEU | CR-43 | `components/RequirementEditors/useRequirementData.ts:51` | 0 `useReducer`, 326 `useEffect` — Update-Pfade verstreut | offen |
| AUD-2026-09-156 | Low | **Low** | WP-4 | NEU | — | `link_types/migrations/0008_…py:83` | Datenmigration ohne Re-Run; 401 statt 402 | offen |
| AUD-2026-09-164 | Low | **Low** | WP-4 | NEU | #940 (geschlossen) | `attribute_definitions/stage_matrix.py:40-44` | Docstring zitiert **geschlossenes** Issue #940 als offenen Blocker | offen |
| AUD-2026-09-175 | Low | **Low** | WP-4 | NEU | — | `presets/registry.py:129` | `known_scopes` = 2. hartkodierte Scope-Liste neben `PresetConfig` | offen |
| AUD-2026-09-182 | Low | **Low** | WP-4 | NEU | — | ``pl_tracelink` (live)` | `link_type` ohne CHECK an den Katalog gebunden | offen |
| AUD-2026-09-189 | Low | **Low** | WP-4 | NEU | #801 (Nachbar) | `frontend/src/utils/artifactRoutes.ts:31` | Getaggte `TestCase:*` haben keinen Frontend-Router | offen |
| AUD-2026-09-205 | Low | **Low** | WP-5 | BLOCKED | — | `admin_ops/health_rest.py:72,434,459` | Health-Aggregation statisch nicht entscheidbar → Messung an laufendem Stack nötig | offen – BLOCKED |
| AUD-2026-09-232 | LOW | **Low** | WP-6a | NEU | — | `GET /api/schema/`, `GET /api/v1/schema/`, `GET /api/v1/version/` | 613 KB OpenAPI-Schema + Commit-SHA unauthentifiziert | offen |
| AUD-2026-09-233 | LOW | **Low** | WP-6a | NEU | — | `backend/rest_api/auth_views.py:329` | Deprecated Login-Body-Token standardmÃ¤ÃŸig aktiv â†’ vergrÃ¶ÃŸerte XSS-Kette | offen |
| AUD-2026-09-234 | LOW | **Low** | WP-6a | NEU | — | `backend/rest_api/serializers.py` (`StandardPagination`)` | `page_size`/`limit` Ã¼ber `max_page_size` â†’ 404 statt 400 | offen |
| AUD-2026-09-235 | LOW | **Low** | WP-6a | NEU | — | `Response-Header `Server: uvicorn` (live verifiziert)` | Server-Banner nicht unterdrÃ¼ckt | offen |
| AUD-2026-09-236 | LOW | **Low** | WP-6a | NEU | Issue **#845** verwandt | `.env`: `AUTH_COOKIE_SECURE=False`, `DJANGO_ENV=development` | Auth-Cookies im laufenden Stack unverschlÃ¼sselt; wird bei Prod-Promotion still Ã¼bernommen | offen |
| AUD-2026-09-237 | LOW | **Low** | WP-6a | NEU | — | `rest_framework.routers.APIRootView` an `/api/v1/` | Ã–ffentlicher API-Root enumeriert die Router-Routen | offen |
| AUD-2026-09-241 | LOW | **Low** | WP-6a | NEU | — | `deploy/verify-backup-command.sh:90,103`; `deploy/docker-compose.yml:73,1053` | Hardcoded PasswÃ¶rter in getrackten Deploy-Dateien (Wegwerf-Container bzw. Rollenname als Default) | offen |
| AUD-2026-09-279 | Low | **Low** | WP-6b | NEU | — | `workflow/signature_gate.py:156-157` | Infra-Fehler ist vom falschen Passwort nicht unterscheidbar; kein Log (ADR-konform, aber ohne Telemetrie) | offen |
| AUD-2026-09-280 | Low | **Low** | WP-6b | NEU | — | `rest_api/icd_views.py:274`, `mcp_server/tools/base.py:148,167`, `rest_api/mixins/workflow_transitions.py:281` | `TenantContextNotSetError → {}` maskiert Tenant-Context-Fehlkonfiguration vollständig | offen |
| AUD-2026-09-288 | Low | **Low** | WP-6b | NEU | **PERF-001/003**, CR-33/CR-35 | ``pg_stat_user_tables` (live)` | Zähler sind **nur seit Postmaster-Start** (21,5 h) und `n_live_tup` ist bis zum nächsten `VACUUM` bedeutungslos ⇒ N+1-Hypothesen ohne tragfähige Evidenzbasis | offen |
| AUD-2026-09-049 | Info | **Info** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/views.py:311-325` vs. `rest_api` 404-Handler` | `/mcp/`-404 ist HTML, `/api/v1/mcp/`-404 ist JSON | offen |
| AUD-2026-09-050 | Info | **Info** | WP-1a/1b/1d | WIDERLEGT | — | `Verdachtiger Cross-Tenant-Leak via `workspace.list`/`artifact.search` — Ursache war ein User in Tenant A; Isolation 65/65 sauber` | Verdachtiger Cross-Tenant-Leak via `workspace.list`/`artifact.search` — Ursache war ein User in Tenant A; Isolation 65/65 sauber | geschlossen (WIDERLEGT) |
| AUD-2026-09-051 | Info | **Info** | WP-1a/1b/1d | NEU | — | `backend/mcp_server/tests/test_tool_manifest_drift.py` | Manifest-Guard besteht 12/12 Mutationen inkl. falscher Tool-Beschreibung | offen |
| AUD-2026-09-067 | Info | **Info** | WP-1a/1b/1d | NEU | CR-20 | `backend/llm_adapter/audit_logger.py:174-191` | Circuit-Breaker außerhalb eines Tenant-Kontexts still deaktiviert (`_NullCircuitBreaker`) — kein Produktpfad, aber Management-Commands/Tests ungeschützt | offen |
| AUD-2026-09-093 | **Info** | **Info** | WP-1a/1b/1d | NEU | CR-13 | `live: 6 Workspace-Endpunkte` | Zwei 404-Texte unterscheiden „gehört fremdem Tenant" **nicht** von „existiert nicht" (`Workspace <id> not found.` vs. `… in the caller's tenant.`) — kein vollständiges Enumerations-Orakel, aber inkonsistent | offen |
| AUD-2026-09-150 | Info | **Info** | WP-2 | NEU | CR-25 | `deploy/docker-compose.yml:1325`; `.env.example:511,515` | Bluepencil registriert + Sidecar läuft gesund; es fehlt **nur** `VITE_BLUEPENCIL_ENABLED=1` | offen |
| AUD-2026-09-151 | Info | **Info** | WP-2 | NEU | CR-25 | `deploy/bluepencil` (live `/notes`)` | `GET /bluepencil/api/notes` liefert ohne Credential 200 mit Notizen aller Workspaces | offen |
| AUD-2026-09-152 | Info | **Info** | WP-2 | WIDERLEGT | CR-24 | `integrations/hermes-plugin/`, `integrations/hermes-agent-plugin/` | „nicht live verifizierte Verträge" ist überholt — beide **sind** live verifizierbar; je einer bricht | geschlossen (WIDERLEGT) |
| AUD-2026-09-153 | Info | **Info** | WP-2 | NEU | — | `dist/plugins/hermes/` | Verzeichnis enthält nur Builder + Test, kein Plugin-Artefakt; im Repo nirgends aufgelöst | offen |
| AUD-2026-09-023 | — | **Info** | WP-3 | BLOCKED | — | `/system-settings` Workspace löschen` | Bestätigungsdialog **nicht verifizierbar** (kein sicherer Trigger ohne Datenverlust) | offen – BLOCKED |
| AUD-2026-09-024 | — | **Info** | WP-3 | BLOCKED | — | `Diagrammeditoren, Create-Dialoge, Baseline-Compare` | **NICHT VERIFIZIERBAR**: Workspace enthält 0 Datensätze dieser Typen | offen – BLOCKED |
| AUD-2026-09-025 | — | **Info** | WP-3 | BLOCKED | — | `Tastaturkontrast, `prefers-reduced-motion`` | Keine Axe-Messung / keine Animation im Testfenster auslösbar | offen – BLOCKED |
| AUD-2026-09-158 | Info | **Info** | WP-4 | **PASS** → Kontrolle | — | `live gemessen` | 4 von 11 Link-Typen haben 0 Links (PASS-Kontext) | Kontrolle bestätigt |
| AUD-2026-09-159 | Info | **Info** | WP-4 | **PASS** → Kontrolle | — | `4-Ebenen-Matrix` | Primärkatalog auf DB/REST/MCP/FE konsistent offen | Kontrolle bestätigt |
| AUD-2026-09-165 | Info | **Info** | WP-4 | **PASS** → Kontrolle | — | `live GET` | Presetwechsel auf Workflow-Achse nachweisbar wirksam (1/5/9 Transitions) | Kontrolle bestätigt |
| AUD-2026-09-166 | — | **Info** | WP-4 | WIDERLEGT | **WIDERLEGT (CR-08)** | `workflow/services.py:302-341`, `lifecycle_manager.py:246-289,354` | Transition validiert **nach** dem Lock — Race behoben | geschlossen (WIDERLEGT) |
| AUD-2026-09-174 | Info | **Info** | WP-4 | **PASS** → Kontrolle | — | `live gemessen` | Scope-Trennung tenant-seitig sauber; 0 Cross-Tenant/Cross-WS TraceLinks | Kontrolle bestätigt |
| AUD-2026-09-185 | Info | **Info** | WP-4 | **PASS** → Kontrolle | — | `29/31 `pl_*`-Tabellen mit RLS; **0** `.raw()` im Produktions-Backend` | 29/31 `pl_*`-Tabellen mit RLS; **0** `.raw()` im Produktions-Backend | Kontrolle bestätigt |
| AUD-2026-09-188 | Info | **Info** | WP-4 | NEU | — | `99 `TestCase:*`-Tags = 3,2 % des Artefaktbestands` | 99 `TestCase:*`-Tags = 3,2 % des Artefaktbestands | offen |
| AUD-2026-09-190 | — | **Info** | WP-4 | BLOCKED | CR-16 (Nachbar) | `baseline/diff_engine.py:109-177` | Diff-Engine-Korrektheit ohne Mutation nicht messbar — **kein PASS** | offen – BLOCKED |


## 4. Nicht-vereinheitlichte Felder — was bewusst **nicht** angeglichen wurde

| Feld | Warum nicht vereinheitlicht |
|---|---|
| **Tabellen-Layout** | 5 unterschiedliche Header-Zeilen (`ID \| Sev \| Klasse \| Ort \| Kurztitel`, `\| ID \| Schweregrad \| Klassifikation \| CR-Track \| Ort \| Kurztitel`, `…`). Layout ist kein Konsistenzmangel, sondern Stil des WP-Agents. |
| **Kurztitel-Länge** | variiert von 40 bis 160 Zeichen; Kürzung würde Substanz verlieren. |
| **CVSS-Spalte (WP-6a)** | nur dort vorhanden; nicht in die Master-Tabelle projiziert. |
| **Mojibake-Anzeige** | reine Anzeige-Artefakte des Grep/Console-Toolings. Dateien sind valides UTF-8 (verifiziert: 0 Replacement-Char, 0 Decode-Fehler). **Keine Kodierungsreparatur nötig oder durchgeführt.** |

---

## 5. Volltext-Detailabschnitte — Critical und High

**90 Findings** (14 Critical + 76 High). Für Medium/Low/Info genügt die Zeile in §3
mit Verweis auf den WP-Report.

Die Felder *Reichweite*, *Evidenz*, *betroffene REQ-ID* und *Status* sind hier
ausgefüllt. *Reproduktionsschritte, Auswirkung und Empfehlung* stehen voll
ausformuliert im jeweiligen WP-Report — sie werden hier **nicht neu erfunden**,
sondern referenziert.

---

#### AUD-2026-09-030 — Redis-Ausfall hängt alle 13 MCP-Endpoints unbegrenzt (kein Timeout)

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/reqogniloom/settings.py:879`; `backend/mcp_server/views.py:272`; `backend/mcp_server/throttling.py:164` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:277 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-031 — `/health/` meldet „ok", während App+Auth+Schema unbenutzbar hängen

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/reqogniloom/health.py:118-190` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:278 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-052 — Anthropic-Default `claude-3-opus-20240229` ist seit 2026-01-05 retired — jeder Aufruf ohne `LLM_MODEL` schlägt fehl

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | **BESTAETIGT** (CR-20-Nachbar; #118) |
| **Ort (Reichweite)** | `backend/llm_adapter/providers.py:1080` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1222 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-070 — CSV-Round-Trip des eigenen Exporters unbrauchbar: `# terminology_profile`-Kommentarzeile wird als Header gelesen → **HTTP 201 `success:true` bei 0 importierten Zeilen**

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-11, CR-42, CR-12 |
| **Ort (Reichweite)** | `application/import_service.py:196-232` ↔ `views.py:8085` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:913 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-071 — ReqIF-Import liefert `success:true` mit 915 × „internal error"; Ursache `pl_artifact_pkey`-UniqueViolation, weil `SPEC-OBJECT/@IDENTIFIER` die globale `Artifact.id` ist

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-11, CR-42 |
| **Ort (Reichweite)** | `application/reqif_import_service.py:697`, `:681`, `:415` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:914 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-120 — Alle 4 Queues identisch gebunden → **jede Task läuft 4×**

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **NEU** (kein Vor-Audit-Track; CR-35-Nähe) |
| **Ort (Reichweite)** | `backend/reqogniloom/celery.py:31-36` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:42 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-121 — Beat dispatcht **nie** — gesamter 5-s/60-s/Monats-Schedule tot

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **BESTAETIGT** Klasse #171 (geschlossen 2026-07-29, Wirkung besteht fort) |
| **Ort (Reichweite)** | `Live: `celery-beat`-Log 0× `Sending due task`; `settings.py:817-830` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:43 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-122 — `backup.sh` ist permanent nicht ausführbar (`exit 1`)

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **NEU** (CR-37) |
| **Ort (Reichweite)** | `scripts/backup.sh:84-87` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:44 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-123 — Backup-Datei wird nie in den Container kopiert; `psql -f` liest Datei statt stdin

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **NEU** (CR-37) |
| **Ort (Reichweite)** | `scripts/restore.sh:183,186,198-213` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:45 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-115 — `_handle_slash` wirft `TypeError` — dokumentiert „never raises"; `start`/`status`/`answer` brechen live

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**Critical**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-2 · Report `AUDIT_NATIVE_PLUGINS.md` · Agent senior-developer |
| **CR-Track / Issue** | — (CR-24 verwandt) |
| **Ort (Reichweite)** | `integrations/hermes-agent-plugin/__init__.py:79` (via `:110,:120,:127`)` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_NATIVE_PLUGINS.md`:86 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_NATIVE_PLUGINS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-345 — Backup/Restore als `Implemented/Covered`, Restore-Skript nie im Image

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `Critical` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `matrix:331`, `backend/Dockerfile:154` |
| **Betroffene REQ-ID** | `REQ-L1-046` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:427 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-346 — Default-Modell `claude-3-opus-20240229` abgeschaltet; jeder Anthropic-Call scheitert

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `Critical` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/llm_adapter/providers.py:1080` |
| **Betroffene REQ-ID** | `REQ-L1-013` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:428 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-220 — Live `reqlo_`-API-Key im Klartext committet â€” **Key widerrufen 2026-09-30, Arbeitsbaum redigiert, Historie offen**

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**CRITICAL** âš ï¸*` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6a · Report `AUDIT_SECURITY.md` · Agent security-auditor |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2246` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_SECURITY.md`:44 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_SECURITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | TEILWEISE BEHOBEN |

#### AUD-2026-09-221 — Unauthentifizierter Rate-Limit-Check vor AuthN + Cache ohne `SOCKET_TIMEOUT` = DoS-VerstÃ¤rker

| Feld | Wert |
|---|---|
| **Schweregrad** | Critical — Originalwert `**CRITICAL**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6a · Report `AUDIT_SECURITY.md` · Agent security-auditor |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/mcp_server/views.py:272` + `backend/reqogniloom/settings.py:879-884` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_SECURITY.md`:45 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_SECURITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-032 — Zwei inkompatible Fehler-Hüllen (`code` int vs. `error_code` str) auf demselben Endpunkt

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | **CR-22** |
| **Ort (Reichweite)** | `backend/mcp_server/views.py:291-304` vs. `:311-325` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:283 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-033 — Nicht-dict `params` ⇒ HTTP 500 statt `-32600`/`-32602` (AttributeError außerhalb jedes try)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/mcp_server/protocol_handler.py:536` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:279 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-034 — `create_api_key` persistiert beliebige Scope-Strings für User-Keys; Key ist stumm schreibunfähig

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/auth_tenancy/services/authentication.py:616` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:280 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-035 — `ApiKey.tenant_id` ist dekorativ — `validate_api_key` nutzt `api_key.user.tenant_id`

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/auth_tenancy/services/authentication.py:562` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:281 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-036 — Domänen-`ValidationError`/`NotFoundError` als „internal error" maskiert; REST mappt dieselbe Exception auf 400

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/mcp_server/tools/generic.py:512-515` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:282 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-053 — OpenAI-Default `gpt-4` → Alias `gpt-4-0613`, API-Shutdown 2026-10-23; `.env.example:184,189` nennt ebenfalls retired Modelle

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-20 |
| **Ort (Reichweite)** | `backend/llm_adapter/providers.py:1333` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1223 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-055 — SDK-eigenes `max_retries=2` läuft zusätzlich zum 4er-`PolicyEngine`-Loop → **12 HTTP-Requests** pro logischem Aufruf bei 429/5xx

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-20 |
| **Ort (Reichweite)** | `backend/llm_adapter/providers.py:1100,1347,1689` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1225 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-057 — `decompose_requirement` nutzt nackten `json.loads` in allen 5 HTTP-Providern → `JSONDecodeError` mit Roh-Parsertext durch `get_task_status` ins Client

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | #576 (teilgewirkt) |
| **Ort (Reichweite)** | `backend/llm_adapter/providers.py:1215,1407,1595,1749,1941` + `dispatcher.py:187-193` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1227 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-058 — `azure` implementiert und in Doku beworben, aber in DB-Enum, REST-ChoiceField und UI-Liste **nicht wählbar**

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-12/CR-42 (Vertragsdrift) |
| **Ort (Reichweite)** | `backend/llm_adapter/providers.py:1663,2014` vs. `models.py:2411`, `llm-settings.ts:24` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1228 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-061 — Mock liefert 4 feste Token-Konstanten (42/100/200/120), prompt-unabhängig, die als exakte API-Nutzung in Budget + Aggregation einfließen

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-20 |
| **Ort (Reichweite)** | `backend/llm_adapter/providers.py:390,413,438,455` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1231 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-062 — Gesamtsumme wird als `input_tokens` gebucht, `output_tokens` ist konstruktionsbedingt 0 → keine Kosten-Attribution nach Modell/Provider

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-20 |
| **Ort (Reichweite)** | `backend/llm_adapter/router.py:286-292` + `tasks.py:166-172` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1232 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-066 — Ausgefallener Celery-Worker ist für den Aufrufer nicht von „läuft noch" unterscheidbar — `pending` ohne ETA/Ablauf

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-36 (Nachbar) |
| **Ort (Reichweite)** | `backend/llm_adapter/dispatcher.py:149-152,177-178` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:1236 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-072 — CSV-Import **nicht idempotent**: dreifacher Import derselben Datei erzeugt 3 Duplikate; keine Duplikaterkennung

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-11 |
| **Ort (Reichweite)** | `live `POST /workspaces/B/import/csv/` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:915 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-073 — **HTTP 500** auf ungültiges `page` (5 Werte je Endpunkt), während `/workspaces/` korrekt 404 liefert

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-14 |
| **Ort (Reichweite)** | `live `GET /trace-links/?page=0\/abc\/99999999`, `GET /glossary/?page=0\/abc` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:916 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-074 — 4 Listen-Endpunkte ohne Pagination: `/api-keys/` (200 Items, 54 KB), `/users/`, `/link-type-defaults/`, `workspaces/{id}/link-type-definitions/`; `page`/`page_size` werden komplett ignoriert

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-11 |
| **Ort (Reichweite)** | `rest_api/api_key_views.py:81`, `user_management_views.py:81`, `link_type_views.py:90` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:917 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-075 — **432 von 439 Operationen deklarieren keinen Fehler-Fall**, 0 deklarieren 5xx; `COMMON_ERROR_RESPONSES` ist tote Deklaration (nirgends verwendet)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-12, CR-21 |
| **Ort (Reichweite)** | `rest_api/openapi.py:71-98`; `GET /api/schema/` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:918 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-076 — ReqIF-Export ist **nicht ReqIF-1.2-konform**: `REQ-IF-HEADER/@reqIFVersion` fehlt, `THE-VERSION` fehlt, 0 von 915 `SPEC-OBJECT` enthalten das Pflicht-Element `SPEC-OBJECT-CONTENT`

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-11, CR-42 |
| **Ort (Reichweite)** | `application/reqif_export_service.py:296` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:919 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-077 — Fehlerhülle enthält **kein `trace_id`/`request_id`**, obwohl die App durchgängig eine `request_id` loggt — 500er sind für Clients nicht korrelierbar

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-11 |
| **Ort (Reichweite)** | `rest_api/error_envelope.py:48-68` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:920 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-078 — ReqIF-Import akzeptiert nur `multipart/form-data`; Export liefert `application/xml` — asymmetrisch und im OpenAPI-Schema **ohne** `requestBody` dokumentiert

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1a/1b/1d · Report `AUDIT_EXTERNAL_INTEGRATIONS.md` · Agent senior-developer (WP-1a/1b) · api-specialist (WP-1d) |
| **CR-Track / Issue** | CR-12 |
| **Ort (Reichweite)** | `views.py:8176-8216` (Export) vs. `ReqifImportView` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_EXTERNAL_INTEGRATIONS.md`:921 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_EXTERNAL_INTEGRATIONS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-124 — Format-/Ort-Inkompatibilität: `.sql.gz` im Volume vs. `*.dump\/*.sql` in `./backups`

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **NEU** (CR-37) |
| **Ort (Reichweite)** | `scripts/restore.sh:49,116` vs. `deploy/docker-compose.yml:372` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:46 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-125 — `audit.archive_lifecycle_manager` beim Worker **nicht registriert**

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/audit/archive.py:448` vs. `celery.py:45` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:47 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-126 — pre-ack + kein Retry ⇒ Worker-Kill = **endgültiger** Task-Verlust

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **NEU** (kein Vor-Audit-Track; CR-35-Nähe) |
| **Ort (Reichweite)** | `live `app.conf.task_acks_late=False`; 7 Task-Dateien` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:48 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-127 — Restore nicht atomar (`--clean --if-exists` in-place auf der Live-DB)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **NEU** (CR-37) |
| **Ort (Reichweite)** | `scripts/restore.sh:183` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:49 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-128 — 42-h-Horizont, kein Off-Host, keine Verschlüsselung, keine Medien/Uploads

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **NEU** (CR-37) |
| **Ort (Reichweite)** | `deploy/docker-compose.yml:357,361,372` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:50 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-129 — `/health/` prüft weder Cache **noch Worker/Beat**; `degraded` liefert HTTP **200**

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/reqogniloom/health.py:118-313`; `deploy/docker-compose.yml:642` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:51 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-137 — Kein Test-vor-Image-Vertrag; Scan≠Push-Artefakt; **kein** SBOM/Cosign/Provenance

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | **BESTAETIGT** `CR-32`, `CR-38` |
| **Ort (Reichweite)** | `.github/workflows/docker-publish.yml:102,145,168,183`; `ci.yml:4-7` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:59 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-149 — **Keine Staging-Stufe** zwischen CI und Produktion; keine Approval-Gate

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-1c · Report `AUDIT_INFRASTRUCTURE.md` · Agent devops-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `keine Staging-Definition; `ci.yml`/`docker-publish.yml` 0× `environment:`/`concurrency:` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_INFRASTRUCTURE.md`:71 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_INFRASTRUCTURE.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-100 — `main: dist/plugin.js` ist gitignored; Hermes-Installation komplett undokumentiert

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-2 · Report `AUDIT_NATIVE_PLUGINS.md` · Agent senior-developer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:7` + `.gitignore:2` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_NATIVE_PLUGINS.md`:87 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_NATIVE_PLUGINS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-101 — Manifest ist VS-Code-Schema, nicht der Hermes-`manifest.json {name, api}`-Vertrag

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-2 · Report `AUDIT_NATIVE_PLUGINS.md` · Agent senior-developer |
| **CR-Track / Issue** | CR-24 |
| **Ort (Reichweite)** | `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:8-46` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_NATIVE_PLUGINS.md`:88 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_NATIVE_PLUGINS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-109 — Beide Plugins lesen nur `results[]`, ignorieren `next` → Ziel-Workspace live unerreichbar (25 von 401)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-2 · Report `AUDIT_NATIVE_PLUGINS.md` · Agent senior-developer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `…/src/api.ts:143-153`; `integrations/hermes-agent-plugin/reqogniloom_client.py:136-139` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_NATIVE_PLUGINS.md`:89 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_NATIVE_PLUGINS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-110 — Hilfetext-Beispiel `start requirement` wird live mit 400 abgelehnt (nur PascalCase gültig)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-2 · Report `AUDIT_NATIVE_PLUGINS.md` · Agent senior-developer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `integrations/hermes-agent-plugin/__init__.py:62,105-107` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_NATIVE_PLUGINS.md`:90 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_NATIVE_PLUGINS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-114 — 210 grüne Tests, zwei Live-Bugs: Fixtures kodieren einen Vertrag, den der Server nicht erfüllt

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-2 · Report `AUDIT_NATIVE_PLUGINS.md` · Agent senior-developer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `…/__tests__/api.test.ts:8-9,31,42-43,62-63`; `…/tests/test_slash_command.py:40` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_NATIVE_PLUGINS.md`:91 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_NATIVE_PLUGINS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-117 — MCP-Fehler wird nie angezeigt — `interviewError` nur in Views gerendert, die `view==="connected"` nicht baut

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-2 · Report `AUDIT_NATIVE_PLUGINS.md` · Agent senior-developer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `…/src/state.ts:196-198` + `ConnectedView.tsx:6-24` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_NATIVE_PLUGINS.md`:92 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_NATIVE_PLUGINS.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-001 — 453 Requests für einen Dashboard-Load: 1× `/requirements/` pro Workspace (401 Workspaces ⇒ 401 Requests), keine Pagination, keine Virtualisierung

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**P1**` (bereits kanonisch) · P-Skala → P0=Critical, **P1=High**, P2=Medium, P3=Low |
| **Klassifikation** | NEU |
| **Workpackage** | WP-3 · Report `AUDIT_UI_BROWSER.md` · Agent e2e-tester (Browser, Playwright/Chromium) |
| **CR-Track / Issue** | NEU (verwandt #1115, #711 ⚠️ beide geschlossen) |
| **Ort (Reichweite)** | `/` — `DashboardViews/*` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_UI_BROWSER.md`:373 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_UI_BROWSER.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-002 — 112 `t()`-Keys fehlen in **beiden** Locales, maskiert durch Inline-Default ⇒ in DE englisch, in EN deutsch

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**P1**` (bereits kanonisch) · P-Skala → P0=Critical, **P1=High**, P2=Medium, P3=Low |
| **Klassifikation** | NEU |
| **Workpackage** | WP-3 · Report `AUDIT_UI_BROWSER.md` · Agent e2e-tester (Browser, Playwright/Chromium) |
| **CR-Track / Issue** | **BESTAETIGT CR-40/FEA-005** (7 geschlossene Issues: #676, #421, #595, #610, #651, #653, #654) |
| **Ort (Reichweite)** | `/settings`, `/import`, `/system-settings`, `/profile`; 112 Stellen in 41 Dateien` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_UI_BROWSER.md`:374 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_UI_BROWSER.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-003 — Kein Skip-Link; 25 Sidebar-Einträge ⇒ 50+ Tabs pro Hauptbereichswechsel

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**P1**` (bereits kanonisch) · P-Skala → P0=Critical, **P1=High**, P2=Medium, P3=Low |
| **Klassifikation** | NEU |
| **Workpackage** | WP-3 · Report `AUDIT_UI_BROWSER.md` · Agent e2e-tester (Browser, Playwright/Chromium) |
| **CR-Track / Issue** | **BESTAETIGT CR-40/FEA-001** (verwandt #449/#592/#608/#720, alle geschlossen) |
| **Ort (Reichweite)** | `AppShell global` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_UI_BROWSER.md`:375 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_UI_BROWSER.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-300 — 116 Keys fehlen in BEIDEN Locales (41 Dateien)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `P1` → kanonisch **High** · P-Skala → P0=Critical, **P1=High**, P2=Medium, P3=Low |
| **Klassifikation** | NEU |
| **Workpackage** | WP-3b · Report `AUDIT_FRONTEND_STATIC.md` · Agent frontend-reviewer |
| **CR-Track / Issue** | #619 |
| **Ort (Reichweite)** | `components/BaselinesView/BaselinesPanels.tsx:57` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_FRONTEND_STATIC.md`:438 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_FRONTEND_STATIC.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-301 — Ratchet-Obergrenze 116 macht die Lücke unsichtbar

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `P1` → kanonisch **High** · P-Skala → P0=Critical, **P1=High**, P2=Medium, P3=Low |
| **Klassifikation** | NEU |
| **Workpackage** | WP-3b · Report `AUDIT_FRONTEND_STATIC.md` · Agent frontend-reviewer |
| **CR-Track / Issue** | #619 |
| **Ort (Reichweite)** | `frontend/src/test/i18n-parity.test.ts:186` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_FRONTEND_STATIC.md`:439 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_FRONTEND_STATIC.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-160 — SSOT-Behauptung falsch; 7 datengetrieben / 5+ hartkodiert

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `presets/registry.py:13` vs. 6 Module` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:60 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-161 — `stage_mandatory` geseedet, **null** Produktionskonsumenten

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `attribute_definitions/stage_matrix.py:40-47` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:61 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-162 — Downgrade-Blocker ist **fail-open** (`except Exception: pass`)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `presets/gate.py:536-549` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:62 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-167 — CSV-Import schreibt `current_state` ohne Transition, History, Version

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `application/import_service.py:714-722` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:67 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-168 — ReqIF-Import ändert `current_state` **ohne `version`-Bump** → CAS-Blindstelle

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `application/reqif_import_service.py:791-793` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:68 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-169 — GET mutiert Zustand; `except Exception`; Status nie persistiert; `version` ohne State-Änderung

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | **BESTAETIGT (CR-07) + NEU** |
| **Ort (Reichweite)** | `application/interview_service.py:337-344, 354-369` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:69 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-180 — `workspace_id` **ohne FK** — inkl. `pl_artifact`, `pl_requirement`

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `26 von 44 Tabellen` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:80 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-181 — Datenmigration nicht nachgelaufen; Tag-Rückstände in 30 lebenden Links

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | #1093 (geschlossen) |
| **Ort (Reichweite)** | `persistence/migrations/0093_…py:76-78` + 99 Live-Zeilen` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:81 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-325 — `refines` (Built-in, Hierarchiekante) fehlt in **allen 3** Hierarchie-Definitionen

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `traceability/audit/hierarchy.py:172-186`, `baseline/services.py:430`, `baseline/delta_index_builder.py:288`, `frontend/src/utils/traceEndpoints.ts:72-75` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:50 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-326 — ReqIF-Import umgeht Workspace-Katalog komplett

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `application/reqif_import_service.py:886-897` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:51 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-327 — ICD-Connector ohne Paar-Validierung

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-4 · Report `AUDIT_DATA_MODEL.md` · Agent data-engineer |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `icd/traceability_connector.py:82-87` → `traceability/trace_link_manager.py:334` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_DATA_MODEL.md`:52 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_DATA_MODEL.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-191 — stdio-Handler existiert, stdio-Transport nicht exponiert; Doku nennt 3 Transporte

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `protocol_handler.py:345` vs. `views.py:425` |
| **Betroffene REQ-ID** | `REQ-L2-MC-019` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:433 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-192 — Nur 42.9 % der REQ-IDs haben einen Test-Bezug (3.6 % der Tests)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | CR-30 |
| **Ort (Reichweite)** | `backend`, `frontend/src`, `e2e` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:434 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-193 — 511 von 10 052 Testdefinitionen laufen in keinem CI-Job (`memory`, `link_types`, `tests`)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | CR-30 |
| **Ort (Reichweite)** | `.github/workflows/ci.yml:44-55` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:435 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-195 — „Regression-Suite ist vollständig grün" bei 511 nie ausgeführten Tests + 4 eigenen Errors

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | CR-43 |
| **Ort (Reichweite)** | `RELEASE_v1.8.0-beta.17.md:12` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:437 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-196 — „W1–W4 implementiert, dokumentiert und getestet" — W4-Tests sind rot (65 FE-Fehler)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `RELEASE_v1.8.0-beta.17.md:17` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:438 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-201 — Nummerierungslücke: 031 existiert nirgends; Matrix springt 030 → 032

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | ``SN_Stakeholder_Needs.md`` |
| **Betroffene REQ-ID** | `REQ-L0-031` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:443 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-330 — 324 Quell-REQ-IDs fehlen in der SOLL-Matrix (24× L2, 300× L3)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | CR-09, CR-47 |
| **Ort (Reichweite)** | `docs/se/traceability-matrix.md` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:412 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-331 — Matrix publiziert 0 von 354 REQ-L3-Zeilen; behauptete 369 vs. gemessene 354

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | CR-09 |
| **Ort (Reichweite)** | `traceability-matrix.md:649-655` |
| **Betroffene REQ-ID** | `REQ-L3-Zeilen` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:413 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-333 — `open_adrs` existiert repo-weit nicht (0/835 REQs)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `docs/se/**` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:415 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-334 — 14 von 15 `arch_impact:true` ohne ADR; kein akzeptiertes ADR deckt L1/L2

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `L1_Gesamtsystem_Requirements.md:37…2522` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:416 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-339 — `arch_impact` bei L2-Ableitung von `true` auf `false` umgeschrieben, ohne ADR

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | ``L2_{ReqIF,Comment,VectorSearch}…_Requirements.md`` |
| **Betroffene REQ-ID** | `REQ-L1-034` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:421 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-340 — 17 `Implemented`-REQ-L1 mit nicht-implementiertem Kind (3 vollständig)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `traceability-matrix.md` §2/§3` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:422 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-342 — MCP-Tool `semantic_search` als `Implemented/Covered` dokumentiert, existiert nicht

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `L2_McpServerSystem_Requirements.md:97-107` |
| **Betroffene REQ-ID** | `REQ-L2-MC-014` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:424 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-343 — 7/29 Stichproben-REQs als nicht umgesetzt markiert, obwohl Code + Tests existieren

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `REQ-L2-RQ-001/-002`, `REQ-L2-AT-018`, `REQ-L2-CM-001`, `REQ-L2-RF-015` |
| **Betroffene REQ-ID** | `REQ-L2-AT-018`, `REQ-L2-CM-001`, `REQ-L2-RF-015`, `REQ-L2-RQ-001` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:425 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-344 — 3 REQ-L1 `Not Implemented` mit vollständig implementierten Kindern

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `REQ-L1-022/-033/-036` |
| **Betroffene REQ-ID** | `REQ-L1-022` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:426 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-347 — Azure implementiert und beworben, aber nicht wählbar

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `frontend/src/api/llm-settings.ts:22` |
| **Betroffene REQ-ID** | `REQ-L2-LA-007` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:429 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-348 — i18n `Implemented/Covered`; 112 Keys fehlen in beiden Locales, Lint-Regel wirkungslos

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `traceability-matrix.md:114` |
| **Betroffene REQ-ID** | `REQ-L1-016`, `REQ-L2-RF-001` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:430 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-349 — CSV-Import meldet Datenverlust als `success: true`

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/application/import_service.py:149,226-233` |
| **Betroffene REQ-ID** | `REQ-L1-021`, `REQ-L2-AS-014` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:431 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-350 — Asynchronie `Covered`, jede Celery-Task läuft 4×

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `High` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-5 · Report `AUDIT_TRACEABILITY.md` · Agent validator |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `REQ-L2-RO-001/-AS-029/-LA-008` |
| **Betroffene REQ-ID** | `REQ-L2-RO-001` |
| **Evidenz** | `AUDIT_TRACEABILITY.md`:432 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_TRACEABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-222 — Workspace-Fence greift auf 269/311 mutierenden Routen nicht

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**HIGH**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6a · Report `AUDIT_SECURITY.md` · Agent security-auditor |
| **CR-Track / Issue** | Reopen-Rest zu **#103** (geschlossen) |
| **Ort (Reichweite)** | `backend/auth_tenancy/workspace_scope.py:114`, `backend/auth_tenancy/rest.py:259-271`, `backend/application/requirement_service.py:755` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_SECURITY.md`:46 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_SECURITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-223 — Django-Admin exponiert, 500-er, ohne Brute-Force-Schutz

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**HIGH**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6a · Report `AUDIT_SECURITY.md` · Agent security-auditor |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `backend/reqogniloom/urls.py` (`/admin/`), `settings.py` (kein `ADMIN_ATTEMPTS_BEFORE_LOCKOUT`)` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_SECURITY.md`:47 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_SECURITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-224 — Kein Secret-Scanning-Gate (weder pre-commit noch CI)

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**HIGH**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6a · Report `AUDIT_SECURITY.md` · Agent security-auditor |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `.github/workflows/*.yml`, `.woodpecker.yml`, `.agents/hooks/` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_SECURITY.md`:48 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_SECURITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-225 — 27 von 28 Actions nur Tag-gepinnt bei `packages: write`

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**HIGH**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6a · Report `AUDIT_SECURITY.md` · Agent security-auditor |
| **CR-Track / Issue** | **CR-45 verschÃ¤rft** |
| **Ort (Reichweite)** | `.github/workflows/docker-publish.yml:42-185`, `ci.yml:15-343`, `playwright.yml:50-216`, `pages.yml:43-55`, `version-drift-check.yml:49` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_SECURITY.md`:49 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_SECURITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-239 — **Der Audit erzeugte den Secret-Leak selbst**: kein Evidenz-Redactor + Cleanup prÃ¼fte User-LÃ¶schung, aber nie Key-Widerruf

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**HIGH**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6a · Report `AUDIT_SECURITY.md` · Agent security-auditor |
| **CR-Track / Issue** | — |
| **Ort (Reichweite)** | `AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2237-2246`, `AUDIT_EVIDENCE/wp1d-cleanup-verification.md` Â§2` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_SECURITY.md`:63 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_SECURITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-270 — `audit.archive_lifecycle_manager` ist **nicht** im Worker-Task-Set — monatliche Retention läuft nie, `audit_entry` wächst unbegrenzt

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | BESTAETIGT |
| **Workpackage** | WP-6b · Report `AUDIT_RELIABILITY.md` · Agent backend-reviewer |
| **CR-Track / Issue** | **#125 (BESTÄTIGT)** · CR-10 |
| **Ort (Reichweite)** | `audit/archive.py:448`, `reqogniloom/celery.py:45`, `audit/apps.py:36`, `settings.py:822` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_RELIABILITY.md`:49 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_RELIABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-281 — `as_goal` ohne `UNIQUE(lineage_id, sequence_number)` und ohne `version` → `max+1` unter keinem Lock forkt die Lineage

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6b · Report `AUDIT_RELIABILITY.md` · Agent backend-reviewer |
| **CR-Track / Issue** | CR-06 (neu) |
| **Ort (Reichweite)** | `application/goal_service.py:134-149`, `persistence/models.py:3342-3381` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_RELIABILITY.md`:50 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_RELIABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |

#### AUD-2026-09-282 — 6 Transition-Wrapper reichen `expected_version` nicht weiter ⇒ REST-Transitions bleiben last-writer-wins, obwohl dieselben Services `update_*` schützen

| Feld | Wert |
|---|---|
| **Schweregrad** | High — Originalwert `**High**` (bereits kanonisch) |
| **Klassifikation** | NEU |
| **Workpackage** | WP-6b · Report `AUDIT_RELIABILITY.md` · Agent backend-reviewer |
| **CR-Track / Issue** | CR-08 (Rest) |
| **Ort (Reichweite)** | `application/adr_service.py:562`, `risk_service.py:686`, `issue_service.py:726`, `change_request_service.py:638`, `main_goal_service.py:556`, `goal_service.py:659` |
| **Betroffene REQ-ID** | — |
| **Evidenz** | `AUDIT_RELIABILITY.md`:51 (Finding-Tabelle) · `AUDIT_EVIDENCE/`-Dateien des WP |
| **Volltext / Reproduktion / Empfehlung** | `AUDIT_RELIABILITY.md` — dort voll ausformuliert; dieses Register normalisiert nur |
| **Status** | offen |


## 6. Bestätigte Kontrollen (Negativbefunde — **nicht** in der Finding-Zählung)

Nach der PASS-Regel (§2.4) getrennt geführt. Diese Zeilen belegen, dass geprüfte
Kontrollen **wirksam** sind; sie sind kein Mangel.

| ID | Sev | WP | Kontrolle | Beleg |
|---|---|---|---|---|
| `AUD-2026-09-158` | Info | WP-4 | 4 von 11 Link-Typen haben 0 Links — **Kontext zur Offenheit**, kein Defekt | live gemessen |
| `AUD-2026-09-159` | Info | WP-4 | Primärkatalog des Link-Typs konsistent offen über DB/REST/MCP/FE | 4-Ebenen-Matrix |
| `AUD-2026-09-165` | Info | WP-4 | Presetwechsel auf der Workflow-Achse nachweisbar wirksam | live GET, 1/5/9 Transitions |
| `AUD-2026-09-174` | Info | WP-4 | Tenant-Scope-Trennung sauber; 0 Cross-Tenant/Cross-WS TraceLinks | live gemessen |
| `AUD-2026-09-185` | Info | WP-4 | 29/31 `pl_*`-Tabellen mit RLS; **0** `.raw()` im Produktions-Backend | live gemessen |
| `AUD-2026-09-067` | Info | WP-1b | Circuit-Breaker außerhalb eines Tenant-Kontexts still deaktiviert — **kein Produktpfad** | `audit_logger.py:174-191` |
| `AUD-2026-09-050` | Info | WP-1d | Verdachtiger Cross-Tenant-Leak via `workspace.list` — **Test-Setup, kein Produktfehler** | WIDERLEGT |
| `AUD-2026-09-152` (WP-2) | Info | WP-2 | „nicht live verifizierte Plugin-Verträge" ist überholt — beide **sind** live verifizierbar | WIDERLEGT (CR-24) |
| RLS-Rollen | — | WP-6a | Laufende DB-Rolle `reqogniloom_app` ist non-superuser **und ohne BYPASSRLS** ⇒ **RLS greift tatsächlich** | `wp6a-rls-db-roles.md:50-58` |
| Adapter-Degradation | — | WP-1b | L4-Mock-Fallback ist mit `[MOCK FALLBACK]` markiert, wird nie gecacht, wird geloggt + auditiert | ADR-02-konform |
| Retry-Klassifikation | — | WP-1b | 401/403/400 sind non-retryable (1 Versuch), 429/5xx transient — live gemessen | `resilient_transport.py:92-103` |

**Zusammenfassung:** 5 formerkläre `PASS`-Findings + 6 weitere Negativbefunde.
Diese **vermindern** das tatsächliche Defektvolumen gegenüber der rohen Zeilenzahl.

---

## 7. BLOCKED / nicht verifiziert

**Vollständige Liste** — jedes BLOCKED-Finding sowie alle offenen Prüfpunkte.
BLOCKED ist **ausdrücklich kein PASS**.

### 7.1 BLOCKED-Findings (5 + 1 Teilbefund)

| ID | Sev | WP | Thema | Grund |
|---|---|---|---|---|
| `AUD-2026-09-023` | Info | WP-3 | Workspace-Löschen-Bestätigungsdialog | **nicht verifizierbar** — kein sicherer Trigger ohne Datenverlust |
| `AUD-2026-09-024` | Info | WP-3 | Diagrammeditoren, Create-Dialoge, Baseline-Compare | **NICHT VERIFIZIERBAR** — Workspace enthielt 0 Datensätze |
| `AUD-2026-09-025` | Info | WP-3 | Tastaturkontrast, `prefers-reduced-motion` | keine Axe-Messung, keine Animation im Testfenster auslösbar |
| `AUD-2026-09-178` | Medium | WP-4 | 3/11 Item-Types materialisieren nie; 134/401 Workspaces ohne Attribut-Katalog | **NEU (BLOCKED-Anteil)** — Teil des Befunds ist belegt, Rest offen |
| `AUD-2026-09-190` | — | WP-4 | Diff-Engine-Korrektheit | ohne Mutation **nicht messbar** — explizit **kein PASS** |
| `AUD-2026-09-205` | Low | WP-5 | Health-Aggregation bei Totalausfall | statisch nicht entscheidbar, Messung am laufenden Stack nötig |

### 7.2 Offene Prüfpunkte aus den WP-Reports (nicht als Findings geführt)

| WP | Punkt | Grund |
|---|---|---|
| WP-1b | Echter Aufruf gegen Anthropic/OpenAI/Azure/OpenCode | keine API-Keys; `LLM_PROVIDER`-Umschaltung hätte den geteilten Container verändert. **Request-Formate wurden per Capture gegen einen Stub feldweise verifiziert** — echte Provider-Antworten **nicht**. |
| WP-1b | Modell-ID-Gültigkeit | statisch gegen Provider-Doku, **nicht** live gegen `/v1/models` |
| WP-1b | Echter Ollama-Server | kein Ollama im Stack; Verhalten eines realen `llama3` ungeprüft |
| WP-1b | Circuit-Breaker OPEN→Half-Open→CLOSED mit echter DB-Zeile | statisch gelesen, nicht live gefahren |
| WP-3 | Bundle-Größe, ungenutzte Libraries | kein `vite build` in der Analyse |
| WP-3 | Tote Dateien / ungenutzte Komponenten | bräuchte Import-Graph über Modulgrenzen |
| WP-3b | Auth-Dominanz Cookie vs. Bearer im Deployment | Deployment-Konfiguration; die 7 Roh-`fetch()`-Pfade als **potenzielle** Bruchstelle markiert, **nicht** als Finding |
| WP-3b | Typ-Drift TS ↔ Django-Serializer | nur Stichprobe, kein Schemasvergleich |
| WP-5 | Ob die 3,6 % REQ-referenzierten Tests den REQ **inhaltlich** prüfen | statische Analyse; Testausführung nötig → `tester` |
| WP-5 | `AGENTS.md:16` „111 E2E-Tests" | kein Playwright-Lauf |
| WP-6a | `/admin/` **tatsächlich** erreichbar und Brute-Force-anfällig | live 500 wegen Static-Manifest; siehe C12 |
| WP-6b | Health-Aggregation unter Fehlerinjektion | erfordert Eingriff in den laufenden Stack |

---

## 8. Adjudizierte Widersprüche (C1–C12)

Jede Zeile wurde **eigenständig geprüft** (Datei:Zeile gelesen, Code verifiziert).
Kein „beide könnten recht haben" ohne Auflösung.

| # | Thema | Aussage A | Aussage B | **Ergebnis** | Beleg der Prüfung |
|---|---|---|---|---|---|
| **C1** | Anzahl fehlender i18n-Keys | WP-3: **112** | WP-3b: **116** | **B bestätigt → 116** | `frontend/src/test/i18n-parity.test.ts:185-186`: `Re-measured: 117 - 1 = 116` / `MISSING_KEY_BASELINE = 116`. Die Differenz 4 zu WP-3 erklärt sich durch Testdatei-Ausschluss + `<Trans i18nKey>`-Ergänzung. |
| **C2** | Was der i18n-Ratchet prüft | WP-3 (`-016`): prüft Key-Menge statt Code→Locale | WP-3b: prüft **sehr wohl** Code→Locale; Defekt = eingefrorene Obergrenze 116 | **B bestätigt** | `i18n-parity.test.ts:102-111` `collectReferencedKeys()` mit `T_CALL_PATTERN = /\bt\(\s*["']([a-zA-Z0-9_.]+)["']/g` ist ein echter Code→Locale-Scan; `:219` `toBeLessThanOrEqual(116)` ist die eingefrorene Obergrenze. |
| **C3** | Hex-Literale im Frontend | WP-3: erst 441/74, dann selbst korrigiert auf **0** | WP-3b: **37** in Prod, davon **21 in `.ts`** vom Ratchet nicht erfasst | **B bestätigt → 37** | Eigenmessung mit WP-3b-Methode (Kommentare gestrippt, Strings erhalten): `.ts` 21 Treffer in 3 Dateien, `.tsx` 16 in 2 Dateien = **37**. `ui-ratchet.test.ts:48` `collectFiles(dir, /\.tsx$/)` scannt **ausschließlich `.tsx`**. |
| **C4** | Veraltete E2E-Selektoren | WP-3: **0** stale | WP-3b: **≥6** verifiziert stale | **beide teilweise korrekt, korrigiert zu 3** | Repo-weit: `visibility-row-diagrams`, `visibility-checkbox-diagrams`, `visibility-reset-diagrams` stehen in `e2e/tests/user-profile.spec.ts:23,24,31,41` und haben **0** Treffer in `frontend/src` ⇒ **verifiziert stale**. `login-form`, `main-header`, `todo-item` haben **0 Treffer in `e2e/` *und* `frontend/src`** ⇒ sie sind nicht „stale", sondern **überhaupt nicht vorhanden** (WP-3b-Fundstelle „`e2e/tests/*.spec.ts`" ist für diese drei falsch). |
| **C5** | API-Key-Widerruf mit Bestätigungsdialog | WP-3 (`-006`): **ohne** Dialog | WP-3b: **mit** `ConfirmDialog` | **B bestätigt** | `ApiKeysSection.tsx:276-288`: `{pendingRevokeId && (<ConfirmDialog … onConfirm={confirmRevoke} … testId="api-key-revoke-confirm" />)}`. Fehlend sind nur Pagination/Filter/Virtualisierung (`ApiKeysSection.tsx:224`). |
| **C6** | MCP-Tool-Anzahl | `AGENTS.md:8,30` 215, `tools/list` lieferte **80** | WP-1a: Registry hat **219/35** | **B bestätigt → 219 Tools / 35 Gruppen; Doku-Drift, kein Registrierungsfehler** | `wp1a-mcp-registry-manifest-219.json`: `tool_count: 219`, 219 Einträge, 35 Präfix-Gruppen. Die 80 sind ein **Rollenfilter** (`readwrite` kennt `can_write` nicht ⇒ 139 `is_write`-Tools werden herausgefiltert). |
| **C7** | ViewSet-/APIView-Zahl | `AGENTS.md:30`: 27 + 67 | WP-1d: **27 + 76** | **beide teilweise korrekt, korrigiert zu 27 ViewSets + 76 APIViews** | `backend/rest_api/urls.py`: **27** `router.register(...)`-Aufrufe über **26** distinkte Klassen (`TraceLinkViewSet` doppelt als `tracelinks` + `trace-links`); + `BaseEntityViewSet` (Shared Base, keine Route) = **27 ViewSet-Klassen**. APIViews: **76** unabhängig nachgezählt. `67` in `AGENTS.md` ist **veraltet**. |
| **C8** | Embedding-Dimension | Auftragsprämisse: dimensionsfremde Einbettung könne fehlschlagen | WP-1c: alle Spalten `vector(384)`, jeder Write-Site prüft vorher | **B bestätigt — Prämisse widerlegt** | `backend/persistence/embedding_dimensions.py`: `DEFAULT_EMBEDDING_VECTOR_DIMENSIONS = 384`, alle `VectorField(dimensions=EMBEDDING_VECTOR_DIMENSIONS)` (`models.py:1602,1946`). Das Modul-Docstring dokumentiert #794: alle vier Spalten auf 384 vereinheitlicht. Rest = stille Degradation ⇒ **Duplikat `AUD-2026-09-143` / #1019**. |
| **C9** | `audit.archive_lifecycle_manager` im Worker | WP-5 (`-204`): **nicht reproduzierbar**, `settings.py:822` registriert es | WP-1c (`-125`) + WP-6b (`-270`): **NICHT im Task-Set** | **B bestätigt (WP-6b/WP-1c)** | `settings.py:822` ist ein Eintrag in **`CELERY_BEAT_SCHEDULE`** (`:817-830`), **nicht** die Worker-Registrierung. `celery.py:45` `app.autodiscover_tasks()` importiert `audit.tasks` nach App-Modulname — `audit/apps.py:36` importiert nur `audit.writer`. `backend/audit/archive.py` wird von **nichts** außer sich selbst importiert ⇒ Task nie registriert. |
| **C10** | Nicht ausgeführte Tests in CI | Vor-Audit `CR-30`: **463** | WP-5: **511** von 10 052 | **beide teilweise korrekt; reproduzierbar ist 443 von 8 127** | `.github/workflows/ci.yml:43-55` definiert 4 Test-Sets über **20** App-Pfade. Nicht abgedeckt: `memory/tests` (282), `link_types/tests` (135), `backend/tests` (26) = **443 Testdefinitionen**. Die Zahlen 463/511/10 052 beruhen auf abweichenden Zählmethoden (Dezimal-Tausenderpunkte, Klassen- vs. Methodenzählung, inkl. Frontend/E2E). |
| **C11** | `stack-db-redis.txt` DB-Rolle | WP-1c: `DB_USER=reqflow (superuser)` | WP-6a: laufender Container nutzt `reqogniloom_app` (non-superuser, kein BYPASSRLS) | **beide korrekt für verschiedene Scopes** | `stack-db-redis.txt:11` liest `deploy/.env` (**Bootstrap-/Migrationsrolle**). `wp6a-rls-db-roles.md:27-31` liest die **effektive Backend-Container-Umgebung** (Compose-Override) = `reqogniloom_app`, `rolsuper=f`, `rolbypassrls=f` ⇒ **RLS greift zur Laufzeit tatsächlich**. `settings.py:328-342` Default ist bereits `reqogniloom_app`. WP-6a hat die Diskrepanz bereits selbst dokumentiert (`:36-39`). |
| **C12** | Rotations-Endpunkt `/admin/` | WP-6a (`-223`): `/admin/` exponiert, **500** wegen fehlendem staticfiles-Manifest | — | **übernommen, teilweise verifiziert** | `urls.py:33` `path("admin/", admin.site.urls)` bestätigt; `ADMIN_ATTEMPTS_BEFORE_LOCKOUT` ist repo-weit **nicht vorhanden** ⇒ Brute-Force-Schutz fehlt bestätigt. **Einschränkung:** `backend/Dockerfile:217-223` führt `collectstatic --noinput` aus und `settings.py:405` setzt `CompressedManifestStaticFilesStorage` ⇒ im **Produktions-Image** ist ein Manifest vorhanden. Die 500 gilt damit für den **Audit-Stack**, nicht allgemein. |

---

## 9. Korrekturen an Vor-Audits und offene Entscheidungen

### 9.1 Korrekturen an Vor-Audit-Befunden (bestätigt durch dieses Gate)

| Vor-Audit | Vor-Audit-Aussage | Korrektur | Beleg |
|---|---|---|---|
| `CR-08` | Transition validiert **vor** dem Lock → Race | **WIDERLEGT / behoben** | `AUD-2026-09-166`: `workflow/services.py:302-341` validiert **nach** dem Lock, mit expliziten `CR-08:`-Kommentaren und Lock-Weitergabe an `perform_transition` |
| `CR-30` | 463 nicht ausgeführte Testdefinitionen | **Zahl korrigierbar, Defektklasse bestätigt** | `AUD-2026-09-193`: 3 App-Pfade fehlen in CI; reproduzierbar 443 (s. C10) |
| `CR-17` | 2 Modelle ohne `tenant_id`/RLS | **erweitert auf 5** | `AUD-2026-09-184`: `application/models.py:44,147,170,204`, `baseline/models.py:116` |
| `CR-20` | Budget/Tracking-Lücke | **bestätigt, Severity relativiert** | `AUD-2026-09-020`, Abschnitt WP-1b: P1 → P2 (self-hosted) bzw. policyabhängig P1 |
| Embedding-Dimension | implizite Prämisse des Auftrags | **widerlegt** | s. C8; alle 4 Spalten `vector(384)` via eine SSOT-Konstante (#794) |
| `#940` | offener Blocker (Attribut-`kind`) | **→ `#1112`** | `AUD-2026-09-176`: `#940` ist geschlossen; der Metadaten-Defekt ist `#1112`, **bestätigt und dreifach gesperrt** statt einfach |
| `#1019` | Embedding-Dimension | **Duplikat** | `AUD-2026-09-143` als `DUPLIKAT #1019` (geschlossen 2026-09-21) geführt |
| `CR-22` | Plugin-Verträge | **präzisiert** | `AUD-2026-09-152` (WP-2): beide Verträge **sind** live verifizierbar |
| `CR-24` | nicht live verifizierte Verträge | **WIDERLEGT** | s. §6 |
| `CR-09` | Matrix-Drift | **bestätigt + verschärft** | `AUD-2026-09-330` (früher `170`, 324 fehlende REQ-IDs), `AUD-2026-09-331` (früher `171`, 0 von 354 REQ-L3 publiziert) |

### 9.2 ID-Kollisionen — **aufgelöst** (Regel: früherer Commit behält)

**Angewandte Regel (vom Orchestrator verbindlich entschieden):**
> *Wer die ID **zuerst committet** hat, behält sie. Wer später committet hat,
> wird umnummeriert.*

#### (a) Commit-Reihenfolge — Beleg

Ermittelt mit `git log --diff-filter=A --format='%h|%ad|%s' --date=iso -- <report>`
und gegengeprüft mit `git cat-file -e <sha>:<pfad>`:

| WP | Report | Commit | Zeitstempel | Verifikation |
|---|---|---|---|---|
| WP-2 | `AUDIT_NATIVE_PLUGINS.md` | `75beb750` | 2026-09-30 **06:53:41** | Datei existiert in `75beb750`, **nicht** in `ed9a445a` |
| WP-4 | `AUDIT_DATA_MODEL.md` | `441f48f3` | 2026-09-30 **20:13:40** | Datei existiert **erstmals** in `441f48f3` (`git cat-file -e 75beb750:…` → *not in*) |
| WP-5 | `AUDIT_TRACEABILITY.md` | `33237041` | 2026-09-30 **22:01:24** | Datei existiert **erstmals** in `33237041` (dem Gate-Commit dieses Audits) |

**Reihenfolge: WP-2 (06:53) → WP-4 (20:13) → WP-5 (22:01).**

#### (b) Anwendung der Regel

| Klasse | IDs | Frühester | Später | Ergebnis |
|---|---|---|---|---|
| **K2** | `150–153` | **WP-2** `75beb750` 06:53 | WP-4 `441f48f3` 20:13 | **WP-2 behält**, **WP-4 umnummeriert** |
| **K3** | `170–190` | **WP-4** `441f48f3` 20:13 | WP-5 `33237041` 22:01 | **WP-4 behält**, **WP-5 umnummeriert** |

#### (c) Umrechnungstabelle (jede ID einzeln)

**WP-4: 4 IDs verschoben** — `AUDIT_DATA_MODEL.md` + `wp4-link-type-4level-matrix.md`

| alt | neu | alt | neu | alt | neu | alt | neu |
|---|---|---|---|---|---|---|---|
| `150` | **`325`** | `151` | **`326`** | `152` | **`327`** | `153` | **`328`** |

**WP-5: 21 IDs verschoben** — `AUDIT_TRACEABILITY.md` (+ 1 semantischer Querverweis)

| alt | neu | alt | neu | alt | neu |
|---|---|---|---|---|---|
| `170` | **`330`** | `171` | **`331`** | `172` | **`332`** |
| `173` | **`333`** | `174` | **`334`** | `175` | **`335`** |
| `176` | **`336`** | `177` | **`337`** | `178` | **`338`** |
| `179` | **`339`** | `180` | **`340`** | `181` | **`341`** |
| `182` | **`342`** | `183` | **`343`** | `184` | **`344`** |
| `185` | **`345`** | `186` | **`346`** | `187` | **`347`** |
| `188` | **`348`** | `189` | **`349`** | `190` | **`350`** |

**Zielblöcke:** `325–328` (WP-4) und `330–350` (WP-5); `329` bleibt als Trenner frei.

#### (d) Betroffene Dateien (vollständig)

| Datei | Ersetzungen | Art |
|---|---:|---|
| `AUDIT_DATA_MODEL.md` | 12 | Finding-Tabelle (4), Prioritätsliste (2), Fließtext/Kurzform (6) |
| `AUDIT_EVIDENCE/wp4-link-type-4level-matrix.md` | 5 | WP-4-Evidenz |
| `AUDIT_TRACEABILITY.md` | 21 | Finding-Tabelle WP-5 |
| `AUDIT_EVIDENCE/wp3b-07-api-client.md` | 1 | **semantischer Querverweis** `187` = WP-5s Azure-Befund → `347` |
| `AUDIT_FINDINGS.md` | 87 | Master-Tabelle, Detailabschnitte, Legende, Gate-Vermerk |

**Bewusst NICHT geändert** (Eindeutigkeitsprüfung je Fundstelle):

| Datei / Stelle | Grund |
|---|---|
| `AUDIT_NATIVE_PLUGINS.md:106-109` | **WP-2 behält** `150–153` — unverändert |
| `wp4-baseline-and-artifact-model.md`, `wp4-bootstrap-fieldkind-proof.md`, `wp4-constraints-and-migrations.md`, `wp4-state-bypass-inventory.md` | Verweise auf `170–190` sind **WP-4s eigene** Findings ⇒ bleiben |
| `AUDIT_DATA_MODEL.md:418` (`AUD-070/071`) | Querverweis auf **WP-1d** — fremde IDs, unangetastet |

### 9.3 Dangling-Verweise (markiert, nicht repariert)

| Verweis | Datei:Zeile | Status |
|---|---|---|
| ~~`AUD-2026-09-026…043`~~ | `AUDIT_TRACEABILITY.md:433`, `wp5-04-widersprueche.md:88` | **BEHOBEN (O-2):** korrigiert auf **`AUD-2026-09-030…043`**. `026` existierte nicht (`026–029` reserviert); `030` ist der erste vergebene MCP-ID. |
| `AUD-2026-09-221` (2. Vorkommen) | `AUDIT_SECURITY.md:98` | **Kein Defekt** — Verweis im Remediation-Abschnitt auf das eigene Finding aus `:45`. |
| `AUD-2026-09-120`, `-092` (2. Vorkommen) | `AUDIT_DATA_MODEL.md:417,419` | **Kein Defekt** — Verweise in der Reconciliation-Tabelle auf WP-1c-/WP-1d-Befunde. |

---

## 10. Dokumentationsdrift (Ist vs. Soll)

| Angabe | Quelle | Dokumentiert | **Gemessen** | Bewertung |
|---|---|---|---|---|
| MCP-Tools | `AGENTS.md:8`, `AGENTS.md:30` | 215 (auch 218/219 in Lesetexten) | **219** (`tool_count` im Registry-Manifest) | **Doku-Drift** |
| MCP-Tool-Gruppen | `AGENTS.md:8,30,58` | 31 | **35** Präfixe | **Doku-Drift** |
| ViewSets | `AGENTS.md:30` | 27 | **27** (`router.register`) | ✅ korrekt |
| APIViews | `AGENTS.md:30` | 67 | **76** | **Doku-Drift** |
| Compose-Services | `AGENTS.md:7` | 8 | **15** (`postgres`, `postgres-backup`, `redis`, `backend`, `llm-preflight`, `migrate`, `celery`, `celery-beat`, `frontend`, `honcho-postgres`, `honcho-redis`, `honcho-migrate`, `honcho`, `honcho-deriver`, `bluepencil`) | **Doku-Drift** |
| E2E-Tests | `AGENTS.md:16` | 111 | **54** Spec-Dateien in `e2e/tests/` | **Doku-Drift** (Testanzahl vs. Dateianzahl nicht direkt vergleichbar) |
| React-Version | `AGENTS.md:7,59`, Projektkontext | React 18 | **`react: ^19.2.8`**, `react-dom: ^19.3.0` (`frontend/package.json:34-35`) | **Doku-Drift** |
| TypeScript-Toolchain | Projektkontext | — | `vite ^8.1.5`, `eslint ^10.10.0` | außerhalb des belegten Rahmens |
| fehlende i18n-Keys | `AGENTS.md` / Matrix | 112 (WP-3) | **116** | **Doku-/Berichtsdrift**, s. C1 |
| Backend-Services | `AGENTS.md:14` | 19 | nicht gemessen (außerhalb Auftrag) | offen |

---

## 11. Statistik

### 11.1 Findings je Schweregrad × Klassifikation

| Schweregrad | NEU | BESTAETIGT | WIDERLEGT | BLOCKED | DUPLIKAT | Summe |
|---|---:|---:|---:|---:|---:|---:|
| **Critical** | 14 | 0 | 0 | 0 | 0 | **14** |
| **High** | 75 | 1 | 0 | 0 | 0 | **76** |
| **Medium** | 111 | 2 | 0 | 1 | 1 | **115** |
| **Low** | 56 | 1 | 2 | 1 | 0 | **60** |
| **Info** | 8 | 0 | 3 | 4 | 0 | **15** |
| **Findings gesamt** | **264** | **4** | **5** | **6** | **1** | **280** |
| *davon bestätigte Kontrollen (PASS)* | 1 | 4 | 0 | 0 | 0 | **5** |
| **Master-Tabelle gesamt** | 265 | 8 | 5 | 6 | 1 | **285** |


### 11.2 Findings je Workpackage

| WP | Report | Agent | Critical | High | Medium | Low | Info | Findings | Kontrollen | Zeilen |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WP-1a/1b/1d | `AUDIT_EXTERNAL_INTEGRATIONS.md` | senior-developer (WP-1a/1b) · api-specialist (WP-1d) | 5 | 19 | 24 | 9 | 5 | **62** | 0 | 62 |
| WP-1c | `AUDIT_INFRASTRUCTURE.md` | devops-engineer | 4 | 8 | 13 | 5 | 0 | **30** | 0 | 30 |
| WP-2 | `AUDIT_NATIVE_PLUGINS.md` | senior-developer | 1 | 6 | 7 | 6 | 4 | **24** | 0 | 24 |
| WP-3 | `AUDIT_UI_BROWSER.md` | e2e-tester (Browser, Playwright/Chromium) | 0 | 3 | 7 | 12 | 3 | **25** | 0 | 25 |
| WP-3b | `AUDIT_FRONTEND_STATIC.md` | frontend-reviewer | 0 | 2 | 11 | 12 | 0 | **25** | 0 | 25 |
| WP-4 | `AUDIT_DATA_MODEL.md` | data-engineer | 0 | 11 | 17 | 5 | 3 | **36** | 5 | 41 |
| WP-5 | `AUDIT_TRACEABILITY.md` | validator | 2 | 19 | 15 | 1 | 0 | **37** | 0 | 37 |
| WP-6a | `AUDIT_SECURITY.md` | security-auditor | 2 | 5 | 8 | 7 | 0 | **22** | 0 | 22 |
| WP-6b | `AUDIT_RELIABILITY.md` | backend-reviewer | 0 | 3 | 13 | 3 | 0 | **19** | 0 | 19 |
| **Gesamt** | 9 Reports | | 14 | 76 | 115 | 60 | 15 | **280** | **5** | **285** |


### 11.3 Verteilung der Original-Skalen

| Skala | WPs | Findings | davon umgerechnet |
|---|---|---:|---:|
| 5-stufig (`Critical/High/Medium/Low/Info`) | WP-1a, WP-1b, WP-1c, WP-1d, WP-2, WP-4, WP-5, WP-6a, WP-6b | 235 | 0 |
| P-Skala (`P1/P2/P3`) | WP-3 (25), WP-3b (25) | 50 | **50** |

---

## 12. Konsistenz-Gate-Vermerk

### 12.1 Durchgeführte Reparaturen

| Datei:Zeile | alt | neu | Grund |
|---|---|---|---|
| `AUDIT_FRONTEND_STATIC.md:438-462` (25 Zeilen) | `AUD-2026-09-240` … `264` | `AUD-2026-09-300` … `324` | **Autorisierte Kollisionsreparatur.** WP-3b überlappte mit WP-6a (220–241) bei 240/241. Entscheidung: WP-6a behält 220–241 (2 Commits), WP-3b → neuer Block 300–324. Umrechnung +60, 25 Einzel-IDs. |
| `AUDIT_FRONTEND_STATIC.md:467` | `Finding-ID-Bereich: **240–264**` | `**300–324**` | Folge der Umnummerierung; Bereichsangabe im Fließtext. |
| `AUDIT_DATA_MODEL.md` (12 Fundstellen) | `150,151,152,153` (+ Kurzformen) | `325,326,327,328` | **Regel „früherer Commit behält"**: WP-2 (`75beb750`, 06:53) vor WP-4 (`441f48f3`, 20:13) ⇒ WP-4 weicht. |
| `AUDIT_EVIDENCE/wp4-link-type-4level-matrix.md` (5) | `150,151,152` | `325,326,327` | dieselbe Umnummerierung in der WP-4-Evidenz |
| `AUDIT_TRACEABILITY.md` (21 Fundstellen) | `170…190` | `330…350` | **Regel „früherer Commit behält"**: WP-4 (`441f48f3`, 20:13) vor WP-5 (`33237041`, 22:01) ⇒ WP-5 weicht. |
| `AUDIT_EVIDENCE/wp3b-07-api-client.md:157` | `AUD-2026-09-187` | `AUD-2026-09-347` | semantischer Querverweis: `187` war **WP-5s** Azure-Befund, nicht WP-4s Registry-Befund (Kontext „`azure` nicht wählbar") |
| `AUDIT_DATA_MODEL.md:92` | `41 IDs vergeben (150–190)` | `(154–190, 325–328)` | Bereichsangabe an die neue Blocklage angepasst |
| `AUDIT_RELIABILITY.md:24-26` | veraltete Blockliste | aktualisiert | andere WPs haben zwischenzeitlich umnummeriert |
| `AUDIT_DATA_MODEL.md:165` | `AUD-150 bis AUD-159` | `AUD-325, AUD-326, AUD-327, AUD-328` | **Korrektur einer durch die Regex verursachten Fehlform**: die Bereichsangabe wäre sonst auf einen nicht existierenden Block `325–159` gelaufen |
| `AUDIT_DATA_MODEL.md:400,415,418` | `AUD-151/152`, `AUD-150/157`, `AUD-151/168` | `AUD-326/AUD-327` usw. | **Korrektur von 3 verkürzten Schreibweisen** (`-NNN` ohne Präfix wurde von der Ersetzung nicht erfasst) |
| `AUDIT_TRACEABILITY.md:433`, `wp5-04-widersprueche.md:88` | `AUD-2026-09-026…043` | `AUD-2026-09-030…043` | **O-2**: `026` war nie vergeben |
| `AUDIT_EXTERNAL_INTEGRATIONS.md:738,935`; `AUDIT_NATIVE_PLUGINS.md` (4); 4 Evidenzdateien | `#1004`, `#1005`, `#1118` | `#1004` (PR), `#1005` (PR), `#1118` (PR) | **O-4**: als **PR-Nummern** gekennzeichnet; `#1003` und `#932` sind echte Issues und blieben unverändert |

**Gesamt: 26 Zeilen in 1 Datei geändert. Keine weiteren Reparaturen vorgenommen.**

### 12.2 Geprüft, ohne Reparatur (Bestätigung)

| Prüfung | Ergebnis |
|---|---|
| **Repo-weite ID-Eindeutigkeit** | **0 doppelte IDs.** Alle 285 IDs sind genau **einmal** definiert (Zählung über alle 9 Reports, Finding-Tabellen-Zeilen mit ≥5 Spalten). Verifikation: §12.2a. |
| **Dangling `AUD-2026-09-NNN`** | **0.** Jede referenzierte ID existiert als Definition. Der zuvor dangling Bereichsverweis `026…043` wurde auf `030…043` korrigiert (O-2). |
| **Doppelte IDs 240/241 repo-weit** | **0.** `AUDIT_FRONTEND_STATIC.md` enthält keine `AUD-2026-09-2[4-6]NN` mehr; WP-6a (`AUDIT_SECURITY.md:64-65`) und `AUDIT_EVIDENCE/secret-incident-2026-09-30.md:461-462` unverändert. |
| **Verweise außerhalb `docs/audit/2026-09/`** | **0** — keine Datei im Repo außerhalb des Audit-Ordners referenziert eine `AUD-2026-09-NNN`. |
| **`CR-NN`-Verweise** | **0 ungültig.** Alle Referenzen liegen in `CR-01`…`CR-47` (`09-evidence-register.md` verifiziert). |
| **Issue-Verweise (`#NNNN`)** | 28 Treffer ohne Treffer in `issue-inventory.md` geprüft. Ergebnis: **0 echte Defekte.** `#1004`, `#1005`, `#1118` sind **PR-/Merge-Nummern** (verifiziert über `git log`: `a6541783 …(#1003)(#1004)`, `abd61aed Fix/plugin interface bugs (#1118)`, `8ac16d0d …(#932)(#1013)`), keine Issues. `#002` in `AUDIT_UI_BROWSER.md:417,422` ist eine **AUD-ID-Kurzform** (`AUD-2026-09-002`), kein Issue. `#531` in `wp3-network-console-log.md:38` ist ein **Request-Zähler** („Requests #131–#531"), kein Issue. `#4` in `AUDIT_RELIABILITY.md:92` ist eine **Aufgabennummer** („Pflichtaufgabe #4"). |
| **Zählwerk je Report** | stimmt mit den Selbstaussagen überein: WP-4 41 ✅ · WP-6a 22 ✅ · WP-1c 30 ✅ · WP-2 24 ✅ · WP-6b 19 ✅ · WP-3b 25 ✅ · WP-3 25 ✅. |
| **Kodierung** | alle Dateien valides UTF-8; **0** Replacement-Char, **0** Decode-Fehler. Keine Reparatur. |

### 12.2a Offengelegte ID-Prüfung — vollständige Häufigkeitszählung

**285 IDs**, jede genau **einmal** definiert.

| Häufigkeit (Definitionen) | Anzahl IDs |
|---:|---:|
| **1×** | 285 |

**Belegung je Block:**

| ID-Bereich | Anzahl | WP |
|---|---:|---|
| `001–025` | 25 | `UI_BROWSER` |
| `030–067` | 38 | `EXTERNAL_INTEGRATIONS` |
| `070–093` | 24 | `EXTERNAL_INTEGRATIONS` |
| `100–206` | 107 | `DATA_MODEL` |
| `220–241` | 22 | `SECURITY` |
| `270–288` | 19 | `RELIABILITY` |
| `300–328` | 29 | `DATA_MODEL` |
| `330–350` | 21 | `TRACEABILITY` |

**Vollständige ID-Liste mit Häufigkeit:**

```
001×1    002×1    003×1    004×1    005×1    006×1    007×1    008×1    009×1    010×1    011×1    012×1    013×1    014×1    015×1
016×1    017×1    018×1    019×1    020×1    021×1    022×1    023×1    024×1    025×1    030×1    031×1    032×1    033×1    034×1
035×1    036×1    037×1    038×1    039×1    040×1    041×1    042×1    043×1    044×1    045×1    046×1    047×1    048×1    049×1
050×1    051×1    052×1    053×1    054×1    055×1    056×1    057×1    058×1    059×1    060×1    061×1    062×1    063×1    064×1
065×1    066×1    067×1    070×1    071×1    072×1    073×1    074×1    075×1    076×1    077×1    078×1    079×1    080×1    081×1
082×1    083×1    084×1    085×1    086×1    087×1    088×1    089×1    090×1    091×1    092×1    093×1    100×1    101×1    102×1
103×1    104×1    105×1    106×1    107×1    108×1    109×1    110×1    111×1    112×1    113×1    114×1    115×1    116×1    117×1
118×1    119×1    120×1    121×1    122×1    123×1    124×1    125×1    126×1    127×1    128×1    129×1    130×1    131×1    132×1
133×1    134×1    135×1    136×1    137×1    138×1    139×1    140×1    141×1    142×1    143×1    144×1    145×1    146×1    147×1
148×1    149×1    150×1    151×1    152×1    153×1    154×1    155×1    156×1    157×1    158×1    159×1    160×1    161×1    162×1
163×1    164×1    165×1    166×1    167×1    168×1    169×1    170×1    171×1    172×1    173×1    174×1    175×1    176×1    177×1
178×1    179×1    180×1    181×1    182×1    183×1    184×1    185×1    186×1    187×1    188×1    189×1    190×1    191×1    192×1
193×1    194×1    195×1    196×1    197×1    198×1    199×1    200×1    201×1    202×1    203×1    204×1    205×1    206×1    220×1
221×1    222×1    223×1    224×1    225×1    226×1    227×1    228×1    229×1    230×1    231×1    232×1    233×1    234×1    235×1
236×1    237×1    238×1    239×1    240×1    241×1    270×1    271×1    272×1    273×1    274×1    275×1    276×1    277×1    278×1
279×1    280×1    281×1    282×1    283×1    284×1    285×1    286×1    287×1    288×1    300×1    301×1    302×1    303×1    304×1
305×1    306×1    307×1    308×1    309×1    310×1    311×1    312×1    313×1    314×1    315×1    316×1    317×1    318×1    319×1
320×1    321×1    322×1    323×1    324×1    325×1    326×1    327×1    328×1    330×1    331×1    332×1    333×1    334×1    335×1
336×1    337×1    338×1    339×1    340×1    341×1    342×1    343×1    344×1    345×1    346×1    347×1    348×1    349×1    350×1
```

**Prüfkriterien und Ergebnis:**

| Kriterium | Methode | Ergebnis |
|---|---|---|
| Doppelte IDs | Definition = Tabellenzeile mit `| AUD-… |` unter einer `\| ID \|`-Kopfzeile, ≥5 Spalten; über alle 9 Reports gruppiert | **0** (max. Häufigkeit = 1) |
| Dangling IDs | jede `AUD-2026-09-NNN`-Referenz in allen 41 `.md`-Dateien gegen die Definitionsmenge geprüft | **0** |
| Anzahl Findings | Zeilen je Report gegen die Selbstaussage im jeweiligen Report | **unverändert**, siehe Tabelle |
| Verlorene IDs | Vergleich der belegten ID-Menge vor/nach der Umnummerierung | **0 verloren, 0 hinzugefügt** (285 = 285) |

### 12.3 Nicht reparierte Probleme — mit Begründung

| Problem | Warum nicht repariert |
|---|---|
| ~~Dangling `AUD-2026-09-026…043`~~ | **BEHOBEN (O-2)** — korrigiert auf `030…043`. |
| **`AUD-2026-09-300`-Zeilenangaben im Evidenzordner** | `wp3b-*.md` referenzieren **keine** eigenen 24x/25x/26x-IDs (geprüft) ⇒ nichts nachzuziehen. |
| **Zeilennummern-Abweichungen** (4 Fälle, s. §12.4) | belegt, aber **in 3 Fällen liegt der Inhalt in einem Nachbarbereich** und in 1 Fall (`AUD-2026-09-345`) ist die Angabe **nach Nachprüfung korrekt** — siehe O-3. |
| **Originalreports inhaltlich vereinheitlichen** | ausdrücklich untersagt: die ursprüngliche Einstufung und Formulierung des jeweiligen Audit-Agenten **muss nachvollziehbar bleiben**. Alle Normalisierungen stehen ausschließlich **hier**. |

### 12.4 Stichproben-Verifikation der Belegbarkeit

**39 Findings** geprüft (Soll: ≥ 20) — alle 14 Critical und eine Auswahl der
High je WP, plus WP-3b nach der Umnummerierung.
Prüfkriterien: Datei existiert · Zeile existiert · Inhalt passt zum Kurztitel.

| Ergebnis | Anzahl | Bedeutung |
|---|---:|---|
| **belegt** | **39** | Datei, Zeile und Inhalt stimmen mit dem Kurztitel überein |
| davon mit **ungenauer Zeilenangabe** | 4 | Inhalt passt, die genannte Zeile ist ein Nachbarbereich |
| **Phantom-Finding** | **0** | kein Fall: keine Datei fehlt, keine Zeile liegt außerhalb der Datei |
| **veraltete Zeilennummer (Phantom-Inhalt)** | **0** | in keinem Fall passt der Dateiinhalt **nicht** zum Kurztitel |

**Prüftabelle (Auszug — vollständige Liste in der Gate-Logdatei):**

| ID | angegebener Ort | Datei | Zeile | Inhalt passt | Urteil |
|---|---|---|---|---|---|
| 120 | `reqogniloom/celery.py:31-36` | ✅ | ✅ | ✅ `Queue('default')`…`Queue('llm')` | belegt |
| 121 | `reqogniloom/settings.py:817-830` | ✅ | ✅ | ✅ `CELERY_BEAT_SCHEDULE` | belegt |
| 122 | `scripts/backup.sh:84-87` | ✅ | ✅ | ✅ `exit 1` | belegt |
| 123 | `scripts/restore.sh:183,186,198-213` | ✅ | ✅ | ✅ `psql` | belegt |
| 124 | `scripts/restore.sh:49,116` | ✅ | ✅ | ✅ `backups` | belegt |
| 125 | `audit/archive.py:448` | ✅ | ✅ | ✅ `archive_lifecycle_manager` | belegt |
| 126 | `settings.py` (live `task_acks_late=False`) | ✅ | ✅ | ✅ **`task_acks_late` fehlt repo-weit** (Negativbefund = der Befund) | belegt |
| 127 | `scripts/restore.sh:183` | ✅ | ✅ | ✅ `--clean` | belegt |
| 052 | `llm_adapter/providers.py:1080` | ✅ | ✅ | ✅ `claude-3-opus-20240229` | belegt |
| 053 | `llm_adapter/providers.py:1333` | ✅ | ✅ | ✅ `gpt-4` | belegt |
| 055 | `llm_adapter/providers.py:1100,1347,1689` | ✅ | ✅ | ✅ Client-Konstruktion **ohne** `max_retries=`-Override | belegt (Zeilenangabe = Client-Init) |
| 057 | `llm_adapter/providers.py:1215,…` | ✅ | ✅ | ✅ `json.loads` | belegt |
| 058 | `llm_adapter/providers.py:1663,2014` | ✅ | ✅ | ✅ `azure` | belegt |
| 061 | `llm_adapter/providers.py:390,413,438,455` | ✅ | ✅ | ✅ `42`, `120` | belegt |
| 062 | `llm_adapter/router.py:286-292` | ✅ | ✅ | ✅ `record_token_usage` | belegt |
| 066 | `llm_adapter/dispatcher.py:149-152` | ✅ | ✅ | ✅ `pending` | belegt |
| 220 | `…/wp1d-auth-pagination-filter-errors-live.json:2246` | ✅ | ✅ | ✅ `reqlo_`-Key (Länge stimmt) | belegt |
| 221 | `mcp_server/views.py:272` | ✅ | ✅ | ✅ `check_mcp_rate_limit(request)` | belegt |
| 222 | `auth_tenancy/workspace_scope.py:114` | ✅ | ✅ | ✅ Workspace-Fence | belegt |
| 223 | `reqogniloom/urls.py:33` | ✅ | ✅ | ✅ `path("admin/", admin.site.urls)` | belegt |
| 225 | `.github/workflows/docker-publish.yml:42-185` | ✅ | ✅ | ✅ `uses:` | belegt |
| 226 | `reqogniloom/settings.py:143-160` | ✅ | ✅ | ✅ CORS-Settings | belegt |
| 150 | `traceability/audit/hierarchy.py:172-186` | ✅ | ✅ | ✅ `PARENT_TO_CHILD_LINK_TYPES` / `CHILD_TO_PARENT_LINK_TYPES` | belegt |
| 151 | `application/reqif_import_service.py:886-897` | ✅ | ✅ | ✅ `TraceLink.objects.get_or_create` **ohne** `validate_link_pair` | belegt |
| 152 | `icd/traceability_connector.py:82-87` | ✅ | ✅ | ✅ `create_trace_link(...)` — **kein `validate*`-Aufruf in der ganzen Datei** | belegt |
| 160 | `presets/registry.py:13` | ✅ | ✅ | ✅ „Single Source of Truth"-Docstring | belegt |
| 161 | `attribute_definitions/stage_matrix.py:40-47` | ✅ | ✅ | ✅ `stage_mandatory` | belegt |
| 162 | `presets/gate.py:536-549` | ✅ | ✅ | ✅ `except Exception` | belegt |
| 167 | `application/import_service.py:714-722` | ✅ | ✅ | ✅ `current_state` | belegt |
| 168 | `application/reqif_import_service.py:791-793` | ✅ | ✅ | ✅ `current_state` | belegt |
| 345 (WP-5, ehem. 185) | `docs/se/traceability-matrix.md:331` | ✅ | ✅ | ✅ `REQ-L2-BL-011` = „Not Implemented", Kind von `REQ-L1-046` (`:144`) | **belegt — Angabe korrekt** (siehe O-3) |
| 348 (WP-5, ehem. 188) | `docs/se/traceability-matrix.md:114` | ✅ | ✅ | ✅ REQ-L1-016 | belegt |
| 300 | `BaselinesView/BaselinesPanels.tsx:57` | ✅ | ✅ | ✅ `t(` | belegt |
| 301 | `test/i18n-parity.test.ts:186` | ✅ | ✅ | ✅ `MISSING_KEY_BASELINE = 116` | belegt |
| 306 | `utils/asilUtils.ts:62` | ✅ | ✅ | ✅ Hex-Palette | belegt |
| 309 | `UserProfileSettings/ApiKeysSection.tsx:224` | ✅ | ✅ | ✅ `keys.map` ohne Virtualisierung | belegt |
| 324 | `api/llm-settings.ts:22` | ✅ | ✅ | ✅ `LlmProvider`-Union **ohne** `"azure"` | belegt (Negativbefund = der Befund) |
| 270 | `audit/archive.py:448` | ✅ | ✅ | ✅ `@shared_task(name=…)` | belegt |
| 282 | `application/adr_service.py:562` | ✅ | ✅ | ✅ `WorkflowFacade().transition(...)` **ohne** `expected_version` | belegt |

**3 Findings mit ungenauer Zeilenangabe** (Inhalt korrekt, Zeile ist Nachbarbereich)
+ 1 Fall (`AUD-2026-09-345`) nach Nachprüfung als **korrekt** bewertet (O-3):

| ID | angegeben | tatsächlich | Bewertung |
|---|---|---|---|
| 055 | `providers.py:1100,1347,1689` | genau diese Zeilen (Client-Konstruktion) | Zeile korrekt, **Aussage** betrifft fehlendes `max_retries=` |
| ~~185 (WP-5)~~ → 345 | `traceability-matrix.md:331` | Zeile 331 = `REQ-L2-BL-011` = „Not Implemented", Kind von `REQ-L1-046` (`:144`) | **ERLEDIGT (O-3): die Angabe war korrekt.** Mein ursprünglicher Verdacht „veraltet" ist widerlegt — der Widerspruch `Implemented` (Eltern) vs. `Not Implemented` (Kind) ist genau der Befund. |
| 324 | `llm-settings.ts:22` | genau Zeile 22 | Zeile korrekt, **Negativbefund** (`azure` fehlt) |
| 282 | `adr_service.py:562` | genau Zeile 562 | Zeile korrekt, **Negativbefund** (`expected_version` fehlt) |

**Ergebnis: 0 Phantom-Findings, 0 Phantom-Inhalte.** Alle 39 Stichproben sind
belegbar. Der Fall `AUD-2026-09-185` (WP-5, inzwischen `AUD-2026-09-345`)
wurde **nach Nachprüfung als korrekt bewertet** — die Angabe `matrix:331` zeigt
auf `REQ-L2-BL-011` = „Not Implemented", das Kind von `REQ-L1-046`. Genau dieser
Widerspruch ist der Befund. Siehe O-3; am Finding wurde nichts geändert.

### 12.5 Offene Punkte für den User

| # | Offener Punkt | Entscheidungsbedarf |
|---|---|---|
| ~~**O-1**~~ | ~~**ID-Kollisionen K2/K3**~~ | **ERLEDIGT:** Regel „früherer Commit behält" vom Orchestrator entschieden und angewandt. WP-4 `150–153 → 325–328`, WP-5 `170–190 → 330–350`. Verifikation: 0 Duplikate. (§9.2) |
| ~~**O-2**~~ | ~~`AUD-2026-09-026…043`~~ | **ERLEDIGT:** auf `AUD-2026-09-030…043` korrigiert (2 Fundstellen). |
| ~~**O-3**~~ | ~~Veraltete Zeilenangabe `AUD-2026-09-185`~~ | **ERLEDIGT mit Gegenbefund:** Die Angabe `matrix:331` war **korrekt** — Zeile 331 der Matrix ist `REQ-L2-BL-011` = „Not Implemented", das Kind von `REQ-L1-046` (Zeile 144). Genau dieser Widerspruch ist der Befund. **Meine frühere Diagnose „veraltet" war falsch**; es wurde **nichts** am Finding geändert. |
| ~~**O-4**~~ | ~~PR-Nummern `#1004`, `#1005`, `#1118`~~ | **ERLEDIGT:** an 10 Fundstellen als PR-Nummer gekennzeichnet. `#1003` und `#932` sind echte Issues (im Inventar) und blieben unverändert. |
| **O-5** | **Doku-Drift** (§10): Tools 215→219, Gruppen 31→35, APIViews 67→76, Compose-Services 8→15, React 18→19, E2E 111→54 | Soll `AGENTS.md`/`README.md` korrigiert werden? Außerhalb des Auftragsumfangs (Dokumentation, kein Produkt-Code). |
| **O-6** | **`CR-30`-Zahl** (463 vs. 511 vs. 443) | Welche Zahl soll als kanonisch im Vor-Audit stehen? Empfehlung: **443** mit der in C10 offengelegten Methode. |
| **O-7** | **Historie-Entscheidung** zum Secret-Leak (`AUD-2026-09-220`) | WP-6a empfiehlt Option A (`filter-repo`, kein Force-Push nötig, da `3dcc80d8` nie gepusht wurde) — **nicht ausgeführt**. |

---

## 13. Reproduzierbarkeit

Alle Prüfungen dieses Gates sind deterministisch und ohne Spezialwissen wiederholbar:

| Prüfung | Kommando / Ort |
|---|---|
| ID-Inventar + Kollisionen | `rg -n '^\|\s*[\x60*\s]*AUD-2026-09-\d{3}' docs/audit/2026-09/` |
| Registriertes CR-Spektrum | `rg -o 'CR-\d{2}' docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md` |
| Issue-Basis | `rg -o '^\| #\d+' docs/audit/2026-09/AUDIT_EVIDENCE/issue-inventory.md` |
| C1/C2 (i18n) | `frontend/src/test/i18n-parity.test.ts:80-111,186,219` |
| C3 (Hex) | eigene Messung, Kommentare gestrippt / Strings erhalten, `ui-ratchet.test.ts:48` |
| C4 (E2E-Selektoren) | `rg --fixed-strings <selektor> frontend/src e2e/` |
| C6 (Tool-Registry) | `AUDIT_EVIDENCE/wp1a-mcp-registry-manifest-219.json` |
| C7 (ViewSets/APIViews) | `backend/rest_api/urls.py` (`router.register`), `backend/rest_api/**` (APIView-Klassen) |
| C8 (Embedding) | `backend/persistence/embedding_dimensions.py`, `models.py:1602,1946` |
| C9 (Celery) | `backend/reqogniloom/celery.py:45`, `backend/audit/apps.py:36`, `settings.py:817-830` |
| C10 (CI) | `.github/workflows/ci.yml:43-55` + Testdefinition-Zählung je App |
| C11 (DB-Rollen) | `AUDIT_EVIDENCE/stack-db-redis.txt`, `AUDIT_EVIDENCE/wp6a-rls-db-roles.md:50-58` |

**Kein Produkt-Code wurde geändert.** Sämtliche Reparaturen betreffen ausschließlich
Dokumentation unter `docs/audit/2026-09/`.


---

## 14. Erkannte Prozessdefekte dieses Audits

Dieser Abschnitt ist **kein** Produktbefund und **nicht** Teil der 280 Findings.
Er dokumentiert Mängel des **Auditprozesses selbst**, die beim Konsistenz-Gate
aufgefallen sind. Sie sind hier offengelegt, weil sie die Aussagekraft des
Audits einschränken — nach dem gleichen Grundsatz, mit dem der Audit die
Produktdefekte offenlegt.

| # | Prozessdefekt | Schwere | Beleg | Status |
|---|---|---|---|---|
| **P-1** | **Das Audit committete selbst ein live gültiges API-Key** | **Critical** | `AUD-2026-09-220` (Fundort `AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2246`, Commit `3dcc80d8`), Prozessursache `AUD-2026-09-239` | **Key widerrufen** 2026-09-30 (HTTP 204, `revoked_at = 2026-09-30 19:07:05+00`); Arbeitsbaum redigiert; **Git-Historie offen** — `3dcc80d8` wurde nie gepusht, Option A (`filter-repo`) empfohlen, **nicht ausgeführt** (offener Punkt O-7) |
| **P-2** | **Zwei Agenten schrieben parallel in dieselbe Datei** | Medium | `AUDIT_EXTERNAL_INTEGRATIONS.md` wurde von WP-1a (`cd002d94`, +324 Zeilen), WP-1d (`3dcc80d8`, +689) und WP-1b (+239, im Gate-Commit `33237041`) beschrieben. Der Bericht hält fest (`:12-14`), jeder Agent schreibe ausschließlich seinen Abschnitt und IDs würden „nicht überschrieben". **Status heute: alle drei Abschnitte vorhanden** (`## WP-1a` :24, `## WP-1d` :329, `## WP-1b` :1017) — der zwischenzeitliche Verlust des WP-1b-Abschnitts wurde beim Append erkannt und wiederhergestellt. | **behoben** (inhaltlich vollständig), aber der Mechanismus ist ungeschützt |
| **P-3** | **27 ID-Kollisionen** (2 briefedet + 25 nicht briefedet) | Medium | K1 `240/241` (WP-3b × WP-6a), K2 `150–153` (WP-2 × WP-4), K3 `170–190` (WP-4 × WP-5). Ursache: **blockweise ID-Vergabe ohne Reservierung zwischen parallel laufenden Agenten**; jeder Agent vergab „fortlaufend ab seinem Blockanfang", ohne den Gesamtraum zu kennen. | **behoben** (0 Duplikate, §12.2a) |
| **P-4** | **ID-Block `050/051` doppelt vergeben** (dieselbe Ursache wie P-3) | Low | `AUDIT_EXTERNAL_INTEGRATIONS.md` führt `050/051` im WP-1b-Abschnitt, obwohl der Block für WP-1a reserviert war; beide Reports liegen in derselben Datei, wodurch die Doppelvergabe nicht als Dateikonflikt auffiel. | **behoben** (IDs existieren nur einmal, §12.2a) |
| **P-5** | **Messfehler, die zu Phantom-/Über-Befunden führten — und aktiv korrigiert wurden** | Info | (a) WP-3: 441 Hex-Literale → selbst korrigiert auf **0**. (b) WP-3b: i18n-Lücke **112 → 116**. (c) WP-3b: „0 stale E2E-Selektoren" → **3 verifiziert stale**. Alle drei Korrekturen sind im jeweiligen Report dokumentiert und wurden vom Gate nachgeprüft (C1, C3, C4). | **behoben** |

### 14.1 Bewertung von P-5 — ehrliche Einordnung der Korrekturen

Die drei Korrekturen aus P-5 wirken in **drei verschiedene Richtungen**. Das ist
wichtig, weil eine Korrektur, die nur in eine Richtung wirkt, kein Qualitäts-
nachweis ist.

| Korrektur | Richtung | Wirkung auf die Befundmenge | Einordnung |
|---|---|---|---|
| WP-3: Hex-Literale **441 → 0** | **nach unten** | entfernt einen **Phantom-Befund** (Messfehler-Überzählung) | War ein **Fehlalarm**. Der Befund `AUD-2026-09-021` wurde als **WIDERLEGT** geführt, nicht weggelassen — die Fehlalarm-Historie bleibt sichtbar. |
| WP-3b: i18n **112 → 116** | **nach oben** | echte Lücke ist **4 Schlüssel größer** als berichtet | War eine **Unterzählung**. WP-3 hatte Testdateien mitgescannt bzw. `<Trans i18nKey>` übersehen. Die höhere Zahl deckt sich exakt mit der im Repo eingefrorenen `MISSING_KEY_BASELINE = 116`. |
| WP-3b: stale Selektoren **0 → 3** | **nach oben** | 3 zusätzliche Defekte | War eine **Falschnegativ-Aussage**. WP-3 hatte im Browser nur die tatsächlich gerenderten Screens geprüft. |

**Gesamtbewertung, ohne die Findings kleinzureden:**

* **Zwei der drei Korrekturen haben die Befundmenge erhöht** (i18n +4,
  stale Selektoren +3). Das ist das wichtigere Signal: die Korrekturen waren
  nicht geschönend, sie haben **Defekte sichtbar gemacht**, die der erste Durchgang
  übersehen hatte.
* **Eine Korrektur hat die Befundmenge reduziert** (441 → 0). Das war ein
  Phantom-Befund. Dass er **korrigiert statt verschwiegen** wurde, ist positiv —
  die Verfehlung ist als `WIDERLEGT` im Register sichtbar und nicht aus der
  Zählung entfernt worden.
* **Die Fehlerklasse ist systematisch, nicht zufällig.** WP-3b hat eine
  Methodik-Sektion (§0) mit genau den Schutzmaßnahmen gegen diese Fehlerklasse
  eingeführt (Block-Kommentare, `//`-Kommentare, Testdatei-Trennung,
  Regex-Fehlertreffer). Das ist die richtige Reaktion — aber sie zeigt, dass
  die erste Messung eines Audits ohne Vorlauf **nicht belastbar** ist.
* **Für die Belastbarkeit des Gesamtergebnisses heißt das:** Die Zahlen in
  diesem Register sind das Ergebnis **einer zweiten, methodisch korrigierten
  Messung** (WP-3b), nicht der ersten. Wo beide Agenten dasselbe Objekt gemessen
  haben (i18n-Lücke, Hex-Literale, E2E-Selektoren), ist die **WP-3b-Zahl**
  maßgeblich; das ist in C1, C3 und C4 so festgehalten.
* **Was das nicht heißt:** Andere WPs haben keinen Methodik-Nachtrag. Für die
  WPs ohne zweite Messung ist die Validität der Zahlen **nicht** durch eine
  unabhängige Gegenmessung abgesichert — sie stammen aus **einer** Messung.
  Das ist eine **Restunsicherheit dieses Audits**, keine Feststellung zu einem
  Produktdefekt.

### 14.2 Lehre für den nächsten Audit

1. **ID-Bereiche vor dem Dispatch reservieren.** Der Orchestrator weist jedem
   Agenten vor dem Start einen exklusiven, nicht überlappenden ID-Block zu und
   schreibt ihn in den Auftrag. Dieser Audit hat stattdessen Blöcke parallel
   vergeben → 27 Kollisionen (P-3).
2. **Ein Report pro Agent.** P-2 entstand, weil drei Agenten dieselbe Datei
   beschrieben. WP-1a/1b/1d sollten drei getrennte Reports bekommen.
3. **Messmethoden-Protokoll verpflichtend.** Jeder Agent legt vor der ersten
   Zählung fest, wie Testdateien, Kommentare und Strings behandelt werden
   (WP-3b §0 ist das vorbildliche Muster).
4. **Evidenz-Dateien auf Geheimnisse prüfen, bevor sie committet werden.**
   P-1 ist der teuerste Prozessdefekt dieses Audits: ein durch das Audit
   selbst erzeugter, live gültiger Produktionszugang.
5. **Zweite Messung für jede Zahl, die später zitiert wird.** Besonders für
   Zahlen, die in andere Reports übernommen werden (hier: 112/116, 441/37,
   0/3) — sonst wandert der erste Messfehler durch das gesamte Audit.