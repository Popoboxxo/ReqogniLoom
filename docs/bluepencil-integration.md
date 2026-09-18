# bluepencil in ReqogniLoom integrieren

> **Status: Vorschlag.** Dieses Dokument ist ein Integrationsplan zur Review — es ändert **keinen**
> Code. Die Stufen sind so geschnitten, dass jede einzeln entschieden und einzeln gemessen werden
> kann. Anker-Strategie, Auth-Transport und Store-Entscheidung sind an diesem Repo geprüft, nicht
> angenommen.

Stand: geprüft gegen `Popoboxxo/ReqogniLoom` (Django 4.2 + DRF, React 18 + Vite, PostgreSQL, Redis,
Celery, docker-compose mit 5 Services, Woodpecker CI, Playwright-E2E) und bluepencil `main`
(`47f24f1` + die offenen PRs #8/#9).

**Grundsatz:** bluepencil ist eine *Schicht*, kein Service. Es braucht keinen eigenen Auth, keine
eigene Datenbank und keinen Build-Schritt im Wirt — es braucht **einen Script-Slot** und **einen
Store**, der den dokumentierten HTTP-Vertrag spricht.

---

## 0. Die eine Entscheidung, die alles andere bestimmt: welcher Store?

| | Option A — **DRF-Implementierung** (Produktpfad) | Option B — **Sidecar** (QS/Demo) |
|---|---|---|
| Was | neues Django-App `backend/review_notes/` mit ~6 Endpunkten | `node dist/server.js` als 6. Compose-Service |
| Mandantentrennung | **ja** — über eure RLS/TenantContext | **nein** — eine JSON-Datei, alle Workspaces teilen sie |
| Auth | euer JWT + Rollen + Audit | keine (der Sidecar kennt keine Nutzer) |
| Notizen im MCP-Server | **ja** — als eigene Tool-Gruppe für Agenten | nein |
| Aufwand | ~1–2 Tage inkl. Tests | ~1 Stunde |
| Wofür | das Produkt | „ich will es einmal in unserer App sehen" und Messungen (Stufe 2) |

**Empfehlung:** mit **B** anfangen, um die Schicht in der echten App zu sehen und zu messen (wie bei
der Vortragsseite: Stufe 2 = Parallelbetrieb), und **A** als den Weg bauen, der ausgeliefert wird.
Der Sidecar ist in einem Multi-Tenant-Produkt **keine** Dauerlösung: keine Nutzerprüfung, kein
Mandantenbezug, und ein einziger JSON-Store für alle. Das offen sagen, statt es „Pilot" zu nennen.

---

## 1. Der Script-Slot (einmalig, unvermeidbar)

`frontend/index.html` ist heute:

```html
<body>
  <div id="root"></div>
  <script type="module" src="/src/index.tsx"></script>
</body>
```

Dort darf **genau einmal** ein Slot hin — danach ist alles Weitere per Attribut/URL änderbar. Drei
Wege, in aufsteigender Sauberkeit:

1. **Build-Zeit (QS, heute):** `frontend/src/index.tsx` hängt den Tag nur an, wenn
   `import.meta.env.VITE_BLUEPENCIL === "1"`. Kostet drei Zeilen, gilt aber pro Build.
2. **nginx (`frontend/` Production-Target):** `sub_filter` fügt den Tag im `index.html` ein, sobald
   `auth_request` gegen Django „ist Reviewer" sagt. Laufzeit-Änderung ohne Rebuild, ohne dass der
   Tag je bei Endnutzern im HTML steht.
3. **Django liefert die SPA-Hülle** (Template statt statischem `index.html`) — der sauberste Ort für
   die Entscheidung, aber ein größerer Umbau.

Der Tag selbst (Element-Build + Loader liegen unter einem versionierten Pfad, `latest.json` daneben):

```html
<bluepencil-notes
    endpoint="/api/v1/bluepencil"
    headers-from="rfBluepencil.headers"
    gate="rfBluepencil.gate"
    route-from="rfBluepencil.routeFor"
    identity="rfBluepencil.identity"
    build-ref="rfBluepencil.buildRef"></bluepencil-notes>
<script src="/bluepencil/latest/attach.js"></script>
```

> **Stand nach dem Bugfix-PR [bluepencil#15](https://github.com/Popoboxxo/bluepencil/pull/15):** Dieses
> Snippet ist **wortgleich** das, was vorher stumm blieb. Der Loader-Tag ohne ein einziges `data-*`
> Attribut hing nicht an (Issue #11: die Erkennung verlangte mindestens einen bekannten Schlüssel),
> und `identity` als *globaler Pfad* war nicht vorgesehen (Issue #12). Beides ist behoben; die
> Gegenprobe lief in genau eurem Frontend: Tag zur Laufzeit nach `DOMContentLoaded` eingefügt →
> Element definiert, 1 Attach-Instanz, 3 API-Aufrufe alle 200, 2 Notizen im Round-Trip, 0 Long Tasks.
> Ein **später** ergänzter Tag wird außerdem von `bluepencilAttach.check()` aufgenommen — ohne Reload.

`endpoint` **root-relativ** lassen: dann ist es derselbe Origin wie die SPA, `fetch` schickt eure
Cookies automatisch mit (`credentials: "same-origin"` ist der Default) — und CORS entfällt komplett.

---

## 2. Die Host-Globale (das eigentliche Stück Arbeit, ~30 Zeilen)

```ts
// frontend/src/bluepencil/host.ts
import { readCookie } from "../api/client"; // existiert bereits und ist exportiert

export function installBluepencilHost(opts: {
  getToken: () => string | null;          // euer TokenManager hält es im Speicher
  isReviewer: () => boolean;              // Rolle/Feature-Flag im Wirt
  getIdentity: () => { id?: string; name: string };
  buildRef: () => string;
}): void {
  (window as any).rfBluepencil = {
    /**
     * Header als FUNKTION, nicht als Konstante: euer Token rotiert zur Laufzeit, und der
     * CSRF-Token ist ein Cookie. bluepencil ruft das pro Request auf.
     */
    headers: () => {
      const token = opts.getToken();
      const csrf = readCookie("csrftoken");
      return {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(csrf ? { "X-CSRFToken": csrf } : {}),   // Pflicht: POST/PATCH haben eure REQ-052-Prüfung
      };
    },
    /** Client-seitige Vorprüfung. Der echte Riegel muss serverseitig sein (siehe §3). */
    gate: () => opts.isReviewer(),
    /**
     * ReqogniLoom ist eine SPA: die Route ist die Location. Das Element wird genutzt, wenn der Wirt
     * präziser sein kann (Detail-Ansicht, die das Artefakt besitzt).
     */
    routeFor: (element?: Element) => {
      const scoped = element?.closest?.("[data-rf-view]") as HTMLElement | null;
      return scoped?.dataset.rfView ?? window.location.pathname;
    },
    identity: { getUser: opts.getIdentity },
    buildRef: () => opts.buildRef(),
  };
}
```

Aufruf in `App.tsx`/`AuthContext` **nach** dem Login (`setAuthToken`), Abbau beim Logout:
`delete (window as any).rfBluepencil` plus `document.querySelector("bluepencil-notes")?.remove()` —
sonst bleiben Marker eines abgemeldeten Nutzers stehen.

**Anker-Strategie:** ihr habt `data-testid` auf allen interaktiven Elementen (eure Konvention,
E2E-Pflicht) — und das ist **ab Werk** der Anker, den bluepencil bevorzugt: die Standard-Hooks sind
`["data-bluepencil", "data-testid"]` (geprüft in `src/core/anchor.ts`). Ihr müsst dafür **nichts**
konfigurieren. Ein Attribut `anchor-hooks` (inzwischen nachgereicht) existiert nur, wenn ein Wirt
*andere* stabile Haken hat oder die Priorität drehen will, z. B. `anchor-hooks="id,data-testid"`.

> Korrektur zu einer früheren Fassung dieses Dokuments: dort stand, `data-testid` sei über den Tag
> nicht nutzbar und das Attribut sei „der einzige echte Blocker". Das war falsch — es hätte genügt,
> die Standard-Hooks nachzusehen. Der Tag kann die Haken jetzt zusätzlich setzen, gebraucht wird es
> für euch aber nicht.

**Aussehen:** bluepencil stylt ausschließlich über CSS-Custom-Properties (`--bp-*`). Eine
`frontend/src/styles/bluepencil.css` mappt eure Tokens aus `styles/tokens.css` auf `--bp-accent`,
`--bp-surface`, `--bp-ink`, `--bp-muted`, `--bp-line` — damit sieht die Ebene aus wie euer Produkt,
ohne dass bluepencil etwas über euer Design-System wissen muss.

---

## 3. Der Store: der Vertrag, den Django erfüllen muss

Basis `/api/v1/bluepencil` (Default des http-Adapters). Diese Endpunkte erwartet der Layer:

| Methode | Pfad | Nutzlast / Antwort |
|---|---|---|
| GET | `/health` | `{ ok, status, version }` |
| GET | `/notes` | Filter: `route, intent, type, session, source, environment, includeDone, since, status` → `{ notes }` |
| POST | `/notes` | NoteDraft-JSON → `{ note }` |
| PATCH | `/notes/{id}` | nur Notizfelder → `{ note }` |
| POST | `/notes/{id}/messages` | `{ id, ts, text, author, author_type, kind }` → `{ note }` |
| POST | `/notes/bulk-delete` | `{ ids?, filter?, confirm: true }` → `{ removed }` |
| GET | `/sessions` | `{ sessions }` |
| GET | `/bundle` | kanonisches Bundle (Export/Agenten) |
| GET | `/journal` | Historie — **optional**, nur für Betrieb/Agenten |

Fehlerformat: `{"error":{"code","message"}}`; `400` unparsbare Nutzlast, `404` unbekannte ID, `415`
kein `application/json`, `405` falsche Methode. DRFs Default-Format weicht ab → eigener
Exception-Handler (`EXCEPTION_HANDLER`) ist Pflicht, sonst zeigt die Ebene generische Fehler.

Modellseitig: eine `ReviewNote` mit **eurem** Tenant-FK (RLS greift wie überall), den kanonischen
Feldern und `environment` (`dev|staging|live`). Service-Layer-Regel eures Repos gilt: keine
Model-Queries im View, sondern Service + Serializer.

**Serverseitiger Riegel:** die Endpunkte dürfen nur Reviewer-Rollen schreiben. Der `gate` im Client
ist Bequemlichkeit, nicht Sicherheit.

---

## 4. Verifikation (nach euren Regeln, nicht daneben)

1. **Playwright-Spec** (`e2e/bluepencil.spec.ts`): einloggen, `<bluepencil-notes>` muss montiert sein,
   `data-bp-version` gesetzt, `window.bluepencilAttach.version` = erwartete Version; Notiz auf einem
   `data-testid`-Element anlegen; danach **außerhalb der Seite** prüfen, dass sie in der API **und** in
   der DB steht (Assertion im Test, nicht in der App).
2. **Zwei Läufe pro Notiz prüfen:** einmal mit, einmal ohne Reviewer-Rolle — der Layer darf für
   Nicht-Reviewer gar nicht laden (und die API muss 403 liefern, auch wenn jemand den Tag von Hand setzt).
3. **Fehlerpfad mit echter Serverantwort:** `endpoint` auf einen Pfad zeigen, der HTML liefert — die
   Ebene muss den Fehler melden (`bp-error` + `element.issues`), nicht stumm bleiben.
4. **CI-Pflicht:** fehlt der Browser, muss der Job rot werden statt still zu skippen (in bluepencil
   heißt das `BP_REQUIRE_BROWSER=1`).

---

## 5. Der Agenten-Teil (euer eigentlicher Gewinn)

Nach Option A liegen die Review-Notizen in eurer Domäne — dann sind sie in wenigen Zeilen eine
**MCP-Tool-Gruppe** neben den bestehenden 11 (z. B. `review.notes.list`, `review.notes.reply`,
`review.notes.bundle`). Damit kann der LLM Anmerkungen aus der Oberfläche direkt als Anforderungs-,
Risiko- oder Testkandidaten weiterverarbeiten — das ist der Punkt, an dem bluepencil in eurem
Produkt mehr ist als ein Overlay.

Ohne Django-Anbindung geht es auch, aber umständlicher: `bluepencil inspect|export` gegen den
Store, oder der `/bundle`-Endpunkt des Sidecars.

---

## 6. Risiken und offene Punkte (ehrlich)

- **Sechs Endpunkte sind echte Arbeit**, inklusive Schema-Validierung (Notiz-Kanonik) und Tests. Kein
  Nachmittag, wenn ihr eure Qualitätsregeln einhaltet.
- **Multi-Tenancy ist die Gefahrenstelle:** jede Notiz braucht den Tenant-Kontext. Eine Implementierung
  ohne RLS-Prüfung wäre ein Datenleck zwischen Workspaces — das ist der teuerste Fehler dieses Vorhabens.
- **Datenpolitik:** Review-Notizen enthalten Formulierungen aus dem Inneren des Systems („das ist
  unfertig", Kundenmeinungen). Aufbewahrung und Purge gehören in die Doku, nicht in eine Fußnote.
- **Cross-Origin wäre Aufwand:** bluepencil setzt im HTTP-Adapter kein `credentials` (Default
  `same-origin`, geprüft). Root-relative `endpoint` ist deshalb die Empfehlung; ein anderer Origin
  bräuchte `credentials: "include"` im Adapter plus CORS-mit-Credentials.
- **`anchor-hooks`** ist seit `0.1.0-alpha.1` als Attribut vorhanden (bluepencil#10) — **erledigt**, und
  ehrlich: der Befund war ursprünglich falsch zugespitzt. `data-testid` ist bereits der Standard-Anker;
  das Attribut ist nur für andere Haken oder eine andere Reihenfolge nötig.
- **Freigabe-Pfade für den Host (neu, `bluepencil#15`):** `identity="rfBluepencil.identity"` und
  `can-annotate="rfBluepencil.canAnnotate"` erlauben jetzt echte Host-Entscheidungen aus dem Markup —
  `can-annotate` ist der Haken für eure eigene Komponentensprache: `fn(element) → false` lehnt ein
  Element ab (FR-1.10), die Ebene fragt es bei jedem Klick. Damit muss *kein* Element „annotierbar
  aussehen", ihr entscheidet es.
- **Die zwei QS-Befunde sind fix (Issues #11, #12).** Was bleibt, ist Arbeit bei euch, nicht in
  bluepencil: eure sechs Endpunkte, `host.ts`, und der Durchstich durch die Anmeldemaske (dort gibt es
  keine `data-testid`-Haken — der Authentifizierungs-Smoke muss also über Titel/Aria laufen).
- **Versionierung:** bluepencil läuft unter versioniertem Pfad mit `latest.json`; ein Upgrade ist ein
  Attributwechsel, ein Teardown (`destroy()`) gehört dazu — sonst bleibt beim Versionswechsel ein Rest.

---

## Kurzfassung in fünf Schritten

1. Sidecar auf eine **Kopie** des gebauten Frontends zeigen (`--root`), einen Tag injizieren, Notiz
   anlegen, Round-Trip messen. → siehst es heute, ändert noch nichts am Produkt.
2. `frontend/src/bluepencil/host.ts` schreiben (Header-Funktion **mit** `X-CSRFToken`, gate,
   routeFor, identity) und in `App.tsx` verankern.
3. ~~`anchor-hooks` in bluepencil nachreichen~~ — **erledigt** in `0.1.0-alpha.1` (plus die Fixes aus
   PR #15: Default-Tag, `check()`, `identity`-Pfad, `can-annotate`). Dieser Schritt ist abgehakt; an
   seiner Stelle steht jetzt: `build-ref`/`identity` an euren Build binden und den Sidecar-Upgrade-Pfad
   über `latest.json` einmal durchspielen.
4. Django-App `review_notes` mit dem Vertrag aus §3 (RLS!), Exception-Handler in den DRF-Settings.
5. Playwright-Spec + CI-Pflicht aus §4, dann MCP-Tool-Gruppe aus §5.
