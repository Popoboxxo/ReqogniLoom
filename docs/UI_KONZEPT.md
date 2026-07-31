# UI-Konzept ReqogniLoom

> **Status:** Entwurf zur Abstimmung · **Stand:** 2026-07-31 (fachlich korrigiert)
> **Grundlage:** Konsistenz-Audit an der laufenden Anwendung (Issues #157–#186)
> **Sammel-Issue:** #186 · **Geltungsbereich:** `frontend/` gesamt

Dieses Dokument beschreibt das Zielbild der Oberfläche. Es ist bindend für neue
Komponenten und maßgeblich bei Umbauten. Wo der Ist-Zustand abweicht, ist das ein
Befund — kein Präzedenzfall.

---

## Inhalt

1. [Ausgangslage](#1-ausgangslage)
2. [Leitgedanke](#2-leitgedanke)
3. [Gestaltungsprinzipien](#3-gestaltungsprinzipien)
4. [Was bleibt, was sich ändert](#4-was-bleibt-was-sich-ändert)
5. [Das Signaturelement: die Trace-Spine](#5-das-signaturelement-die-trace-spine)
6. [Layout](#6-layout)
7. [Scroll-Modell](#7-scroll-modell)
8. [Farbe](#8-farbe)
9. [Typografie](#9-typografie)
10. [Abstand und Rhythmus](#10-abstand-und-rhythmus)
11. [Bewegung](#11-bewegung)
12. [Komponentenkatalog](#12-komponentenkatalog)
13. [Zustände](#13-zustände)
14. [Sprache](#14-sprache)
15. [Barrierefreiheit als Grundniveau](#15-barrierefreiheit-als-grundniveau)
16. [Durchsetzung](#16-durchsetzung)
17. [Umsetzungsreihenfolge](#17-umsetzungsreihenfolge)
18. [Anhang A: Token-Referenz](#anhang-a-token-referenz)
19. [Anhang B: Messwerte](#anhang-b-messwerte)

---

## 1. Ausgangslage

Das Audit hat zehn Artefaktseiten an der laufenden Anwendung vermessen — Screenshots,
berechnete Stile, Quelltextvergleich. Das Ergebnis in einem Satz:

> **Die Bausteine sind da. Die Regel fehlt.**

`ListToolbar`, `SplitView`, `VersionBadge`, `ArtifactInspector`, `WorkspaceTree` und
`getStatusBadgeStyle` existieren als gemeinsame Komponenten und sind gut gebaut. Aber
jede wird nur von einem Teil der Seiten benutzt. Wer sie nicht benutzt, baut die Sache
nach. So sind entstanden:

| Sache | Anzahl Varianten |
|---|---|
| Seitenkopf-Muster über 10 Routen | **5** |
| Status-Badge im Detail-Kopf | **3** |
| Navigationsbaum-Implementierungen | **3** |
| Leerzustände | **4** |
| Nachlade-Strategien für Listen | **3** |
| Scroll-Flächen je Seite | **2 bis 5** |

Das ist kein Gestaltungsproblem im engeren Sinne. Es ist ein Durchsetzungsproblem: Es
gab nie eine Stelle, an der steht, wie es gemacht wird — und keinen Test, der es prüft.
Kapitel 16 behandelt das gesondert, weil ohne diesen Teil alles andere in zwei Jahren
wieder auseinanderläuft.

Vollständige Messwerte in [Anhang B](#anhang-b-messwerte).

---

## 2. Leitgedanke

Wer mit diesem Werkzeug arbeitet, tut den ganzen Tag dasselbe: **Er bewegt sich durch
einen getracten Graphen und verliert dabei ständig den Kontext.**

Von einem Stakeholder Need zum abgeleiteten Requirement, von dort zum
Architekturelement, weiter zum Testfall, zurück zum Ursprung, um zu prüfen, ob die
Ableitung noch trägt. Vier Seitenwechsel — und man weiß nicht mehr, wovon man
ausgegangen ist.

Die Oberfläche hat genau eine Aufgabe:

> **Den Weg sichtbar halten.**

### Die gestalterische Haltung

Ein zweiter Gedanke bestimmt den Ton. Die Daten in diesem Werkzeug **sind** ein
Spezifikationsdokument unter Versionskontrolle: nummerierte Anforderungen, Ableitungen,
Freigabestände, Revisionen, Prüfvermerke. Das ist keine Metapher, das ist das Datenmodell.

Die Oberfläche soll deshalb aussehen wie ein **gepflegtes, lebendes
Spezifikationsdokument** — nicht wie ein Ticket-Board. Konkret heißt das:

- Der **Bezeichner** hat Gewicht. `SYS-REQ-001` ist nicht Metadatum, sondern der Name der
  Sache. Auf einem kontrollierten Dokument steht die Nummer oben, nicht klein und grau
  am Rand.
- Der **Freigabestand** ist die zweitwichtigste Information. Nicht dekorativ, sondern
  amtlich.
- **Ordnung** ist bedeutungstragend. Die Ebene ist keine feste Kategorie aus einer
  Fünf-Stufen-Liste, sondern eine Position im Ableitungsbaum — und dieser Baum hat pro
  Projekt eine andere Tiefe (Kapitel 5.1).
- **Lücken** sind Inhalt. Ein Requirement ohne Testfall ist die wichtigste Zeile auf dem
  Bildschirm.

Was daraus **nicht** folgt: Zeitungsanmutung, Haarlinien überall, Radius null,
Serifenschrift. Das wäre eine Stilübung. Es folgt nur die Rangordnung der Information.

---

## 3. Gestaltungsprinzipien

Fünf Regeln. Jede Detailentscheidung in diesem Dokument lässt sich auf eine davon
zurückführen.

### 3.1 Ein Artefakt sieht überall gleich aus

ID, Ebene, Status, Version — immer dieselbe Darstellung, dieselbe Reihenfolge, dieselbe
Stelle. In einer Liste, in einem Baum, in einem Trace-Panel, im Detail-Kopf, in einer
Suchtrefferzeile.

Wiedererkennung ist hier kein Stilthema, sondern Navigation. Wer eine ID einmal gelesen
hat, muss sie überall wiederfinden, ohne hinzusehen.

### 3.2 Der Rahmen bewegt sich nicht

Kopf, Navigation, Filterleiste und Kontext bleiben stehen. Nur Inhalt scrollt. Wer
scrollt, behält seinen Platz und seine Werkzeuge.

### 3.3 Farbe gehört dem Zustand

Farbe kodiert genau eine Sache: den Workflow-Status. Typ, Ebene, Kategorie und Priorität
werden über Form, Position und Text unterschieden — nicht über Farbe.

Der Grund ist praktisch: Sobald Farbe zwei Bedeutungen trägt, trägt sie keine mehr.

### 3.4 Eine Fläche, eine Aufgabe

Jede Fläche beantwortet eine Frage. Die Liste: *Was gibt es?* Das Detail: *Was ist das?*
Die Spine: *Wo bin ich, und was fehlt?* Panels, die drei Dinge gleichzeitig versuchen,
werden geteilt.

### 3.5 Leere ist eine Einladung

Ein leerer Bildschirm meldet keinen Zustand, sondern bietet den nächsten Schritt an. Das
gilt für leere Listen, leere Suchen, leere Detailbereiche und für Fehler.

---

## 4. Was bleibt, was sich ändert

Ein bewusster Punkt vorweg: **Dies ist kein Neuentwurf.** ReqogniLoom ist ein laufendes
Produkt. Die Palette ist entschieden, ausgeliefert und in Ordnung. Sie wegzuwerfen wäre
Beschäftigung, kein Fortschritt.

### Bleibt

| Sache | Begründung |
|---|---|
| **Indigo als Primärfarbe** (`#6366f1` / `#4f46e5`) | funktioniert, in beiden Themes kontrastgeprüft, etabliert |
| **Slate als Flächenfamilie** | ruhig, für lange Lesestrecken geeignet |
| **Die Status-Badge-Palette** | vollständig, für beide Themes gespiegelt, semantisch korrekt |
| **Radius-Stufen 6 / 12 / 16 px** | konsistent, nicht auffällig, kein Grund zur Änderung |
| **Split-View als Grundfigur** | die Liste-Detail-Beziehung ist der Kern dieses Werkzeugs |
| **`ListToolbar`, `WorkspaceTree`, `ArtifactInspector`** | gut gebaut, nur zu selten genutzt |

### Ändert sich

| Sache | Was passiert |
|---|---|
| **Schrift** | Outfit + Inter → eine Familie mit Mono-Schnitt, selbst gehostet (Kapitel 9) |
| **Anwendung der Tokens** | 207 Inline-Stile, 128 Hex-Literale → über Klassen und Module |
| **Farbrolle** | Farbe war Typ, Ebene *und* Status → nur noch Status |
| **Scroll-Modell** | 2–5 Flächen je Seite → genau 3 in der ganzen Anwendung |
| **Seitenkopf** | 5 Muster → 1 Komponente |
| **Bäume** | 3 Implementierungen → 1 Primitive |
| **Neu** | Trace-Spine als Orientierungselement (dynamische Tiefe, Kapitel 5) |
| **Neu** | Theming-System — benannte Paletten statt nur Hell/Dunkel (Kapitel 8.6) |

Die gestalterische Freiheit wird also an vier Stellen ausgegeben: **Typografie**, **Spine**,
**Statusdarstellung**, **Theming**. Alles andere wird aufgeräumt, nicht neu erfunden.

### Funktionale Untergrenze

**Harte Regel, keine Ermessensfrage:** Jede Seite, die auf dieses Konzept umgestellt wird,
muss danach **mindestens** den Funktionsumfang bieten, den die heutige Seite hat. Das
Konzept ändert Darstellung, Struktur und Durchsetzung — es ist kein Anlass, im Vorbeigehen
eine Filter-, Export- oder Bearbeitungsfunktion zu verlieren, die heute existiert. Wo eine
Umstellung eine bestehende Fähigkeit vorübergehend nicht abbildet, ist das ein offener
Punkt im PR, kein akzeptierter Verlust.

---

## 5. Das Signaturelement: die Trace-Spine

Der eine Teil, an den man sich erinnern soll.

Am linken Rand des Detailbereichs steht eine schmale, senkrechte Leiste: die **Spine**.
Sie zeigt die Ableitungskette rund um das aktuelle Artefakt und markiert, wo es sitzt.

**Fachliche Korrektur (2026-07-31):** Die Erstfassung zeigte fünf feste V-Modell-Stationen
(L0–L4). Das ist am echten Datenmodell falsch und wurde nach Rückmeldung korrigiert — siehe
5.1 und 5.2.

### 5.1 Warum keine feste Stufenzahl

Zwei Annahmen der Erstfassung halten der Prüfung gegen `backend/persistence/models.py`
nicht stand:

**Erstens:** Die Zahl der Subsystem-Ebenen ist nicht fix. `ArchitectureElement.get_level()`
liefert die **Baumtiefe per CTE-Annotation** (0 = Wurzel, 1 = Kind der Wurzel, …), kein
Enum mit festen Stufen. `element_type` ist seit REQ-006 (D5) bewusst freies Text-Feld, keine
geschlossene Liste — "Subsystem" und "Komponente" sind Namenskonventionen, keine
Ebenennummern. Ein Projekt kann eine Ebene Subsysteme haben, ein anderes sechs, bevor die
erste Komponente auftaucht. Eine Spine mit fest fünf Stationen zeigt in einem Fall vier
leere Stufen, im anderen schneidet sie den echten Baum ab.

**Zweitens:** Verifikation ist keine Ebene, sondern eine Verknüpfungsart. `TestCase` ist
selbst ein `Artifact`; `TraceLink.source`/`target` sind generische Fremdschlüssel auf
`Artifact`. Ein Testfall kann per `VERIFIES`/`TESTS`-Link an **jedes** Artefakt binden — an
einen Stakeholder-Bedarf, ein Requirement, ein Subsystem auf beliebiger Tiefe oder eine
Komponente. Das ist die rechte Seite des V-Modells: Tests laufen parallel zu jeder Ebene der
linken Seite, nicht als eigene, nachgeschaltete Stufe darunter.

### 5.2 Aufbau

Die Spine rendert deshalb **N Stationen aus der tatsächlichen Ableitungskette** des
geöffneten Artefakts — Bedarf, Requirement, dann so viele Architektur-Ebenen, wie der
Baum an dieser Stelle tatsächlich hat — und hängt Verifikation als **Badge an jede
Station**, nicht als eigene Station ans Ende.

```
   ╭──────────────────────────────────────────────────────────╮
   │                                                          │
   │        ○────  Stakeholder-Bedarf                   2 ↑   │
   │        │                                                 │
   │        ●════  System Requirement         ◀ hier     🧪2  │
   │        │                                                 │
   │        ○────  Subsystem                             4 ↓  │
   │        │                                                 │
   │        ○────  Sub-Subsystem                         3 ↓  │
   │        │                                                 │
   │        ◍────  Komponente                       — ⚠  🧪5  │
   │                                                          │
   ╰──────────────────────────────────────────────────────────╯
```

Zwei Architektur-Ebenen im Beispiel sind kein Zufallswert — die Spine fragt bei jedem
Öffnen die reale Tiefe des Baums ab (`get_level()` je Vorfahre/Nachfahre in der Kette) und
rendert genau so viele Zwischenstationen wie vorhanden sind, ohne Ober- oder Untergrenze.
Ein Bedarf mit direkt darunterliegender Komponente (keine Subsystem-Zwischenebene) zeigt
entsprechend keine leere Station — es gibt keine Pflichtebenen zwischen den Ankerpunkten
Bedarf, Requirement und Komponentenblatt.

### Zeichensprache

| Zeichen | Bedeutung |
|---|---|
| `●` gefüllt | die Station des aktuellen Artefakts |
| `○` offen | Station mit Verknüpfungen |
| `◍` halb | Station existiert, aber ohne Verknüpfung zu *diesem* Artefakt |
| `↑` | Herkunft — woraus dieses Artefakt abgeleitet wurde |
| `↓` | Ableitung — was daraus entstanden ist |
| `⚠` | **keine Abdeckung** — die eigentliche Information |
| `🧪N` | **Verifikations-Badge** — N verknüpfte Testfälle an dieser Station, unabhängig von ihrer Position im Baum |

### Verhalten

- **Klick auf eine Station** öffnet die verknüpften Artefakte in einem Panel neben der
  Spine. Der Kontext bleibt stehen — man verlässt die Seite nicht.
- **Klick auf ein 🧪-Badge** öffnet die verknüpften Testfälle dieser Station, getrennt vom
  Ableitungspanel — Verifikation ist eine eigene Frage, keine weitere Ableitungsstufe.
- **Hover** zeigt die Titel der verknüpften Artefakte als Vorschau.
- Die Spine ist **immer** sichtbar, solange ein Artefakt geöffnet ist, und scrollt nicht
  mit dem Inhalt.
- Auf schmalen Fenstern (< 1024 px) wandert sie waagerecht unter den Artefaktkopf. Bei mehr
  als vier Zwischenstationen wird sie horizontal scrollbar statt umzubrechen — die
  Reihenfolge der Kette bleibt so erkennbar.

### Warum das und nicht ein Breadcrumb

Ein Breadcrumb zeigt, wo man **hergekommen** ist — eine Historie der eigenen Klicks. Die
Spine zeigt, wo man **steht**, und, wichtiger: **wo nichts ist.**

Fehlende Abdeckung ist in einem Requirements-Werkzeug die gesuchte Information. Heute
findet man sie nur über einen eigenen Coverage-Report, also nachgelagert und selten. In
der Spine fällt sie bei jedem geöffneten Artefakt beiläufig auf.

Das ist der eine Ort, an dem das Konzept auffällig wird. Alles andere bleibt ruhig.

---

## 6. Layout

### 6.1 Zonen

Drei Zonen, feste Verhältnisse.

```
┌────────────┬───────────────────────────┬──────────────────────────────────┐
│            │  Seitenkopf      (sticky) │  Artefaktkopf         (sticky)   │
│ NAVIGATION ├───────────────────────────┼──────────────────────────────────┤
│            │  Filterleiste    (sticky) │ │                                │
│  (scrollt) ├───────────────────────────┤S│                                │
│            │                           │P│   Inhalt                       │
│  ────────  │  Liste / Baum             │I│   (scrollt)                    │
│  Kontext   │  (scrollt)                │N│                                │
│  Konto     │                           │E│                                │
│            │                           │ │                                │
└────────────┴───────────────────────────┴──────────────────────────────────┘
   240 px              40 %                            60 %
                   min 380 px                       min 520 px
```

### 6.2 Regeln

- **Navigation** hat feste 240 px. Sie ist ein Register, kein Inhaltsbereich, und darf
  nicht mit dem Inhalt um Platz konkurrieren.
- **Liste und Detail** teilen sich den Rest im Verhältnis 40 : 60, jeweils mit
  Mindestbreite. Unterschreitet das Fenster die Summe der Mindestbreiten, greift der
  Umbruch (6.3).
- **Ohne gewähltes Element entfällt der Detailbereich.** Die Liste läuft dann über die
  volle Breite. Kein leeres Panel mit „Select an item from the list."

  Das behebt zugleich, dass heute rund 43 % des Viewports ungenutzt bleiben, solange
  nichts geöffnet ist.
- **Alle Flächen füllen die Höhe.** Keine Karte endet auf halber Strecke mit leerem
  Seitenhintergrund darunter.

### 6.3 Schmale Fenster

Zwei Haltepunkte. Sie gelten nicht nur für Mobilgeräte — ein halbiertes Browserfenster
auf einem Laptop trifft denselben Zustand.

**< 1024 px (`--bp-lg`)**
- Navigation wird zum Off-Canvas-Panel mit Umschalter im Seitenkopf
- Liste und Detail behalten die Nebeneinander-Anordnung, Verhältnis 45 : 55
- Spine wandert waagerecht unter den Artefaktkopf

**< 768 px (`--bp-md`)**
- Liste und Detail stapeln zu einer Spalte
- Ein Artefakt öffnen ersetzt die Liste; ein Zurück-Schritt im Artefaktkopf führt zurück
- Filterleiste bricht auf zwei Zeilen um; Filter **schrumpfen nicht** unter ihre lesbare
  Breite

Heute existiert kein einziger Layout-Haltepunkt. Die vier `@media`-Regeln im Projekt
betreffen ausschließlich `prefers-reduced-motion`.

---

## 7. Scroll-Modell

Der Bereich mit der größten spürbaren Wirkung — und der klarsten Regel.

### 7.1 Genau drei Flächen

| Fläche | scrollt | `overscroll-behavior` |
|---|:---:|---|
| Navigation | ja | `contain` |
| Liste / Baum | ja | `contain` |
| Detail-Inhalt | ja | `contain` |
| **alles andere** | **nein** | — |

Karten, Panels, Formularabschnitte, Toolbars und Trace-Listen bekommen **keinen** eigenen
Scroll. Sie wachsen in ihrer Fläche.

### 7.2 Warum das nötig ist

Gemessen: 4–5 verschachtelte Scroll-Container je Seite, und auf **allen** Routen
`document.scrollHeight === clientHeight` — das Dokument selbst scrollt nie.

Die Folgen sind genau die, über die sich Nutzer beschweren:

- Der Zeiger steht zwischen zwei Containern — auf einer Trennlinie, einem Rand, der
  Toolbar — und das Rad bewegt gar nichts.
- Ein innerer Container erreicht sein Ende, das Scrollen springt unangekündigt auf den
  äußeren über.
- Es gibt keinen „die Seite scrollen"-Rückfallweg, wenn man nicht trifft.
- Die Anzahl schwankt je Seite zwischen 2 und 5 — dasselbe Werkzeug verhält sich pro
  Ansicht anders.

### 7.3 Weitere Regeln

- **Scrollbalken bleiben sichtbar** (`scrollbar-gutter: stable`). Sie sind die einzige
  Ortsangabe in einer langen Liste. Sie zu verstecken spart nichts und kostet Orientierung.
- **Sticky statt mitscrollend:** Seitenkopf, Filterleiste und Artefaktkopf bleiben stehen.
  Wer bei Zeile 400 einen Filter setzen will, soll nicht zurückscrollen müssen.
- **Position merken:** Wechselt man von der Liste ins Detail und zurück, steht die Liste
  an derselben Stelle. Ausgewähltes Element wird bei Bedarf in den Blick gescrollt
  (`scrollIntoView({ block: 'nearest' })` — nicht zentriert, das reißt den Kontext weg).
- **Kein Scroll-Sprung beim Laden.** Platzhalter belegen die spätere Höhe.

Das Modell wird **einmalig in `SplitView` verankert**, damit es nicht pro Seite neu
erfunden wird.

---

## 8. Farbe

### 8.1 Die Rolle der Farbe

Farbe kodiert **den Workflow-Status. Sonst nichts.**

Heute ist das nicht so, und der Schaden ist konkret: In der Requirements-Liste steht ein
**grünes** `SR`. Grün ist im Token-System `--color-badge-success-*` und heißt überall
sonst „freigegeben". Hier heißt es „System Requirement" — ein Typkürzel. Daneben, in der
Architektur, steht ein **blaues** `L0` für eine Ebene.

Drei Informationsarten, ein Farbsystem. Wer gelernt hat, dass Grün „freigegeben" bedeutet,
liest die Requirements-Liste falsch — und zwar bei der ersten Information, die das Auge
aufnimmt.

### 8.2 Statusfarben

| Status | Bedeutung | Token |
|---|---|---|
| Entwurf | in Arbeit, nicht geprüft | `--color-badge-neutral-*` |
| In Prüfung | eingereicht, wartet auf Freigabe | `--color-badge-info-*` |
| Freigegeben | verbindlich, baseline-fähig | `--color-badge-success-*` |
| Veraltet | ersetzt oder zurückgezogen | `--color-badge-warning-*` |
| Abgelehnt | geprüft und verworfen | `--color-badge-danger-*` |

Die Palette existiert bereits vollständig in `tokens.css`, für beide Themes gespiegelt.
Sie muss nur überall benutzt werden — heute tut das nur `getStatusBadgeStyle`, und das
läuft in den Listen, aber nur in einem von sieben Detail-Köpfen.

### 8.3 Was Farbe nicht tut

| Information | Wird unterschieden über |
|---|---|
| Artefakttyp | Position und Text (Präfix der ID: `SYS-REQ`, `SYS-ARCH`) |
| V-Modell-Ebene | neutrales Badge links neben dem Titel |
| Priorität / Schwere | Text, bei Bedarf ein Symbol |
| Auswahl | Fläche und linke Kante, nicht Textfarbe |

### 8.4 Flächen

| Rolle | Token | Verwendung |
|---|---|---|
| Seitengrund | `--color-surface` | Hintergrund der Anwendung |
| Erhöhte Fläche | `--color-surface-raised` | Karten, Panels, Dialoge |
| Navigation | `--color-nav-bg` | **neu** — heute `#1a1f2e` hartkodiert |
| Rand | `--color-border` | Trennungen, Umrisse |
| Fokus | `--color-focus` | **neu** — heute existiert kein Fokusring |

Zwei Tokens fehlen und sind der Grund für zwei Befunde: Die Navigation ignoriert das
Theme (in Light **und** Dark `rgb(26,31,46)`), und Schaltflächen haben überhaupt keinen
sichtbaren Fokus, weil `global.css:41` global `outline: none` setzt.

### 8.5 Kontrast

- Text auf Fläche: mindestens **4,5 : 1** (WCAG AA)
- Große Schrift ab 24 px oder 19 px fett: mindestens **3 : 1**
- Bedienelemente und Fokusring gegen ihre Umgebung: mindestens **3 : 1**
- **In beiden Themes geprüft**, nicht nur im Standard-Theme

Der letzte Punkt betrifft heute konkret die Diff-Ansicht: feste Grün- und Rot-Werte auf
hellem Grund, die im Dunkelmodus unlesbar werden.

### 8.6 Theming-System

**Anforderung (2026-07-31):** Farben sollen austauschbar sein — nicht nur zwischen Hell und
Dunkel, sondern als benannte Paletten. Das ist mehr als der heutige `ThemeContext`, der
genau zwei feste Werte kennt.

**Best Practice, zwei Token-Ebenen statt einer.** Design-Systeme, die Themes tatsächlich
austauschbar halten (Material Design 3, Adobe Spectrum, IBM Carbon), trennen konsequent:

| Ebene | Beispiel | Ändert sich mit dem Theme? |
|---|---|---|
| **Primitiv** | `--palette-indigo-500: #6366f1` | nein — Rohfarbwerte, ein Satz pro Theme |
| **Semantisch** | `--color-primary: var(--palette-indigo-500)` | ja — zeigt je nach aktivem Theme auf ein anderes Primitiv |

Komponenten referenzieren **ausschließlich** die semantische Ebene (`--color-primary`,
`--color-surface`, `--color-badge-success-bg`, …) — das ist bereits die Regel aus Kapitel 8.1
und wird durch das ESLint-Gate aus Kapitel 16.1 erzwungen. Ein neues Theme fügt lediglich
einen neuen Primitiv-Satz hinzu und mappt die bestehenden semantischen Namen darauf — **kein
Component-Code ändert sich.** Ohne diese Trennung müsste jedes neue Theme jede Komponente
einzeln anfassen, was Theming in der Praxis unmöglich macht.

**Umsetzung:**

- `ThemeContext` wird von einem Boolean (`isDark`) zu einer Theme-ID erweitert
  (`activeTheme: string`), `data-theme={activeTheme}` statt `data-theme="dark"`.
- Jedes Theme ist ein vollständiger Primitiv-Satz in `tokens.css` unter
  `:root[data-theme="<id>"]` — analog zum bestehenden Light/Dark-Block, nicht als neue
  Mechanik.
- Zwei Themes sind zum Start Pflicht (Migration aus dem heutigen Zustand): `default-dark`
  und `default-light`, byte-identisch zu den heutigen Werten — Theming ist eine
  Erweiterung, kein Redesign der bestehenden Palette (Kapitel 4).
- **Kontrastprüfung pro Theme, nicht einmalig.** Jedes neue Theme durchläuft dieselbe
  4,5:1-Prüfung aus 8.5, bevor es freigegeben wird — sonst wiederholt sich der
  Diff-Ansicht-Fehler (feste Werte, die in einem Kontext unlesbar werden) mit jedem
  weiteren Theme.
- **Auswahl:** Workspace-Setting mit User-Override, analog zum bestehenden Sprachumschalter
  — Theme ist eine Präferenz, keine Tenant-Policy.
- **Kein neues Farbkonzept.** Kapitel 8.1–8.5 (Farbe kodiert nur Status, Statuspalette,
  Kontrastregeln) gelten unverändert für **jedes** Theme. Theming tauscht die Werte hinter
  den semantischen Tokens aus, nicht deren Bedeutung.

---

## 9. Typografie

Hier wird ein Teil der gestalterischen Freiheit ausgegeben.

### 9.1 Die Empfehlung

**Eine Familie, drei Schnitte: IBM Plex Sans, IBM Plex Mono, IBM Plex Sans Condensed.**

Begründung aus dem Gegenstand:

- **IBM Plex wurde für technische Produkte entworfen.** Das ist keine Anmutung, sondern
  die Entstehungsgeschichte der Schrift. Sie sitzt in derselben Welt wie dieses Werkzeug.
- **Der Mono-Schnitt gehört zur Familie.** IDs, Diffs, JSON und UUIDs sind hier
  Kerninhalt, kein Randfall. Eine passende Mono aus derselben Hand löst das, ohne dass
  zwei Schriftwelten aufeinandertreffen.
- **Eindeutige Ziffern und Buchstaben.** `0` trägt einen Punkt, `1`, `l` und `I` sind
  klar unterscheidbar. Bei Bezeichnern wie `SYS-REQ-001` ist das kein Detail.
- **Condensed für Tabellenköpfe und Badges** — dort, wo Platz knapp und Text kurz ist,
  ohne die Schriftgröße zu opfern.
- **Offene Lizenz (OFL)**, selbst hostbar. Das ist Voraussetzung, nicht Zugabe (9.5).

### 9.2 Was sich damit ändert

Heute läuft die Oberfläche in **Outfit**, mit **Inter** als Rückfall. Outfit ist eine
geometrische Display-Schrift: weite Rundungen, sehr ähnliche `0` und `O`, für Überschriften
gedacht — nicht für dichte Bezeichnerlisten. Im Screenshot ist `SYS-REQ-001` genau deshalb
schwerer zu scannen, als es sein müsste.

Die Umstellung ist ein Ersetzen der Familie in einem Token. Der Aufwand liegt im
Selbst-Hosten, das ohnehin ansteht.

> **Falls Outfit bleiben soll:** Dann muss trotzdem ein Mono-Schnitt dazukommen und
> `font-variant-numeric: tabular-nums` gesetzt werden. Die Empfehlung oben ist die
> saubere Lösung; die Mindestanforderung ist der Mono-Schnitt.

### 9.3 Rollen

| Rolle | Schnitt | Verwendung |
|---|---|---|
| **Titel** | Plex Sans, 600 | Seitenüberschrift, Artefakttitel |
| **Fließtext** | Plex Sans, 400 | Beschreibungen, Erklärungen, Hilfetexte |
| **Auszeichnung** | Plex Sans, 500 | Labels, Buttons, Navigationseinträge |
| **Bezeichner** | Plex **Mono**, 400 | IDs, Versionen, Diffs, JSON, Schlüssel |
| **Kleintext** | Plex Sans **Condensed**, 500 | Badges, Tabellenköpfe, Zähler |

### 9.4 Skala

```
--font-size-xs    0.75rem    12px    Badges, Zähler, Fußnoten
--font-size-sm    0.875rem   14px    Labels, Sekundärtext, Metadaten
--font-size-base  1rem       16px    Fließtext, Formularfelder
--font-size-md    1.0625rem  17px    Abschnittsüberschriften        ← fehlt heute
--font-size-lg    1.125rem   18px    Artefakttitel in Listen
--font-size-xl    1.25rem    20px    Detail-Artefakttitel
--font-size-2xl   1.5rem     24px    Panel-Überschriften
--font-size-3xl   1.875rem   30px    Seitenüberschrift <h1>         ← fehlt heute
```

**Zwei Stufen fehlen heute, und eine davon ist ein aktiver Fehler:**

`--font-size-md` wird an **zehn Stellen** für Abschnittsüberschriften verwendet und ist
**nirgends definiert**. Live gemessen:

```
xs=0.75rem  sm=0.875rem  base=1rem  md=UNDEFINED  lg=1.125rem  xl=1.25rem  2xl=1.5rem
```

Eine undefinierte Custom Property macht die Deklaration *invalid at computed-value time*
— `font-size` fällt auf den geerbten Wert zurück. Jede dieser Überschriften rendert seit
jeher in Fließtextgröße. Erkennbar bleibt sie nur an Schriftschnitt und Unterlinie. Im
Quelltext sieht die Zeile korrekt aus; deshalb ist es niemandem aufgefallen.

`--font-size-3xl` fehlt schlicht — die Seitenüberschrift hat heute keine eigene Stufe und
steht mit 18 px nur anderthalb Schritte über dem Listeneintrag.

### 9.5 Zeilenhöhe und Laufweite

Fehlen heute vollständig als Tokens.

```
--leading-tight    1.15    Überschriften ab --font-size-2xl
--leading-normal   1.5     Fließtext, Listeneinträge
--leading-relaxed  1.7     lange Beschreibungen, Markdown-Inhalte
--tracking-tight  -0.02em  große Grade
--tracking-normal  0
--tracking-wide    0.06em  Kleintext in Versalien, Badges, Eyebrows
```

Lange Requirement-Beschreibungen laufen mit `--leading-relaxed` und einer maximalen
Zeilenlänge von **72 Zeichen** (`max-width: 72ch`). Über die volle Breite eines
1440-px-Fensters gesetzter Fließtext ist nicht lesbar, nur vorhanden.

### 9.6 Zahlen und Bezeichner

- **`font-variant-numeric: tabular-nums`** überall dort, wo Zahlen untereinander stehen:
  Versionen, Zähler, Metrikkacheln, Tabellen. Ohne das springen Zahlenkolonnen.
- **IDs immer in Mono**, immer in derselben Größe, immer mit `user-select: all`.
- **Keine Abkürzung von IDs** in Listen. Wenn der Platz nicht reicht, ist die Spalte zu
  schmal, nicht die ID zu lang.

### 9.7 Selbst hosten

Heute lädt `global.css:1` beide Schriften zur Laufzeit von Google Fonts per CSS-`@import`.
Das hat drei Probleme, von denen das erste das gravierendste ist:

1. **Ohne Internetzugang bricht die Typografie weg.** Für ein Werkzeug mit Multi-Tenancy,
   RLS und Audit-Log ist ein abgeschottetes Netz eine realistische Zielumgebung. Die
   Oberfläche fällt dann auf `system-ui` zurück — und niemand bemerkt es beim Deployment.
2. **Datenschutz.** Jeder Seitenaufruf sendet IP und User-Agent an einen Dritten.
3. **Ladezeit.** `@import` an erster Stelle blockiert das Rendern; zwei zusätzliche
   Verbindungen entstehen, bevor der erste Text erscheint.

**Lösung:** `@fontsource/ibm-plex-sans` und `@fontsource/ibm-plex-mono` als Abhängigkeit,
Import in `src/index.tsx`, nur die benutzten Schnitte, `font-display: swap`.

---

## 10. Abstand und Rhythmus

### 10.1 Skala

Die vorhandene 4-px-Skala bleibt: `--space-1` bis `--space-8` (4, 8, 12, 16, 20, 24, 32 px).
Sie ist ausreichend und konsistent.

### 10.2 Vergabe

| Verhältnis | Abstand |
|---|---|
| innerhalb einer Zeile (Badge zu ID zu Version) | `--space-2` |
| zwischen Feld und Label | `--space-1` |
| zwischen Formularfeldern | `--space-4` |
| zwischen Abschnitten | `--space-6` |
| Innenabstand von Karten und Panels | `--space-6` |
| zwischen Zonen (Liste zu Detail) | `--space-6` |

Regel: **Näher zusammen heißt enger verwandt.** Ein Label gehört zu seinem Feld, also
`--space-1`. Zwei Abschnitte sind unabhängig, also `--space-6`. Wo diese Beziehung heute
nicht stimmt — vier ungleich ausgerichtete Zeilen in der Requirements-Toolbar —, entsteht
der Eindruck von Zufall.

### 10.3 Ausrichtung

- Alles in einer Zone teilt eine linke Kante.
- Bedienelemente in einer Reihe teilen eine gemeinsame Grundlinie.
- Filter derselben Reihe haben **gleiche Breite**, außer der Suche, die wächst.

---

## 11. Bewegung

Zurückhaltend. Dies ist ein Werkzeug für stundenlange Arbeit, keine Präsentation.

### 11.1 Was sich bewegt

| Zweck | Dauer | Kurve |
|---|---|---|
| Zustandswechsel (Hover, Auswahl, Fokus) | 150 ms | `--transition-fast` |
| Ein- und Ausblenden (Panels, Dialoge) | 250 ms | `--transition-normal` |
| Positionswechsel (Baum auf-/zuklappen) | 250 ms | `--transition-normal` |

### 11.2 Was sich nicht bewegt

- Keine Einblendanimation beim Seitenaufbau. Wer alle zehn Minuten die Ansicht wechselt,
  will sie sofort sehen.
- Kein Anheben von Karten beim Überfahren. Die Regel `.glass-panel:hover { transform:
  translateY(-2px) }` erzeugt bei Listen mit vielen Karten ein unruhiges Bild.
- Keine Ladeanimation unter 300 ms. Was schnell da ist, braucht keine Ankündigung.

### 11.3 Reduzierte Bewegung

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Heute steht diese Regel in vier CSS-Modulen. Sie gehört **einmal** nach `global.css` und
muss dort auch `scroll-behavior: smooth` aufheben, das aktuell global gesetzt ist.

---

## 12. Komponentenkatalog

Die verbindlichen Bausteine. Wer eine Ansicht baut, setzt sie zusammen — er baut sie
nicht nach.

### 12.1 `<PageHeader>`

```
┌────────────────────────────────────────────────────────────────────┐
│  System Requirements                        [ Neues Requirement ]  │
│  128 Requirements · 12 in Prüfung                            [ ⋯ ] │
└────────────────────────────────────────────────────────────────────┘
```

```tsx
<PageHeader
  title="System Requirements"                  // immer genau ein <h1>
  summary="128 Requirements · 12 in Prüfung"   // immer, nicht nur bei Filter
  primaryAction={{ label: 'Neues Requirement', onClick }}
  overflowActions={[exportPdf, importCsv, createBaseline]}
/>
```

**Regeln**
- Überschrift immer `<h1>`, `--font-size-3xl`, `--leading-tight`, `--tracking-tight`.
  Nie `h2`, nie `h3`, nie weggelassen.
- **Zusammenfassung immer sichtbar.** Sie ersetzt den heutigen Zähler, der nur bei
  aktivem Filter erscheint. Sie beantwortet die häufigste Frage an ein solches Werkzeug
  („wie viele haben wir?") sofort — und macht still abgeschnittene Listen bemerkbar.
- **Genau eine** Primäraktion, oben rechts, gefüllt. Sie benennt das **Ergebnis**
  („Neues Requirement"), nicht die Geste („+ New").
- Alles Weitere ins Überlaufmenü. Export und Import sind seltene Aufgaben.

**Behebt:** fünf Kopfmuster, zwei Seiten ohne Überschrift, acht Seiten ohne `h1`,
Primäraktion unterhalb der Filter, uneinheitliche Aktionsbeschriftungen.

### 12.2 `<ListToolbar>`

```
┌─────────────────────────────────────────────────────────────────────┐
│  🔍 Suchen…                        [ Status ▾ ]  [ Sortierung ▾ ]   │
└─────────────────────────────────────────────────────────────────────┘
```

**Feste Reihenfolge:** Suche (wächst) → Filter (feste, gleiche Breite) → Sortierung.

**Regeln**
- Eine Zeile, eine Grundlinie. Bricht erst unter `--bp-md` um.
- Filter schrumpfen nicht unter ihre lesbare Breite. Ein Filter, der nur noch als
  Pfeilsymbol erscheint, ist kein Filter mehr.
- **Keine Primäraktion in der Leiste.** Die gehört in den Kopf.
- Ein einzelner Filter wird nicht über die volle Breite gezogen.
- Aktive Filter erscheinen als entfernbare Chips darunter.

**Gilt auch für** Glossar, ICDs, Baselines, Test Runs und Trace Links, die ihre Leiste
heute selbst bauen.

### 12.3 `<ArtifactRow>`

```
┌──────────────────────────────────────────────────────────────────────┐
│  SYS-REQ-001   L1                              ● Freigegeben    v3   │
│  Hauptfunktion des Systems                                           │
└──────────────────────────────────────────────────────────────────────┘
```

**Zweizeilig.** Identität oben, Titel unten. Beim Überfliegen sucht das Auge die ID, beim
Lesen den Titel — beide brauchen ihre Zeile.

| Position | Inhalt | Darstellung |
|---|---|---|
| oben links | ID | `<ArtifactId>`, Mono |
| oben links, daneben | Ebene / Typ | `<LevelBadge>`, neutral |
| oben rechts | Status | `<StatusBadge>`, farbkodiert |
| oben rechts, ganz außen | Version | `<VersionBadge>`, nur bei > 1 |
| unten | Titel | `--font-size-lg`, eine Zeile, bei Bedarf gekürzt |

Auswahl wird über Fläche und eine 3 px starke linke Kante in `--color-primary` angezeigt
— nicht über Textfarbe.

### 12.4 Identitäts-Bausteine

Vier kleine Komponenten, die zusammen Prinzip 3.1 durchsetzen.

```
  SYS-REQ-001    L1     ●  In Prüfung     v3
  └── ID ────┘  └Ebene┘ └─── Status ───┘  └Version┘
```

| Komponente | Regel |
|---|---|
| `<ArtifactId>` | `--font-mono`, `--font-size-sm`, `user-select: all`, Klick kopiert mit Bestätigung, übersetzter Tooltip |
| `<LevelBadge>` | **neutral** — Ebene ist kein Zustand |
| `<StatusBadge>` | **einzige** farbkodierte Angabe, immer über `getStatusBadgeStyle` |
| `<VersionBadge>` | neutral, `tabular-nums`, nur ab Version 2 |

**Behebt:** drei Status-Implementierungen (eine gefärbt, drei grau kopiert, drei fehlend),
vier inline duplizierte ID-Darstellungen, widersprüchliche Badge-Semantik.

### 12.5 `<Tree>`

**Eine** Primitive: `shared/WorkspaceTree`, erweitert um den vereinigten Funktionsumfang
der heutigen drei Implementierungen.

| Fähigkeit | heute vorhanden in |
|---|---|
| Auf-/Zuklappen, Auswahl | alle drei |
| Virtualisierung | `WorkspaceTree` |
| Suche und Filter im Baum | `WorkspaceTree`, `DecompositionTree` |
| Tastaturnavigation | nur `DecompositionTree` |
| Drag & Drop zum Umhängen | nur `DecompositionTree` |
| `role="tree"` / `treeitem` | `WorkspaceTree`, `DecompositionTree` |

Kein Baum kann heute alles. Artefaktspezifisches läuft künftig über Render-Props (Badge,
Kontextmenü) — nicht über eine neue Implementierung.

**Tastaturbedienung, überall gleich** (ARIA-Standard für Bäume):

| Taste | Wirkung |
|---|---|
| `↑` `↓` | vorheriger / nächster sichtbarer Knoten |
| `→` | aufklappen; ist bereits offen, zum ersten Kind |
| `←` | zuklappen; ist bereits zu, zum Elternknoten |
| `Home` `End` | erster / letzter Knoten |
| Buchstabe | zum nächsten Knoten mit diesem Anfangsbuchstaben |
| `Enter` | im Detailbereich öffnen |
| `*` | alle Geschwister aufklappen |

Heute erfüllt das genau einer von drei Bäumen.

### 12.6 `<SplitView>`

Trägt das Layout- **und** das Scroll-Modell. Die zentrale Stelle, an der beide Regeln
verankert werden.

```tsx
<SplitView
  list={<RequirementList />}
  detail={selected ? <RequirementDetail /> : null}
  spine={selected ? <TraceSpine artifact={selected} /> : null}
  ratio={[40, 60]}
  minWidths={[380, 520]}
/>
```

Ohne `detail` läuft `list` über die volle Breite. Beide Bereiche bekommen genau eine
Scroll-Fläche mit `overscroll-behavior: contain`.

### 12.7 `<EmptyState>`

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

Drei Rollen: **Titel** (was fehlt), **ein Satz** (was hier entsteht und wozu), **Aktion**
(der nächste Schritt). Siehe Kapitel 13 für die Varianten.

### 12.8 `<Dialog>`

Verbindliche Primitive auf Basis von `RequirementsList/ModalDialogBase.tsx`.

```tsx
<Dialog title="Neues Requirement" onClose={...}>
  …
</Dialog>
```

**Pflichten**
- `role="dialog"` **und** `aria-modal="true"` **und** `aria-labelledby={titleId}`

  Heute nutzen neun Dateien `aria-modal` **ohne** `role="dialog"`. Nach ARIA-Spezifikation
  ist das wirkungslos — Screenreader behandeln das Element weiter als normalen Container.
- Fokus beim Öffnen auf das erste bedienbare Element
- Fokus-Falle innerhalb des Dialogs
- `Escape` schließt
- Fokus kehrt beim Schließen auf das auslösende Element zurück
- Titel des Dialogs = Beschriftung des auslösenden Knopfes

### 12.9 `<StatusEditor>`

Der vorhandene `WorkflowStatusEditor` bleibt. Er sitzt künftig **im Artefaktkopf** neben
dem `<StatusBadge>`, nicht mitten im Formular — der Status ist eine Eigenschaft des
Artefakts, kein Feld unter anderen.

Nur erlaubte Übergänge werden angeboten. Ein gesperrter Übergang erklärt beim Überfahren,
warum.

### 12.10 `<TraceSpine>`

Siehe Kapitel 5. Die Stationen sind **kein** festes Array — sie werden aus der realen
Ableitungskette des Artefakts aufgelöst (Baumtiefe je Vorfahre/Nachfahre), Verifikation
kommt als Badge pro Station, nicht als eigene Station.

```tsx
<TraceSpine
  artifact={selected}
  chain={useDerivationChain(selected)}   // N Stationen, dynamisch aus get_level()
  onSelectStation={(station) => openLinkedPanel(station)}
  onSelectVerification={(station) => openTestPanel(station)}
/>
```

### 12.11 Dynamische Artefakt-Attribute

**Anforderung (2026-07-31):** Die Menge und der Typ der Attribute pro Artefakttyp ist nicht
fix — `CustomFieldDefinition`/`CustomFieldValue` (tenant-scoped) existieren im Datenmodell
bereits für genau diesen Zweck, werden aber laut Audit nirgends angezeigt (#29).

Detail-Formulare (`<ArtifactInspector>` und seine Editoren) rendern deshalb zwei Blöcke:

1. **Feste Felder** — die eingebauten Attribute des Artefakttyps (Titel, Beschreibung, …),
   wie heute.
2. **Dynamischer Block** — eine Schleife über `CustomFieldDefinition` für den aktuellen
   Artefakttyp/Workspace, ein Eingabe-Widget pro `CustomFieldType` (Text, Zahl, Auswahl, …).
   Neue Felder erscheinen ohne Codeänderung, sobald sie im Workspace definiert werden.

Das ist keine neue Fähigkeit, sondern das Nachholen einer bereits vorhandenen: Backend und
Datenmodell unterstützen variable Attribute seit längerem, die Oberfläche zeigt sie nur
nicht an.

### 12.12 `<Alert>` und Rückmeldungen

| Art | Darstellung | Dauer |
|---|---|---|
| Erfolg | Toast unten rechts | 4 s, automatisch |
| Fehler bei Aktion | `role="alert"` im Formular, nahe der Ursache | bleibt |
| Fehler beim Laden | im Inhaltsbereich, mit „Erneut versuchen" | bleibt |
| Hinweis | im Fluss, nicht überlagernd | bleibt |

**Wichtig:** Heute gibt es in `frontend/src/components/` **46 `console.error`-Aufrufe und
null `role="alert"`**. In mehreren Ansichten schließt sich das Formular auch bei einem
Fehler — der Nutzer glaubt, gespeichert zu haben.

Regel: **Jede fehlgeschlagene Aktion erzeugt eine sichtbare Meldung, und das Formular
bleibt offen.** Der Helfer dafür existiert bereits (`api/client.ts:229`,
`extractErrorMessage`).

---

## 13. Zustände

Jede Ansicht kennt sechs Zustände. Keiner wird ausgelassen.

### 13.1 Übersicht

| Zustand | Aussage | Aktion |
|---|---|---|
| **Lädt** | Platzhalter in der späteren Form | — |
| **Leer** | was hier entsteht und wozu | anlegen, importieren |
| **Kein Treffer** | welcher Filter greift | Filter zurücksetzen |
| **Fehler** | was schiefging, was jetzt hilft | erneut versuchen |
| **Keine Rechte** | welche Rolle nötig ist | wer sie vergeben kann |
| **Gefüllt** | der Normalfall | — |

### 13.2 Laden

Platzhalter in der Form des späteren Inhalts, nicht ein zentriertes Rädchen. Sie belegen
die spätere Höhe, damit beim Eintreffen der Daten nichts springt.

Unter 300 ms wird nichts angezeigt.

### 13.3 Leer gegen kein Treffer

Diese beiden werden heute nicht unterschieden, und der Unterschied ist wesentlich:

- **Leer** heißt: Es gibt nichts. Der nächste Schritt ist *anlegen*.
- **Kein Treffer** heißt: Es gibt etwas, aber nicht mit diesem Filter. Der nächste
  Schritt ist *Filter zurücksetzen*.

Ein „Neues Requirement"-Knopf im Filterfall ist die falsche Antwort auf die falsche Frage.

### 13.4 Fehler

Fehler entschuldigen sich nicht und bleiben konkret.

```
  Requirement konnte nicht gespeichert werden

  Der Titel ist bereits vergeben (SYS-REQ-001).
  Wähle einen anderen Bezeichner.

  [ Erneut versuchen ]
```

Nicht: „Ein Fehler ist aufgetreten." Nicht: „Sorry, something went wrong."

### 13.5 Der leere Detailbereich

Entfällt. Solange nichts gewählt ist, läuft die Liste über die volle Breite (6.2). Kein
zentrierter grauer Satz in 620 px Leerfläche.

---

## 14. Sprache

Wörter sind Gestaltungsmaterial. Sie bekommen dieselbe Sorgfalt wie Abstände.

### 14.1 Grundregeln

- **Aus Sicht des Nutzers benennen**, nicht aus Sicht des Systems. Man verwaltet
  *Anforderungen*, keine *Artefakt-Entitäten*.
- **Aktiv und konkret.** Ein Bedienelement sagt, was passiert.
- **Ein Name über den ganzen Ablauf.** Der Knopf „Baseline anlegen" führt zum Dialog
  „Baseline anlegen" und endet in der Meldung „Baseline angelegt".
- **Ein Element, eine Aufgabe.** Ein Label beschriftet. Ein Beispiel zeigt. Nichts tut
  beides nebenbei.
- **Fachbegriffe, wo sie tragen.** „Baseline", „Trace Link" und „Requirement" sind
  Fachsprache der Zielgruppe und bleiben. „Outdate" ist es nicht.

### 14.2 Konkret

| statt | besser | warum |
|---|---|---|
| `+ New` | `Neues Requirement` | benennt das Ergebnis |
| `Submit` | `Speichern` | sagt, was passiert |
| `No items found.` | `Noch keine Requirements` | nennt den Gegenstand |
| `No trace links available.` | `Noch keine Verknüpfungen` | aktiv statt passiv |
| `Select a need from the list.` | *(entfällt)* | kein leeres Panel |
| `SR` | `System Requirement` | der Platz ist da |
| `Outdate` | `Als veraltet markieren` | beschreibt die Wirkung |
| `Unique Identifier` | `Bezeichner — zum Kopieren klicken` | sagt, was man tun kann |

### 14.3 Eine Sprache pro Oberfläche

Heute stehen nebeneinander:

- das deutsche „Suchen…" der Navigation und das englische „Search by title or ID…"
- ein Workflow-Editor mit **23 Dateien ohne `useTranslation`** — vollständig unübersetzt
- ein Impact-Analysis-Bereich komplett auf Deutsch, während der Rest Englisch spricht
- drei Schlüssel, die in `de.json` fehlen — ausgerechnet bei den Löschbestätigungen

**Regel:** Jeder benutzersichtbare Text läuft über i18n. Ein Test prüft die
Schlüssel-Parität zwischen `en.json` und `de.json` und schlägt bei Abweichung fehl.

---

## 15. Barrierefreiheit als Grundniveau

Kein eigenes Kapitel im Sinne von „danach noch prüfen". Zielniveau **WCAG 2.1 AA**, und
zwar als Eingangsbedingung.

### 15.1 Die harte Liste

| Anforderung | Stand heute |
|---|---|
| Sichtbarer Fokus auf **allen** bedienbaren Elementen | **fehlt** — `global.css:41` setzt `outline: none` ohne Ersatz; gemessen an einem echten Knopf: `outlineStyle: none, boxShadow: none` |
| Genau ein `<h1>` je Seite, lückenlose Überschriftenkette | **2 von 10 Routen** haben ein `h1` |
| Dialoge mit `role="dialog"`, Fokus-Falle, `Escape` | `aria-modal` in 9 Dateien, `role="dialog"` in **0** |
| Fehler als `role="alert"` angekündigt | **0** Vorkommen bei 46 `console.error` |
| Bäume mit Tastaturbedienung nach ARIA-Muster | 1 von 3 Bäumen |
| Kontrast 4,5 : 1 in **beiden** Themes | 128 Hex-Literale umgehen das Theme |
| `prefers-reduced-motion` respektiert | in 4 CSS-Modulen, nicht global |
| Bedienbar ohne Maus, Ende zu Ende | ungeprüft |

### 15.2 Grundsatz

Barrierefreiheit ist hier kein Zusatz für einen Sonderfall. Ein Requirements-Werkzeug
wird über Tastatur bedient, sobald jemand schnell darin arbeitet: Suchen, Pfeil runter,
Enter, Tab, tippen, speichern. Wer den Fokus nicht sieht, kann das nicht — mit oder ohne
Einschränkung.

Der fehlende Fokusring ist deshalb der teuerste Einzelbefund dieses Konzepts, gemessen an
Behebungsaufwand gegen Wirkung.

---

## 16. Durchsetzung

Das eigentliche Thema. Die gemeinsamen Komponenten gab es schon vorher — sie wurden nur
nicht benutzt. Ohne diesen Teil läuft alles oben in zwei Jahren wieder auseinander.

### 16.1 Automatisch prüfbar

| Prüfung | Werkzeug | Verhindert |
|---|---|---|
| Jede `var(--token)`-Referenz existiert in `tokens.css` | Test | das `--font-size-md`-Problem |
| Schlüssel-Parität `en.json` ↔ `de.json` | Test | fehlende Übersetzungen |
| Genau ein `<h1>` je Route | E2E | Kopf-Wildwuchs |
| Keine Hex-Literale in `style={{}}` | ESLint | Theme-Umgehung |
| `aria-modal` nur zusammen mit `role="dialog"` | ESLint | wirkungslose Dialoge |
| Kein `waitForTimeout` in E2E | ESLint | instabile Tests |
| Anzahl `style={{}}` sinkt monoton | Ratchet-Test | Rückfall |
| Anzahl Scroll-Container je Route ≤ 3 | E2E | Scroll-Wildwuchs |

### 16.2 Ratchet statt Verbot

Für Altlasten gilt das Sperrklinken-Prinzip: Der aktuelle Wert wird festgehalten, und der
Test schlägt fehl, sobald er **steigt**. Das erlaubt schrittweises Aufräumen ohne einen
großen Umbau vorab.

Das Muster existiert im Projekt bereits — `rest_api/tests/test_architecture.py` macht
genau das für direkte ORM-Zugriffe. Es fehlt nur im Frontend.

Startwerte in [Anhang B](#anhang-b-messwerte).

### 16.3 Durch Menschen

- **Eine Ansicht wird zusammengesetzt, nicht nachgebaut.** Wer eine neue Komponente
  braucht, weil eine vorhandene nicht passt, erweitert die vorhandene.
- **Neue Muster gehören in dieses Dokument**, bevor sie in den Code gehen.
- **Im Review gilt die Frage:** Gibt es das schon? Bei fünf Kopfmustern und drei Bäumen
  war die Antwort jedes Mal ja.

---

## 17. Umsetzungsreihenfolge

Nach Wirkung je Aufwand. Die ersten beiden Schritte sind klein und tragen weit.

### Schritt 0 — Pilot an drei Artefakttypen

*vor Schritt 1 · Validierung, kein flächendeckender Umbau*

Bevor das Konzept über zehn Routen ausgerollt wird, wird es an drei Artefakttypen mit
unterschiedlichem Belastungsprofil geprüft:

- **Goals/MainGoal** — neuester Artefakttyp, kleinster Bestandscode, geringstes
  Regressionsrisiko.
- **Architecture** — prüft die dynamische Spine (Kapitel 5.2) gegen echte, unterschiedlich
  tiefe Bäume und die Baum-Primitive (Kapitel 12.5).
- **Needs** — prüft `<PageHeader>`, `<ListToolbar>` und dynamische Attribute
  (Kapitel 12.11) an einem etablierten, gut genutzten Artefakttyp.

**Abnahmekriterium:** Für jeden der drei Piloten gilt die funktionale Untergrenze aus
Kapitel 4 — mindestens derselbe Funktionsumfang wie die heutige Seite, geprüft anhand einer
Liste der heute vorhandenen Fähigkeiten (Filter, Sortierung, Export, Bearbeitungsfelder,
Aktionen) vor Beginn der Umstellung. Erst nach erfolgreichem Piloten an allen drei Typen
beginnt der flächendeckende Rollout ab Schritt 1.

### Schritt 1 — Fundament

*klein · wirkt auf jeder Seite*

- Fehlende Tokens ergänzen: `--font-size-md`, `--font-size-3xl`, `--font-mono`,
  `--color-focus`, `--color-nav-bg`, Zeilenhöhen, Haltepunkte
- `outline: none` in `global.css:41` durch globales `:focus-visible` ersetzen
- Navigationsfarbe auf ein Token ziehen
- `prefers-reduced-motion` global setzen
- Test: jede `var(--token)`-Referenz existiert

→ #158, #174, #157, #164

### Schritt 2 — Identität

*klein · überall sichtbar*

- `<StatusBadge>`, `<ArtifactId>`, `<LevelBadge>` bauen
- In allen sieben Detail-Köpfen und allen Listen einsetzen
- Die drei Inline-Kopien und vier ID-Duplikate entfernen
- Farbe ausschließlich für Status

→ #173, #183, #182

### Schritt 3 — Seitenkopf

*mittel*

- `<PageHeader>` bauen, alle zehn Routen umstellen
- Zusammenfassung immer sichtbar
- Sekundäraktionen ins Überlaufmenü
- E2E: genau ein `h1` je Route

→ #172, #178

### Schritt 4 — Scrollen und Massen

*mittel · größte spürbare Wirkung*

- Scroll-Modell in `SplitView` verankern, `overscroll-behavior: contain`
- Scrollbalken sichtbar, Position merken
- Virtualisierung für alle Listen über die gemeinsame Primitive
- `glossary.ts` und `diagrams.ts` auf vollständiges Laden umstellen
- Eine Nachlade-Strategie statt drei

→ #176, #177, #185

### Schritt 5 — Bäume

*groß*

- `WorkspaceTree` um Tastaturbedienung und Drag & Drop erweitern
- `DecompositionTree` und `RequirementTreeNode` darauf umstellen
- Artefaktspezifisches über Render-Props

→ #175

### Schritt 6 — Layout, Zustände, Spine

*groß*

- Split-View für Glossar und Trace Links
- Haltepunkte `--bp-md` und `--bp-lg`
- `<EmptyState>` mit allen sechs Zuständen
- `<Dialog>` mit `role="dialog"` und Fokus-Falle
- **Trace-Spine**

→ #179, #180, #160, #166, #157

### Schritt 7 — Schrift

*mittel · unabhängig, jederzeit einschiebbar*

- Selbst hosten (behebt Air-Gap und Datenschutz)
- Umstellung auf IBM Plex Sans / Mono / Condensed
- `tabular-nums` überall dort, wo Zahlen untereinander stehen

→ #165, #163

---

## Anhang A: Token-Referenz

Vollständige Sollmenge. **Fett** = fehlt heute.

```css
:root {
  /* ── Farbe: Flächen ───────────────────────────────────── */
  --color-surface:          #0f172a;
  --color-surface-raised:   #1e293b;
  --color-nav-bg:           #1a1f2e;    /* NEU — heute hartkodiert */
  --color-border:           #334155;
  --color-border-hover:     #475569;

  /* ── Farbe: Text ──────────────────────────────────────── */
  --color-text:             #f8fafc;
  --color-text-muted:       #94a3b8;

  /* ── Farbe: Aktion und Zustand ────────────────────────── */
  --color-primary:          #6366f1;
  --color-primary-dark:     #4f46e5;
  --color-focus:            #818cf8;    /* NEU — heute kein Fokusring */
  --color-success:          #10b981;
  --color-warning:          #f59e0b;
  --color-danger:           #ef4444;

  /* ── Farbe: Status-Badges (vorhanden, vollständig) ────── */
  --color-badge-neutral-bg / -text;     /* Entwurf */
  --color-badge-info-bg    / -text;     /* In Prüfung */
  --color-badge-success-bg / -text;     /* Freigegeben */
  --color-badge-warning-bg / -text;     /* Veraltet */
  --color-badge-danger-bg  / -text;     /* Abgelehnt */

  /* ── Schrift: Familien ────────────────────────────────── */
  --font-sans:  'IBM Plex Sans', system-ui, sans-serif;
  --font-mono:  'IBM Plex Mono', ui-monospace, monospace;   /* NEU */
  --font-cond:  'IBM Plex Sans Condensed', var(--font-sans); /* NEU */

  /* ── Schrift: Größen ──────────────────────────────────── */
  --font-size-xs:   0.75rem;
  --font-size-sm:   0.875rem;
  --font-size-base: 1rem;
  --font-size-md:   1.0625rem;   /* NEU — 10 Verwendungen, nie definiert */
  --font-size-lg:   1.125rem;
  --font-size-xl:   1.25rem;
  --font-size-2xl:  1.5rem;
  --font-size-3xl:  1.875rem;    /* NEU — für <h1> */

  /* ── Schrift: Rhythmus ────────────────────────────────── */
  --leading-tight:   1.15;       /* NEU */
  --leading-normal:  1.5;        /* NEU */
  --leading-relaxed: 1.7;        /* NEU */
  --tracking-tight: -0.02em;     /* NEU */
  --tracking-normal: 0;          /* NEU */
  --tracking-wide:   0.06em;     /* NEU */
  --measure:         72ch;       /* NEU — max. Zeilenlänge Fließtext */

  /* ── Schrift: Gewichte ────────────────────────────────── */
  --weight-regular:  400;        /* NEU */
  --weight-medium:   500;        /* NEU */
  --weight-semibold: 600;        /* NEU */

  /* ── Abstand (vorhanden) ──────────────────────────────── */
  --space-1 … --space-8;         /* 4 8 12 16 20 24 32 px */

  /* ── Radius (vorhanden) ───────────────────────────────── */
  --radius-sm: 6px;  --radius-md: 12px;
  --radius-lg: 16px; --radius-full: 9999px;

  /* ── Schatten (vorhanden) ─────────────────────────────── */
  --shadow-sm / -md / -card / -glow;

  /* ── Bewegung (vorhanden) ─────────────────────────────── */
  --transition-fast:   150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-normal: 250ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow:   400ms cubic-bezier(0.4, 0, 0.2, 1);

  /* ── Layout ───────────────────────────────────────────── */
  --nav-width:     240px;        /* NEU */
  --list-min:      380px;        /* NEU */
  --detail-min:    520px;        /* NEU */
  --bp-md:         768px;        /* NEU */
  --bp-lg:        1024px;        /* NEU */
}
```

Jedes neue Token wird **im Light-Theme-Block gespiegelt**, wo es farbabhängig ist. Der
vorhandene Spiegel in `tokens.css:86-129` ist vollständig und bleibt es.

---

## Anhang B: Messwerte

Erhoben am 2026-07-28 an der laufenden Anwendung über zehn Routen. Startwerte für die
Sperrklinken-Tests aus 16.2.

| Kennzahl | Stand | Ziel |
|---|---:|---:|
| Seitenkopf-Muster über 10 Routen | 5 | 1 |
| Routen mit `<h1>` | 2 / 10 | 10 / 10 |
| Status-Badge-Implementierungen | 3 | 1 |
| Navigationsbaum-Implementierungen | 3 | 1 |
| Leerzustands-Muster | 4 | 1 |
| Scroll-Flächen je Seite | 2–5 | 3 |
| Listen mit Virtualisierung | 2 / 10 | 10 / 10 |
| Nachlade-Strategien | 3 | 1 |
| Layout-Haltepunkte | 0 | 2 |
| Inline-`style={{}}` in Komponenten | 207 | → 0 |
| Hartkodierte Hex-Farben | 128 in 33 Dateien | 0 |
| Undefinierte, aber verwendete Tokens | 1 (`--font-size-md`, 10×) | 0 |
| `role="dialog"` | 0 bei 9× `aria-modal` | 9 |
| `role="alert"` | 0 bei 46× `console.error` | ≥ 46 |
| Fehlende i18n-Schlüssel in `de.json` | 3 | 0 |
| Dateien ohne `useTranslation` im Workflow-Editor | 23 / 23 | 0 |
| `waitForTimeout` in E2E | 35 | 0 |

### Messverfahren

Die Werte stammen aus zwei Quellen und sind reproduzierbar:

- **Statisch:** `grep`/`ripgrep` über `frontend/src` und `e2e`, jeweils ohne Testdateien
  und ohne `external/`
- **Dynamisch:** Playwright gegen `localhost:5173`, angemeldet, über zehn Routen —
  `getComputedStyle` für Tokens und Überschriften, `document.querySelectorAll` für
  Scroll-Container und ARIA-Rollen

Die Sonden-Spezifikationen waren temporär und wurden nach der Messung entfernt. Für eine
Wiederholung genügt ein Spec, der die Tabelle oben nachfährt — sinnvollerweise als
dauerhafter Test aus 16.1.

---

## Änderungshistorie

| Datum | Änderung |
|---|---|
| 2026-07-28 | Erstfassung aus dem Konsistenz-Audit (#157–#186) |
| 2026-07-31 | Fachliche Korrektur nach Review: Trace-Spine von fünf festen V-Modell-Stationen auf dynamische Ebenenzahl umgestellt (Kapitel 5, gegen `ArchitectureElement.get_level()` geprüft — Baumtiefe, kein Enum); Verifikation von eigener Endstufe zu Badge pro Station (Tests verlinken laut Datenmodell auf jede Ebene, nicht nur auf eine Verifikationsstufe); neues Kapitel 8.6 Theming-System (benannte Paletten über Primitiv-/Semantik-Token-Trennung, best practice nach Material Design 3 / Adobe Spectrum / IBM Carbon); Kapitel 12.11 Dynamische Artefakt-Attribute ergänzt (`CustomFieldDefinition` existiert im Datenmodell, wird nicht angezeigt — Audit #29); funktionale Untergrenze in Kapitel 4 ergänzt; Schritt 0 (Pilot an Goals, Architecture, Needs) vor die Umsetzungsreihenfolge gesetzt. |
