# `site/` — ReqogniLoom Präsentationsseite

Diese Datei richtet sich an Maintainer der statischen One-Page-Website unter
`site/`. Sie beschreibt Aufbau, lokale Vorschau, i18n-Workflow, die
Token-Herkunft und das GitHub-Pages-Setup.

## Was ist das?

Eine einzelne, statische Landing-Page für ReqogniLoom (Produktüberblick,
Architektur, Traceability, AI/MCP, Rigor-Presets, Deployment). Kein Framework,
kein Bundler, keine externen Abhängigkeiten — HTML + CSS + Vanilla JS, komplett
offline lauffähig.

```
site/
  index.html                 # die komplette Seite (EN-Text steht inline im HTML)
  .nojekyll                  # verhindert Jekyll-Verarbeitung auf GitHub Pages
  assets/
    css/tokens.css           # kopierte App-Tokens + SITE-OVERRIDE-Block am Ende
    css/style.css            # Komponenten-Styles (nur --color-* Semantic-Tokens)
    js/i18n.js               # DE/EN-Wörterbuch (window.REQLO_I18N)
    js/main.js               # Theme, Sprache, Nav/Scroll-Spy, Reveal, Explorer, Accordion
    img/favicon.svg          # Favicon (verhindert den sonst automatischen /favicon.ico-404)
```

Es gibt **keinen Build-Schritt**: Dateien ändern, committen, fertig. Alles wird
über relative Pfade (`./assets/...`) referenziert und funktioniert daher auch
unter dem Unterpfad `https://popoboxxo.github.io/ReqogniLoom/` — niemals
absolute `/assets/...`-Pfade einführen.

## Lokale Vorschau

```bash
# Variante A: direkt aus site/
cd site
python -m http.server 8765
# -> http://127.0.0.1:8765/

# Variante B: Unterpfad wie in Produktion (empfohlen)
# aus dem Repo-Root:
python -m http.server 8765
# -> http://127.0.0.1:8765/site/
```

## i18n-Workflow (DE/EN)

- Standard ist **Englisch**: Der englische Text steht direkt in `index.html`
  (die Seite ist damit auch ohne JavaScript vollständig). `i18n.js` enthält nur
  die Übersetzungen und ersetzt die Knoten beim Sprachwechsel.
- Neue übersetzbare Stelle:
  1. im HTML das Attribut setzen —
     `data-i18n="key"` (Text), `data-i18n-content="key"` (`content`-Attribut,
     z. B. Meta-Description), `data-i18n-aria-label="key"` (`aria-label`),
     `data-i18n-title="key"` (`title`); als englischen Default denselben Text
     inline eintragen.
  2. den Key in **beiden** Wörterbüchern unter `en` und `de` in
     `assets/js/i18n.js` ergänzen.
- Produkt-IDs, Code, ADR-IDs und Tool-Namen werden nicht übersetzt.
- Parität prüfen (EN/DE, fehlende und verwaiste Keys; berücksichtigt auch die
  dynamischen Keys aus `main.js`):

```bash
node -e "const fs=require('fs');const h=fs.readFileSync('site/index.html','utf8')+fs.readFileSync('site/assets/js/main.js','utf8');const src=fs.readFileSync('site/assets/js/i18n.js','utf8');const w={};new Function('window',src)(w);const {en,de}=w.REQLO_I18N;const used=new Set();for(const m of h.matchAll(/data-i18n(?:-content|-aria-label|-title)?=\"([^\"]+)\"/g))used.add(m[1]);for(const m of h.matchAll(/(?<![A-Za-z0-9_$.])t\('([^']+)'\)/g))used.add(m[1]);const miss=[...used].filter(k=>!(k in en)||!(k in de));const orph=Object.keys(en).filter(k=>!used.has(k));console.log('used',used.size,'EN',Object.keys(en).length,'DE',Object.keys(de).length,'missing',miss,'orphaned',orph);"
```

## Design-Tokens und Site-Overrides

- `assets/css/tokens.css` beginnt mit einer **byte-identischen Kopie** von
  `frontend/src/styles/tokens.css` (Layer-1-Primitives + Layer-2-Semantiken aller
  Themes). Dieser kopierte Bereich wird **nicht** verändert — bei Änderungen am
  App-Designsystem die Kopie neu ziehen und den Override-Block unten erhalten.
