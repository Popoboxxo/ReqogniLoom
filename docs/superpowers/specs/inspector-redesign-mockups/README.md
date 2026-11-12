# Mockups — Inspector-Neukonzept

Statische, offline öffnbare HTML-Mockups zu
[`../2026-11-10-inspector-redesign-design.md`](../2026-11-10-inspector-redesign-design.md).
Kein Framework, kein JavaScript, keine externen Assets (keine Fonts, Bilder, CDNs).
Einfach im Browser öffnen.

| Datei | Zeigt | Spec-Bezug |
|---|---|---|
| [`requirements.html`](requirements.html) | Typ **Requirement**, voller Funktionsumfang: Spine, alle vier Reiter (Version, Diff, Links, Kommentare), Rail-Zähler als Buttons, Zustandskarten (Loading/Empty/Error/Partial) | §2, §3, §4.2 (R2), §5.3, §6 |
| [`glossary.html`](glossary.html) | Typ **Glossary**: keine Spine, Reiter „Links" als einziger Trace-Ort mit allen Zeilen; Vorher/Nachher-Vergleich der „Verwendungen"-Doppelung | §2.4, §3, §8 M5 |
| [`narrow-768.html`](narrow-768.html) | **768 px**: A) Rail mit Zählern (Standard), B) Sheet über dem Detailbereich (`inert` dahinter); Spine waagerecht | §4.2 (R4), §5.1 |

## Konventionen

- **Tokens:** Alle Farben, Abstände, Radien, Höhen und Schriftgrößen sind CSS-Variablen, deren Namen
  1:1 `frontend/src/styles/tokens.css` entsprechen (Theme `light`). Die Paletten-Primitives sind im
  `:root`-Block aufgelöst, weil das Mockup ohne Build läuft — die *Namen* der semantischen Tokens sind
  unverändert (`--color-surface`, `--btn-h-sm`, `--radius-md`, …).
- **Komponenten-Aliase** entsprechen dem Vertrag in Spec §6.1:
  `--inspector-w-min: 280px` · `--inspector-w-default: 320px` · `--inspector-w-wide: 360px` ·
  `--inspector-w-max: 520px` · `--inspector-rail-w` (40) · `--inspector-tab-h` (32) ·
  `--inspector-row-h` (36) · `--inspector-spine-w` (52) · `--inspector-resize-hit` (24).
  Die vier Breiten-Aliase sind die einzigen Pixel-Literale und stehen genau einmal im `:root`.
- **Kantenbreite:** jede Kante nutzt `var(--control-border-width)` statt `1px` (Spec §6.1/§7 SC 1.4.11);
  Sheet-Kante und Splitter-Ruheline sind `1px solid var(--color-text-muted)` (7.24:1 auf `--color-surface`,
  7.58:1 auf `--color-surface-raised`).
- **Fokus:** `--control-focus-ring` mit **1 px** Offset (kein Offset-Token — begründete Ausnahme, §6.1).
- **Typografie:** keine Schriftgröße unter `--font-size-xs`; Mikro-Labels (Stationslabels, Zähler, Badges)
  nutzen `--font-size-xs`. Kein `9px`/`10px`-Literal.
- **Badges:** 22 px Höhe und `--radius-sm` — der Ist-Vertrag aus `frontend/src/utils/badgeBase.ts:67,92`,
  nicht `--radius-full`.
- **Flächen:** Panel/Sheet = `--color-surface-raised`, Zeilen/Karten = `--color-surface` (Spec §6.1/§6.3).
- **Zähler im gewählten Reiter:** `color: var(--color-on-primary)` auf `background: var(--color-primary)`
  (light 6.29:1, dark 6.29:1, bauhaus 7.52:1), **keine** Invertierung; ein 1-px-Rahmen in
  `--color-on-primary` hält den Zähler auf der Primärfläche sichtbar (Spec §6.2).
- **Überschriften:** Detail- und Inspector-Überschrift sind `h2` (Geschwister), Bereichsüberschriften `h3`
  (Spec §7 SC 1.3.1). Annotationsziffern (`.mark`) sind `aria-hidden="true"` und damit nicht Teil des
  Accessible Name.
- **Reiter:** in `requirements.html`/`glossary.html` als Radio-Gruppe nachgebildet, damit alle Bereiche
  ohne JavaScript sichtbar sind; in `narrow-768.html` (Rahmen B) als echte `<button role="tab">`. Die
  Umsetzung nutzt `role="tablist"`/`role="tab"`/`role="tabpanel"` mit Roving Tabindex und **manueller
  Aktivierung** (Pfeile = Fokus, `Enter`/`Space` = aktivieren, weil jeder Reiter einen Fetch auslöst),
  siehe Spec §5.1/§7. Die IDs `inspector-tab-<key>` / `inspector-panel-<key>` und `aria-controls`
  entsprechen dem Id-Vertrag aus §7; inaktive Panels sind im Mockup per CSS `display:none`, in der
  Umsetzung per `hidden`.
- **Rail-Zähler** sind `<button>` mit eigenem `aria-label` („Kommentare, 3 offen") und `aria-controls`;
  die Kürzel V/D/L/K sind `aria-hidden` (Spec §3, §7 SC 4.1.2).
- **Sheet-Zustand:** non-modal, aber der überdeckte Detailbereich ist `inert` (Spec §4.2); Rail und Sheet
  sind ein DOM-Knoten, der jeweils andere Zweig wird nicht gerendert.
- **Keine Messwerte:** Die Breiten (1440 / 768 / 320 px) sind aus CSS und `docs/UI_KONZEPT.md` §6
  abgeleitet. Es lief kein Stack; nichts hier ist gerendert gemessen (Ist-Analyse §0). `requirements.html`
  zeigt den R2-Default (Liste 320 · Spine 52 · Inhalt 508 · Inspector 320); 448 px wäre die Untergrenze
  beim Ziehen, nicht der Default.
- Die Mockups sind **Diskussionsgrundlage für Task 6**, kein Produktivcode und keine Vorlage zum
  Kopieren: die Umsetzung entsteht aus dem Implementierungsplan, nicht aus diesen Dateien.
