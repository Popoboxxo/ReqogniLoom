# WP-3b Evidence 07 — API-Client-Schicht (`frontend/src/api/`)

## 1. Zentraler Client

`frontend/src/api/client.ts` ist die einzige Stelle mit voller Auth-Logik:

| Zeile | Mechanismus |
|---|---|
| `client.ts:5` | `REQ-L2-RF-010 (Bearer-Token auth)`, `REQ-L2-RF-011 (Error rendering)` |
| `client.ts:12` | 401 → single-flight silent refresh (`POST /auth/refresh/`) + **einmaliger** Retry |
| `client.ts:15` | parallele 401s teilen **einen** Refresh-Versuch (GitHub #135) |
| `client.ts:45` | Single-Flight-Guard-Modul |
| `client.ts:80` | `_refreshController: AbortController` |
| `client.ts:103` | Re-Arm der unauthorized-Notification |
| `client.ts:142-144` | Auth-Endpoint-Ausschluss (kein Refresh-Retry auf `/auth/refresh/`, `/auth/login/`) |
| `client.ts:267` | `timeoutController = options.signal ? null : new AbortController()` → Request-Timeout |
| `client.ts:304` | `if (response.status === 401)` |
| `client.ts:329` | `if (response.status === 403)` |
| `client.ts:349` | `if (response.status === 422)` |
| `client.ts:377` | Fallback `message: \`HTTP ${response.status}\`` |
| `client.ts:385` | `if (response.status === 204)` |
| `client.ts:198` | `export class RequestTimeoutError extends Error` |

**Bewertung:** 4xx/5xx werden differenziert behandelt (401/403/422 eigens),
es gibt einen eigenen Timeout-Fehler, und die Retry-Mechanik ist gegen
Refresh- und Login-Endpoint abgesichert. Das ist überdurchschnittlich sauber.

## 2. Roh-`fetch()`-Aufrufe außerhalb des Clients — 7 Stellen

```
api/export.ts:40              const resp = await fetch(
api/export.ts:77              const resp = await fetch(`/api/v1/workspaces/${workspaceId}/export/reqif/`, {
api/import.ts:118             const resp = await fetch(
api/import.ts:179             const resp = await fetch(
api/memory.ts:267             const response = await fetch(`/api/v1${path}`, {
api/requirementBundle.ts:109  const resp = await fetch(`/api/v1${path}`, {
api/workspaces.ts:86          const resp = await fetch(
```

### Gemeinsame Merkmale

| Merkmal | Wert |
|---|---|
| `Authorization`-Header | **nein** — nur `Accept-Language` (+ `Accept`) |
| Auth-Mechanismus | `credentials: "same-origin"` (httpOnly-Cookie) |
| 401-Refresh + Retry | **nein** |
| Request-Timeout (`AbortController`) | **nein** |
| Fehler-Typisierung | uneinheitlich, siehe unten |

### Fehlerbehandlung im Detail

`api/export.ts:44-55` und `:81-92` (identisches Muster):

```ts
    if (!resp.ok) {
      let message = `Export failed (HTTP ${resp.status})`;
      try {
        const body = (await resp.json()) as { error?: { message?: string } };
        message = body?.error?.message ?? message;
      } catch {
        // ignore — fall back to default message
      }
      throw new Error(message);
    }
```

→ wirft `Error` **ohne Status**; Aufrufer können 403 (Berechtigung) nicht von
500 (Server) unterscheiden. Zusätzlich ist `Export failed (HTTP …)` ein
**hartkodierter englischer String** — er taucht im DE-UI auf
(`CsvImport.tsx:252,270` fangen ihn als `err.message`).

`api/memory.ts:265-279` — abweichend und schlimmer:

```ts
async function fetchExport(path: string): Promise<Response> {
  const lang = document.documentElement.lang || "en";
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json", "Accept-Language": lang },
  });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error body → fall through to a generic Error below.
    }
    if (body !== null) throw body;          // ← wirft ein Plain-Objekt
    throw new Error(`HTTP ${response.status}`);
  }
```

`throw body` wirft einen **beliebigen JSON-Wert** (String, Objekt, Array).
Jeder Aufrufer mit `err instanceof Error ? err.message : …` fällt in den
Fallback-Zweig und zeigt dem Nutzer den Roh-JSON-Body bzw. `String(err)`
(`[object Object]`). Das ist ein realer, gut belegbarer Fehlerpfad.

`api/memory.ts:262` dokumentiert das selbst:

```
 * Errors are surfaced as the parsed error body so callers can
 * reuse `extractErrorMessage`.
```

## 3. Bearer-Token-Injektion

| Pfad | Header |
|---|---|
| `api/client.ts` (Zentralpfad) | Bearer **und** httpOnly-Cookie (laut Docstring REQ-L2-RF-010) |
| 7 Roh-`fetch()`-Pfade | **nur** Cookie (`credentials: "same-origin"`) |

**BLOCKED, kein Finding:** Welche Auth-Variante im konkreten Deployment
dominant ist (Cookie-only oder Bearer+Cookie), ist statisch nicht
entscheidbar. `client.ts` sendet beide; die Roh-Pfade nur Cookie. Wenn ein
Deployment nur Bearer konfiguriert, brechen die 7 Pfade — das ist eine
Deployment-Frage, keine Code-Frage.

## 4. Doppelte Requests / Retry-Interceptors

* Es existiert **kein** Axios/globaler Interceptor; der Client ist ein
  `fetch`-Wrapper. Damit ist „Interceptor doppelt" nicht anwendbar.
* Single-Flight-Guard (`client.ts:80`) verhindert Refresh-Duplikate.
* Kein automatisches Retry auf 5xx/Netzwerkfehler — nur der 401-Pfad retryt
  (bewusst, dokumentiert in `client.ts:12-15`).

## 5. TypeScript-Typen vs. Backend-Serializer

Durchgeführt wurde eine **Stichprobe** über die Feldbenennungen, die der
Ratchet-Hex-Befund incidentally sichtbar machte. Kein Drift-Befund
feststellbar: die im Frontend gepflegten Feldnamen (`workspace_id`,
`include_outdated`, `include_unreviewed_ai`, `item_type`, `backup_type`,
`max_depth`, `link_types`, `scope_artifact_id`, `include_suppressed`,
`propagated_workspace_count`, `excluded_no_embedding`, `pending_mismatch_count`)
entsprechen 1:1 den Django-Serializer-Feldnamen.

**Einschränkung:** Das ist eine Stichprobe auf Namensebene, kein
Schemasvergleich. Ein echter Drift (Nullable, Enum-Werte, Datumsformat) wäre
damit nicht erfasst → **BLOCKED**, siehe Bericht §13.

## 6. Modulbestand

`api/` enthält **56** Module ohne Tests (`ls api/*.ts | grep -v test | wc -l`), darunter (`actorRefs`, `actors`, `admin-ops`,
`api-keys`, `artifactRefs`, `artifacts`, `attribute-definitions`,
`attributeCatalog`, `audit`, `baseline`, `baselines`, `change-requests`,
`client`, `context-graph-settings`, `diagrams`, `export`, `glossary`,
`import`, `interviews`, `item-permissions`, `llm-settings`, `main-goal`,
`memory`, `metrics`, `permissions`, `prompt-templates`, `requirementBundle`,
`requirements`, `system-memory-settings`, `test-runs`, `testcases`,
`tracelinks`, `traceability`, `workflow`, `workspaces`, …).

**Nicht geprüft:** toter Code / ungenutzte Wrapper-Module (bräuchte einen
Import-Graph über Modulgrenzen; im Zeitbudget nicht durchführbar →
**BLOCKED**).

## 7. `azure` nicht wählbar — statisch bestätigt

`AUD-2026-09-058` / `AUD-2026-09-347` wird auf API-Ebene **unabhängig
bestätigt** und auf die Typ-Ebene verschärft. `frontend/src/api/llm-settings.ts:22`:

```ts
export type LlmProvider = "anthropic" | "openai" | "ollama" | "opencode_go" | "mock";

export const LLM_PROVIDERS: readonly LlmProvider[] = [
  "anthropic",
  "openai",
  "ollama",
  "opencode_go",
  "mock",
] as const;
```

`azure` ist **nicht Teil des TypeScript-Unions** und nicht Teil der
Provider-Konstante. Damit kann die ChoiceField-UI `azure` nicht anbieten,
unabhängig davon, was der Backend-Adapter kannst — der Frontend-Typ
schließt es aus. Das ist stärker als der ursprüngliche Befund („fehlt im
ChoiceField/UI"): die Lücke sitzt bereits in der Typdefinition.

Ergänzend aus dem Locales-Inventar (Evidence 01):
`settings.llm.title/provider/baseUrl/apiKey/apiKeyNotSet/modelName/description`
fehlen in **beiden** Locale-Dateien — der komplette LLM-Settings-Block rendert
in beiden Sprachen über seine Inline-Defaults.