- Am **Ende** von `tokens.css` steht ein klar getrennter, kommentierter
  **SITE-OVERRIDE-Block**. Er ergänzt ausschließlich Website-eigene Tokens und
  referenziert nur vorhandene `--palette-*`-Primitives (keine Rohfarben):
  - `--color-link` / `--color-link-hover`: Textlinks. Das App-Token
    `--color-primary` (indigo-600) ist nur als **Füllung für weißen Text**
    gerechtfertigt und fiel als Linktext auf den dunklen Flächen auf 2.33:1
    (`--color-surface-raised`) bzw. 2.84:1 (`--color-surface`); der Light-Hover
    (indigo-400) lag auf Weiß bei 2.98:1 — alles unter WCAG 2.2 AA (1.4.3) für
    14-px-Text.
  - Geprüfte Kontraste (beide Themes, beide Flächen):

    | Token | Theme | auf `--color-surface` | auf `--color-surface-raised` |
    |---|---|---|---|
    | `--color-link` | dark (indigo-400) | 5.98:1 | 4.90:1 |
    | `--color-link-hover` | dark (indigo-400) | 5.98:1 | 4.90:1 |
    | `--color-link` | light (indigo-600) | 6.01:1 | 6.29:1 |
    | `--color-link-hover` | light (indigo-700) | 7.55:1 | 7.90:1 |

- `style.css` verwendet **ausschließlich** semantische `--color-*`-Tokens. Die
  Regel „keine Rohfarben außerhalb von `tokens.css`“ gilt für Hover-/Fokus-/
  Rand-/Schattenfarben gleichermaßen:

```bash
rg -n "#[0-9a-fA-F]{3,8}\b|rgba?\(" site/assets/css/style.css   # muss leer bleiben
```

## Verhalten und Robustheit

- **Theme**: `dark` ist Default, `light` die Alternative. Der Bootstrap-Skript
  im `<head>` setzt `data-theme` vor dem ersten Paint (localStorage gewinnt,
  sonst `prefers-color-scheme`). Der Toggle hat einen **stabilen Namen**
  („Dark mode“ / „Dunkelmodus“) und trägt den Zustand in `aria-pressed`.
- **Nav-Breakpoint 1280 px** (site-lokal): Die 10-Punkte-zweisprachige
  Navigation passt unterhalb 1280 px nicht in eine Zeile (deutsche Labels sind
  länger). Bis 1279 px läuft daher das Burger-Menü, ab 1280 px die Inline-Nav.
  Die App-Breakpoints 768/1024/1600 gelten weiter für die Karten-Grids.
- **No-JS-Fallbacks**: `.reveal`-Inhalte sind ohne JS sichtbar; Accordion- und
  Layer-Panels werden erst versteckt, nachdem das jeweilige Modul die Klassen
  `accordion-ready` bzw. `explorer-ready` gesetzt hat (scheitert das Skript,
  bleibt alles sichtbar). Das Burger-Menü wird ohne JS gar nicht angezeigt.
- **Sticky Header**: bewusst **opak** (`--color-surface`), damit die Nav-Texte
  über allen vorbeiscrollenden Inhalten ≥4.5:1 bleiben (6.96:1 dark / 7.24:1
  light). Der `backdrop-filter: blur()` bleibt als progressive enhancement.
- Interaktive Elemente tragen `data-testid` (Repo-Konvention, u. a. für
  Playwright).

## GitHub Pages

- **Deployment-Quelle** in den Repo-Settings: *Settings → Pages → Build and
  deployment → Source = „GitHub Actions“*.
- Workflow: `.github/workflows/pages.yml` (bewusst getrennt von `ci.yml` und
  `docker-publish.yml`). Trigger: Push auf `main` mit Pfaden `site/**` und
  `.github/workflows/pages.yml` plus `workflow_dispatch`.
- Es gibt **keinen Build-Schritt**: Der Workflow lädt `site/` unverändert als
  Pages-Artefakt hoch (`actions/upload-pages-artifact`, `path: site`) und
  deployt es.
- Erwartete URL: `https://popoboxxo.github.io/ReqogniLoom/`.
