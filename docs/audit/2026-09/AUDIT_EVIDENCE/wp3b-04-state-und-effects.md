# WP-3b Evidence 04 — State-Management, Effects, Render-Performance

## 1. State-Architektur (Bestandsaufnahme)

| Mechanismus | Vorkommen (prod + test) | Ort |
|---|---:|---|
| `createContext` | 12 | `src/context/*` + lokale Provider |
| `useReducer` | **0** | — |
| `useEffect` | 326 | verteilt |
| `useQuery` (@tanstack/react-query) | 33 | `src/queries/{requirements,testcases}.ts` + 15 `use*Data.ts` |
| `useMutation` | 25 | dito |
| `useVirtualizer` (@tanstack/react-virtual) | 1 | `components/shared/WorkspaceTree/workspace-tree.tsx:540` |
| `AbortController` | 6 | `api/client.ts:83,123,267`, `context/AuthContext.tsx:154,237,238,239,300,322,323` |
| `debounce` | 28 | div. |

**Modell:** Context für app-weite Zustände (Auth, Workspace, Theme, Sprache) +
TanStack Query für Server-State + `useState` für lokalen UI-State.
Kein Reducer, keine externe State-Library. Keine doppelte Wahrheitsquelle
zwischen Context und Query-Cache für denselben Zustand festgestellt.

`src/queries/queryClient.ts` + `src/queries/query-error.ts` bilden die
Server-State-Schicht; 15 `use*Data.ts`-Adapter (z. B.
`components/RequirementEditors/useRequirementData.ts`) kapseln sie pro
Artifact-Familie.

## 2. Request-Waterfall — statische Erklärung des 453-Request-Befunds

`frontend/src/api/requirements.ts:143-157`:

```ts
      page_size: "100",
    …
    let pageCount = 0;
    while (nextUrl && pageCount < 100) {
      pageCount += 1;
      …
```

* Jeder Listen-Abruf exhaustiert die serverseitige Pagination **bis zur
  100-Seiten-Grenze** → bis zu 10 000 Datensätze, **im Client**.
* Die Schleife läuft komplett vor dem ersten Render → der erste Render
  wartet auf die *letzte* Seite (Waterfall-Kaskade, kein progressives Rendering).
* Die Funktion hängt an `useRequirementsList()`
  (`frontend/src/queries/requirements.ts:38`, `enabled: !!workspaceId`),
  erreichbar über `useRequirementData()`
  (`components/RequirementEditors/useRequirementData.ts:51`).
* Dieselbe Muster-Klasse existiert parallel in `api/adrs.ts`,
  `api/traceability.ts`, `api/tracelinks.ts` (`limit`/`offset`-Parameter
  gesetzt, aber keine clientseitige Abbruchlogik sichtbar).

Addiert man die 15 datenladenden Hooks über die Artifact-Familien ergibt
sich die im WP-3-Browser-Audit gemessene Request-Menge pro Dashboard-Load.

**Geschlossene Teile:**
* `items[0]` existiert in **keiner** Produktionsdatei mehr
  (`grep -rn 'items\[0\]' frontend/src | grep -v test` → 0 Treffer).
  Die WP-3-Ursache „`getWorkspaceId(items[0])` (#1115)" ist damit behoben.
* `enabled: !!workspaceId` in den Query-Hooks verhindert ungekey-te Requests.

## 3. Virtualisierung / lange Listen

| Liste | virtualisiert | paginiert | filterbar |
|---|---|---|---|
| Workspace-Baum (`workspace-tree.tsx:540`) | **ja** (`useVirtualizer`) | n/a | n/a |
| API-Keys (`ApiKeysSection.tsx:224`, `keys.map(...)`) | nein | nein | **nein** |
| Anforderungsliste | nein (fetch-seitig gedeckelt) | implizit | ja |
| Audit-Findings | nein | nein | nein |

`@tanstack/react-virtual` ist eine Abhängigkeit, wird aber an **genau einer**
Stelle verwendet. Bei ~190 API-Keys (WP-3-Messung) rendert
`ApiKeysSection.tsx:224` alle Zeilen ohne Fensterung.

## 4. Kandidaten für Race Conditions (nicht als Finding geführt)

* `AbortController` existiert ausschließlich für Auth-Refresh/Timeout und
  Login-Abbruch. Für Suchfelder gibt es Debounce (28 Stellen), aber kein
  Request-Cancelling. Ob ein schnelles Tippen tatsächlich eine ältere Response
  später treffen lässt, ist **statisch nicht entscheidbar** — die
  React-Query-Cache-Key-Strategie könnte es bereits verhindern.
  → **Confidence 65 %, nicht als Finding geführt.**
* Keine `Promise.all`-Wasserkaskaden in `api/` gefunden, die ein N+1 pro
  Listenelement erzeugen.

## 5. Bundling

`mermaid` und `fabric` werden **dynamisch** importiert:

```
components/canvas/CanvasEditor.tsx:471        const fabric = await import("fabric");
components/DiagramView/DiagramDetailView.tsx:221  const mermaid = (await import("mermaid")).default;
```

`@xyflow/react` + `@dagrejs/dagre` werden regulär importiert (DiagramGraphEditor).
Keine ungenutzte große Bibliothek nachweisbar. Bundle-Größe wurde **nicht**
gemessen (kein Build-Lauf in dieser Analyse) → **BLOCKED**, siehe Bericht §13.

## 6. Konkrete Stellen mit Beleg

| Stelle | Befund |
|---|---|
| `api/requirements.ts:143` | `page_size: "100"` |
| `api/requirements.ts:156` | `while (nextUrl && pageCount < 100)` |
| `api/requirements.ts:372-375` | `/requirements/similar/…?limit=10` — eigener, ungeteilter Pfad |
| `queries/requirements.ts:39` | `queryKey: [...requirementKeys.list(workspaceId ?? ""), { includeDeleted }]` |
| `queries/requirements.ts:42` | `enabled: !!workspaceId` |
| `components/UserProfileSettings/ApiKeysSection.tsx:224` | `{keys.map((key) => (` — keine Paginierung |
| `components/shared/WorkspaceTree/workspace-tree.tsx:540` | `const rowVirtualizer = useVirtualizer({` — einzige Virtualisierung |
| `context/AuthContext.tsx:237-239` | einziger Nutzer-Abbruch-Pfad (`loginAbortController`) |