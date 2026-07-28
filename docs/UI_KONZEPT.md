# UI-Konzept ReqogniLoom

> Entstanden aus dem Konsistenz-Audit vom 2026-07-28 (Issues #157–#185).
> Dieses Dokument beschreibt das Zielbild, nicht den Ist-Zustand.

---

## 1. Ausgangslage

Das Audit hat zehn Artefaktseiten an der laufenden Anwendung vermessen. Das Ergebnis
in einem Satz: **die Bausteine sind da, die Regel fehlt.**

`ListToolbar`, `SplitView`, `VersionBadge`, `ArtifactInspector`, `WorkspaceTree` und
`getStatusBadgeStyle` existieren als gemeinsame Komponenten — aber jede wird nur von
einem Teil der Seiten benutzt. Wer sie nicht benutzt, baut die Sache nach. So sind
entstanden: fünf Seitenkopf-Muster, drei Status-Badge-Varianten, drei
Baum-Implementierungen, vier Leerzustände und zwischen zwei und fünf Scroll-Flächen
pro Seite.

Das Konzept unten fügt deshalb wenig Neues hinzu. Es entscheidet.

---

## 2. Leitgedanke

Wer mit diesem Werkzeug arbeitet, tut den ganzen Tag dasselbe: **er bewegt sich durch
einen getracten Graphen und verliert dabei ständig den Kontext.** Von einem Stakeholder
Need zum abgeleiteten Requirement, von dort zum Architekturelement, zum Testfall, zurück.
Vier Seitenwechsel, und man weiß nicht mehr, wovon man ausgegangen ist.

Die Oberfläche hat genau eine Aufgabe: **den Weg sichtbar halten.**

Daraus folgen drei Regeln, die jede Detailentscheidung in diesem Dokument bestimmen:

1. **Ein Artefakt sieht überall gleich aus.** ID, Ebene, Status, Version — immer dieselbe
   Darstellung an derselben Stelle, egal ob in einer Liste, einem Baum, einem Trace-Panel
   oder im Detail-Kopf. Wiedererkennung ist hier kein Stilthema, sondern Navigation.
2. **Der Rahmen bewegt sich nicht.** Kopf, Navigation und Kontext bleiben stehen; nur der
   Inhalt scrollt. Wer scrollt, soll seinen Platz behalten.
3. **Der Graph ist immer sichtbar.** Man sieht jederzeit, wo man ist und was daran hängt —
   ohne die Seite zu wechseln.

---

## 3. Das Signaturelement: die Trace-Spine

Der eine Teil, an den man sich erinnern soll — und der einzige, an dem das Konzept
auffällig wird.

Am linken Rand des Detailbereichs steht eine schmale, senkrechte Leiste: die **Spine**.
Sie zeigt die fünf V-Modell-Ebenen als feste Stationen und markiert, auf welcher das
aktuelle Artefakt sitzt. Neben jeder Station steht, wie viele verknüpfte Artefakte dort
liegen.

```
    ┌───────────────────────────────────────────────────────────┐
    │  L0  ○───  Stakeholder Needs                     2 ↑      │
    │      │                                                    │
    │  L1  ●═══  System Requirements       ◀ hier               │
    │      │                                                    │
    │  L2  ○───  Subsysteme                            4 ↓      │
    │      │                                                    │
    │  L3  ○───  Komponenten                           – ⚠      │
    │      │                                                    │
    │  L4  ○───  Verifikation                          7 ↓      │
    └───────────────────────────────────────────────────────────┘
```

- Die gefüllte Station ist das aktuelle Artefakt.
- Zahlen sind Verknüpfungen nach oben (↑ Herkunft) und unten (↓ Ableitung).
- Ein `⚠` markiert eine Ebene ohne Abdeckung — die Lücke, die man in einem
  Requirements-Werkzeug sucht.
- Klick auf eine Station öffnet die verknüpften Artefakte im Panel daneben. Der Kontext
  bleibt dabei stehen.

Warum das und nicht ein Breadcrumb: Ein Breadcrumb zeigt, wo man **hergekommen** ist. Die
Spine zeigt, wo man **steht** — und, wichtiger, wo nichts ist. Fehlende Abdeckung ist in
diesem Werkzeug die eigentliche Information; sie sollte nicht erst über einen
Coverage-Report auffallen.

Die Spine ist das einzige auffällige Element des Konzepts. Alles andere bleibt ruhig.

---

## 4. Das Grundgerüst

Drei Zonen, feste Breiten, **genau drei Scroll-Flächen** in der gesamten Anwendung.

```
┌────────────┬──────────────────────────┬───────────────────────────────┐
│            │  Seitenkopf   (sticky)   │  Artefaktkopf      (sticky)   │
│  NAVIGATION├──────────────────────────┼───────────────────────────────┤
│            │  Filterleiste (sticky)   │ │                             │
│  (scrollt) ├──────────────────────────┤S│  Inhalt                     │
│            │                          │P│  (scrollt)                  │
│  ──────    │  Liste / Baum            │I│                             │
│  Kontext   │  (scrollt)               │N│                             │
│  Konto     │                          │E│                             │
└────────────┴──────────────────────────┴───────────────────────────────┘
     240px            40 %                          60 %
```

**Scroll-Modell — verbindlich:**

| Fläche | scrollt | `overscroll-behavior` |
|---|---|---|
| Navigation | ja | `contain` |
| Liste / Baum | ja | `contain` |
| Detail-Inhalt | ja | `contain` |
| **alles andere** | **nein** | – |

Karten, Panels, Formularabschnitte und Toolbars bekommen **keinen** eigenen Scroll mehr.
Sie wachsen in ihrer Fläche. Scrollbalken bleiben sichtbar (`scrollbar-gutter: stable`) —
sie sind die einzige Ortsangabe in einer langen Liste.

Ohne gewähltes Element entfällt der Detailbereich und die Liste läuft über die volle
Breite. Kein leeres Panel mit „Select an item from the list".

**Schmale Fenster (< 1024px):** Navigation wird zum Off-Canvas-Panel, Liste und Detail
stapeln zu einer Spalte mit Zurück-Schritt. Die Spine wandert waagerecht unter den
Artefaktkopf.

---

## 5. Der Seitenkopf — ein Muster für alle

```
┌──────────────────────────────────────────────────────────────────┐
│  System Requirements                       [ Neues Requirement ] │
│  128 Requirements · 12 in Prüfung                          [ ⋯ ] │
└──────────────────────────────────────────────────────────────────┘
```

Eine Komponente, keine Ausnahmen:

```tsx
<PageHeader
  title="System Requirements"           // immer genau ein <h1>
  summary="128 Requirements · 12 in Prüfung"
  primaryAction={{ label: 'Neues Requirement', onClick }}
  overflowActions={[exportPdf, importCsv, createBaseline]}
/>
```

- **Überschrift** immer `<h1>`, `--font-size-3xl`, `--leading-tight`. Nie `h2` oder `h3`,
  nie weggelassen.
- **Zusammenfassung** ersetzt den heutigen Zähler, der nur bei aktivem Filter erscheint.
  Sie beantwortet die häufigste Frage sofort und macht abgeschnittene Listen sichtbar.
- **Eine** Primäraktion, oben rechts, gefüllt. Sie benennt das Ergebnis
  („Neues Requirement"), nicht die Geste („+ New"), und behält denselben Namen im
  Dialogtitel und in der Erfolgsmeldung.
- Alles Weitere ins Überlaufmenü. Export und Import sind seltene Aufgaben und dürfen den
  Kopf nicht besetzen.

---

## 6. Artefakt-Identität

Vier Angaben, immer dieselbe Reihenfolge, immer dieselbe Darstellung — in Listen, Bäumen,
Trace-Panels und im Detail-Kopf:

```
  SYS-REQ-001    L1    ●  In Prüfung    v3
  └── ID ───┘   └Ebene┘ └── Status ──┘  └Version┘
   --font-mono  neutral  farbkodiert    neutral
```

| Element | Komponente | Regel |
|---|---|---|
| ID | `<ArtifactId>` | `--font-mono`, klickbar zum Kopieren, `user-select: all` |
| Ebene / Typ | `<LevelBadge>` | **neutral** gefärbt — Ebene ist kein Zustand |
| Status | `<StatusBadge>` | **einzige** farbkodierte Angabe, immer über `getStatusBadgeStyle` |
| Version | `<VersionBadge>` | neutral, nur bei > 1 |

Der entscheidende Punkt: **Farbe ist für Status reserviert.** Heute ist das grüne `SR` bei
Requirements ein Typkürzel und das blaue `L0` eine Ebene — beide besetzen ein System, das
für „freigegeben / in Prüfung / veraltet" gedacht ist. Wer einmal gelernt hat, dass Grün
freigegeben heißt, liest die Requirements-Liste falsch.

---

## 7. Listen und viele Elemente

Eine Listen-Primitive für alle Artefakttypen:

```
┌──────────────────────────────────────────────────────────────┐
│ 🔍 Suchen…                    [ Status ▾ ] [ Sortierung ▾ ]  │  sticky
│ 128 Requirements · gefiltert: 12                             │
├──────────────────────────────────────────────────────────────┤
│ SYS-REQ-001  L1   ● Freigegeben   v3                         │
│ Hauptfunktion des Systems                                    │
├──────────────────────────────────────────────────────────────┤
│ SYS-REQ-002  L1   ● In Prüfung    v1                         │
│ Abschaltverhalten bei Übertemperatur                         │
└──────────────────────────────────────────────────────────────┘
                        ⋮ virtualisiert
```

- **Zweizeilig:** Identität oben, Titel unten. Beim Überfliegen sucht man die ID, beim
  Lesen den Titel — beide brauchen ihre eigene Zeile.
- **Filterleiste in einer Zeile:** Suche wächst, Filter feste und gleiche Breite,
  Sortierung rechts. Keine Primäraktion in der Leiste.
- **Virtualisierung immer an**, nicht nur in zwei Listen. Ab 100 Zeilen greift sie
  automatisch.
- **Nachladen einheitlich:** eine Strategie für alle. Heute gibt es drei — `fetchAll`,
  `page_size=100` und „erste Seite", letztere schneidet das Glossar still bei 25 Einträgen
  ab. Empfehlung: serverseitige Paginierung mit automatischem Nachladen beim Scrollen,
  plus die Gesamtzahl im Seitenkopf als Kontrollanzeige.

---

## 8. Bäume

**Eine** Baum-Primitive, `shared/WorkspaceTree`, mit dem vereinigten Funktionsumfang der
heutigen drei:

| Fähigkeit | Quelle heute |
|---|---|
| Auf-/Zuklappen, Auswahl | alle drei |
| Virtualisierung | `WorkspaceTree` |
| Suche und Filter im Baum | `WorkspaceTree`, `DecompositionTree` |
| Tastaturnavigation | `DecompositionTree` |
| Drag & Drop zum Umhängen | `DecompositionTree` |
| `role="tree"` / `treeitem` | `WorkspaceTree`, `DecompositionTree` |

Artefaktspezifisches nur noch über Render-Props (Badge, Kontextmenü) — nicht über eine
neue Implementierung.

**Tastatur, überall gleich:** `↑` `↓` Zeile wechseln · `→` aufklappen, dann tiefer ·
`←` zuklappen, dann zum Elternknoten · `Home` `End` Anfang/Ende · Buchstabe tippen springt
zum nächsten passenden Knoten · `Enter` öffnet im Detail.

Das ist der ARIA-Standard für Bäume. Heute erfüllt ihn genau einer von dreien.

---

## 9. Leerzustände

Ein leerer Bildschirm ist der erste, den ein neuer Nutzer sieht. Er soll den nächsten
Schritt anbieten, nicht den Zustand melden.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   Noch keine Requirements                                    │
│                                                              │
│   Requirements halten fest, was das System können muss.      │
│   Leg das erste an oder übernimm einen bestehenden Bestand.  │
│                                                              │
│   [ Neues Requirement ]   [ CSV importieren ]                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

Drei Fälle, klar getrennt:

| Fall | Aussage | Aktion |
|---|---|---|
| **Leer** | was hier entsteht und wozu | anlegen, importieren |
| **Kein Treffer** | welcher Filter greift | Filter zurücksetzen |
| **Fehler** | was schiefging und was jetzt hilft | erneut versuchen |

Fehler entschuldigen sich nicht und bleiben konkret. Heute werden sie in vier Ansichten
nur nach `console.error` geschrieben, während sich das Formular schließt — der Nutzer
glaubt, gespeichert zu haben. Jede fehlgeschlagene Aktion braucht eine `role="alert"`-
Meldung, und das Formular bleibt offen.

---

## 10. Was den Tokens fehlt

Das System in `tokens.css` ist gut gebaut — es hat einen vollständigen Light-Spiegel für
jedes Farb-Token. Es fehlen fünf Dinge, ohne die die Regeln oben nicht durchsetzbar sind:

```css
/* Schrift */
--font-mono:  'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
--font-size-md:  1.0625rem;   /* wird an 10 Stellen benutzt, existiert aber nicht */
--font-size-3xl: 1.875rem;    /* für <h1> im Seitenkopf */

/* Rhythmus */
--leading-tight: 1.15;
--leading-normal: 1.5;
--leading-relaxed: 1.7;
--tracking-tight: -0.02em;
--tracking-wide: 0.06em;

/* Zustand */
--color-focus: <pro Theme>;   /* global.css setzt heute outline: none ohne Ersatz */
--color-nav-bg: <pro Theme>;  /* heute #1a1f2e hartkodiert, ignoriert das Theme */

/* Layout */
--bp-md: 768px;
--bp-lg: 1024px;
```

`--font-size-md` ist der aufschlussreichste Fall: Er wird an zehn Stellen für
Abschnitts-Überschriften verwendet und ist nirgends definiert. Eine undefinierte Custom
Property lässt `font-size` auf den geerbten Wert zurückfallen — jede dieser Überschriften
rendert seit jeher in Fließtextgröße. Im Code sieht die Zeile korrekt aus. Deshalb gehört
ein Test dazu, der jede `var(--token)`-Referenz gegen `tokens.css` prüft.

---

## 11. Sprache

Die Oberfläche benennt, was der Nutzer kontrolliert — nicht, wie das System gebaut ist.

| statt | besser | warum |
|---|---|---|
| `+ New` | `Neues Requirement` | benennt das Ergebnis |
| `No items found.` | `Noch keine Requirements` | nennt den Gegenstand |
| `Select a need from the list.` | *(entfällt — Liste läuft breit)* | kein leeres Panel |
| `Submit` | `Speichern` | sagt, was passiert |
| `SR` | `System Requirement` | Platz ist da |
| `Outdate` | `Als veraltet markieren` | Fachjargon nur, wo er trägt |

Eine Aktion behält ihren Namen über den ganzen Ablauf: Der Knopf „Baseline anlegen" führt
zum Dialog „Baseline anlegen" und endet in der Meldung „Baseline angelegt".

Und: **eine** Sprache pro Oberfläche. Heute steht das deutsche „Suchen…" der Sidebar neben
dem englischen „Search by title or ID…", der Workflow-Editor ist vollständig
unübersetzt (23 Dateien ohne `useTranslation`), und der Impact-Analysis-Bereich ist
komplett deutsch, während der Rest englisch spricht.

---

## 12. Umsetzungsreihenfolge

Nach Wirkung je Aufwand geordnet. Die ersten beiden Schritte sind klein und tragen weit.

**Schritt 1 — Tokens und Fokus** (klein, sofort sichtbar)
Fehlende Tokens ergänzen · `outline: none` in `global.css:41` durch globales
`:focus-visible` ersetzen · Sidebar-Farbe auf ein Token ziehen.
→ #158, #174, #157

**Schritt 2 — Identität vereinheitlichen** (klein, überall sichtbar)
`<StatusBadge>`, `<ArtifactId>`, `<LevelBadge>` bauen und in allen sieben Detail-Köpfen
und allen Listen einsetzen. Die drei Inline-Kopien entfallen.
→ #173, #183, #182

**Schritt 3 — Seitenkopf** (mittel)
`<PageHeader>` bauen, alle zehn Routen umstellen, Ratchet-Test für „genau ein h1 pro
Route".
→ #172, #178

**Schritt 4 — Scrollen und Listen** (mittel, größte spürbare Wirkung)
Scroll-Modell in `SplitView` verankern · Virtualisierung für alle Listen · `glossary.ts`
und `diagrams.ts` auf vollständiges Laden umstellen · Zähler immer anzeigen.
→ #176, #177, #185

**Schritt 5 — Bäume zusammenführen** (groß)
`WorkspaceTree` um Tastatur und Drag & Drop erweitern, die beiden anderen darauf
umstellen.
→ #175

**Schritt 6 — Layout und Leerzustände** (groß)
Split-View für Glossar und Trace Links · Breakpoints · `<EmptyState>` · Spine.
→ #179, #180, #160, #166

---

## Anhang: gemessene Ausgangswerte

Damit später überprüfbar ist, ob es besser wurde.

| Kennzahl | Stand 2026-07-28 |
|---|---|
| Seitenkopf-Muster über 10 Routen | 5 |
| Routen mit `<h1>` | 2 von 10 |
| Status-Badge-Implementierungen | 3 |
| Baum-Implementierungen | 3 |
| Scroll-Flächen je Seite | 2–5 |
| Listen mit Virtualisierung | 2 von 10 |
| Nachlade-Strategien | 3 |
| Layout-Breakpoints | 0 |
| Inline-`style={{}}` in Komponenten | 207 |
| Hartkodierte Hex-Farben | 128 in 33 Dateien |
| Undefinierte, aber verwendete Tokens | 1 (`--font-size-md`, 10 Verwendungen) |
