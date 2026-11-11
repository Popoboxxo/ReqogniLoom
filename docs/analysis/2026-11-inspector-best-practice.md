# Best-Practice-Recherche Artefakt-Inspector — 2026-11

**Auftrag:** Task 4 aus `docs/superpowers/plans/2026-11-10-phase-b2-inspector-concept.md`.
**Zweck:** Belegte Muster für den Neuzuschnitt des Artefakt-Inspectors (`shared/ArtifactInspector`), damit Task 5 (Spec) per Quellennummer referenzieren kann.
**Abrufdatum aller Quellen:** 2026-11-11.
**Regel:** Nur Quellen, die am 2026-11-11 tatsächlich abrufbar waren und deren Inhalt hier gelesen wurde. Nicht erreichbare Kandidaten sind in Abschnitt 6 dokumentiert und nicht verwendet.

## 0. Abdeckung

| Thema | Quellen | Anzahl |
|---|---|---|
| (a) Detail-/Seitenpanel-Muster und Progressive Disclosure | Q1–Q5 | 5 |
| (b) Nachverfolgbarkeit und Verlauf in Requirements-Werkzeugen | Q6–Q9 | 4 |
| (c) Diff-Darstellung und Versionshistorie | Q10–Q12 | 3 |
| (d) Barrierefreie Seitenpanels und Splitter | Q13–Q15 | 3 |
| (e) Responsives Verhalten von Seitenpanels | Q3, Q4, Q5 (Querschnitt) | 3 |

Muster-Katalog: 6 Muster (Abschnitt 5).

---

## 1. Thema (a): Detail-/Seitenpanel-Muster und Progressive Disclosure

### Q1 — Progressive Disclosure (Jakob Nielsen, NN/g, 2006-12-03)

- **URL:** https://www.nngroup.com/articles/progressive-disclosure/
- **Kernaussage:** Zuerst nur wenige wichtige Optionen zeigen, seltene und spezialisierte Optionen erst auf Anforderung nachladen; das verbessert Lernbarkeit, Effizienz und Fehlerrate. Zwei Dinge müssen stimmen: der Schnitt zwischen primären und sekundären Inhalten und ein offensichtlicher, klar benannter Weg zur zweiten Ebene („starker Information Scent").
- **Übertragbarkeit:** **teilweise.** Der Grundsatz passt direkt auf die Panel-Reihenfolge (Version, Diff, Trace, Kommentare) und auf das Ein-/Ausklappen. Nicht übertragbar ist die Zahl der Ebenen: Nielsen hält mehr als zwei Disclosure-Ebenen für unbrauchbar, der Inspector darf also keine dritte Ebene (Panel → Unterpanel → Dialog) aufbauen.

### Q2 — User-Interface Elements: Glossary, Eintrag „Side Sheet (Drawer, Flyout)" (Raluca Budiu, Kara Rivenbark, NN/g, 2025-02-28)

- **URL:** https://www.nngroup.com/articles/ui-elements-glossary/
- **Kernaussage:** Ein Side Sheet ist ein Overlay, das vom linken oder rechten Rand einfährt und typischerweise einen erheblichen Teil des Bildschirms bedeckt; es kann modal (Hintergrund blockiert) oder non-modal sein. Ein Side Sheet darf Navigation, Befehle oder Inhalt enthalten; „Drawer" und „Flyout" sind Synonyme.
- **Übertragbarkeit:** **ja.** Liefert die Begriffe für die Spec und die entscheidende Unterscheidung modal/non-modal. Der heutige Inspector ist non-modal (`aside role="complementary"`); ein Wechsel zu modal wäre eine bewusste Entscheidung, nicht ein Nebeneffekt.

### Q3 — Drawer, Design Guidelines (PatternFly 6.7.0, Red Hat)

- **URL:** https://www.patternfly.org/components/drawer/design-guidelines
- **Kernaussage:** Ein Drawer ist ein einfahrendes Panel, das entweder Inhalt überlagert („overlay") oder ihn verschiebt („inline"); er ist das übliche Detail-Element in einem Primary-Detail-Layout, weil das Detail oft ein- und ausgeklappt wird, während der Primärinhalt immer sichtbar bleibt. Ein Splitter gehört an die dem Öffnungsrand gegenüberliegende Seite (bei rechts öffnendem Drawer also links), und nur dann, wenn der Inhalt wirklich mehr Platz braucht.
- **Übertragbarkeit:** **ja.** Genau die offene Frage aus dem Befund („Spine am Rand, Panel rechts"): PatternFly trennt Drawer-Modus (overlay/inline) vom Splitter und gibt eine Regel für die Splitterposition. Die Token-Hinweise (`--pf-t--global--*`) sind nicht übertragbar, ReqogniLoom nutzt `styles/tokens.css`.

### Q4 — Primary-detail, Design Guidelines (PatternFly 6.7.0, Red Hat)

- **URL:** https://www.patternfly.org/patterns/primary-detail/design-guidelines
- **Kernaussage:** Primary-detail zeigt eine Liste und die Details des gewählten Elements; Panes sind typischerweise Hälften, Drittel oder Viertel der Viewport-Breite, die Detailhöhe beträgt 100 % des Primärcontainers, und es braucht einen sichtbaren Auswahlzustand plus Leerzustand, wenn nichts gewählt ist. Bei Mehrfachauswahl im Primärbereich zeigt das Detailpanel einen eigenen Leerzustand, der zum Aufheben der Auswahl auffordert.
- **Übertragbarkeit:** **ja.** Beschreibt sowohl den Requirements-SplitView (Liste links, Inspector rechts) als auch die Leerzustände, die im Ist je Typ abweichen. Wichtig für Task 5: der Auswahlzustand ist Teil des Vertrags, nicht Dekoration.

### Q5 — Drawer (GitLab Pajamas Design System)

- **URL:** https://design.gitlab.com/components/drawer/
- **Kernaussage:** Ein Drawer ist eine *transiente* Seitenfläche für sekundäre oder temporäre Unterstützung; die Hauptaufgabe bleibt auf der Seite darunter, und er ist schließbar, ohne den Workflow zu brechen. Wenn die Seitenregion Teil des Kernarbeitsbereichs ist oder dauerhaft neben dem Inhalt koexistiert, soll laut Pajamas stattdessen ein Panel verwendet werden — der Drawer ist dann die falsche Bauform.
- **Übertragbarkeit:** **ja, mit Einschränkung.** Das ist der stärkste Gegencheck gegen den heutigen Inspector: Version, Trace-Links und Kommentare sind bei Requirements keine „temporäre" Information, sondern Dauerinhalt. Die Doku liefert damit die Begründung, warum „Drawer" und „Inspector-Panel" zwei verschiedene Muster sind und nicht dasselbe.

---

## 2. Thema (b): Nachverfolgbarkeit und Verlauf in Requirements-Werkzeugen

### Q6 — Trace View (Jama Connect Help)

- **URL:** https://help.jamasoftware.com/ah/en/manage-content/coverage-and-traceability/trace-view.html
- **Kernaussage:** Die Trace View zeigt vor- und nachgelagerte Items, die Item-Details im Kontext ihrer Beziehung und fehlende Abdeckung (rotes Ausrufezeichen bei verletzter Relationship-Regel); Felder lassen sich je Ebene ein- und ausblenden. Ein Klick auf ein Item öffnet ein **Slide-out-Panel mit den Feldern des Items**, in dem ohne Verlassen der Trace View bearbeitet werden kann.
- **Übertragbarkeit:** **ja.** Das ist das nächstliegende Vorbild für „Trace-Ansicht + Detail-Panel": Detailanzeige als Overlay über der Trace-Ansicht, nicht als Seitenwechsel. Ebenfalls übertragbar: Lückenanzeige direkt am Knoten statt in einer separaten Liste.

### Q7 — Relationships (Jama Connect Help)

- **URL:** https://help.jamasoftware.com/ah/en/manage-content/coverage-and-traceability/relationships.html
- **Kernaussage:** Beziehungen haben eine Richtung (upstream/downstream) und dienen der Impact-Analyse; ändert sich ein Upstream-Item, gilt die Beziehung zu den Downstream-Items als „suspect". Upstream/downstream trägt den vertikalen und horizontalen Trace des V-Modells (Anforderungen bzw. Verifikation).
- **Übertragbarkeit:** **ja.** Deckt sich mit dem ReqogniLoom-Modell (20 Link-Typen, Suspect-Propagation, V-Modell L0–L4). Für den Inspector heißt das: Richtung und Suspect-Zustand müssen am Link sichtbar sein, sonst ist die Trace-Anzeige nur eine Liste.

### Q8 — Link work items (Jira Cloud, Atlassian Support)

- **URL:** https://support.atlassian.com/jira-software-cloud/docs/link-issues/
- **Kernaussage:** Verknüpfte Work Items erscheinen standardmäßig in der Detailansicht des Work Items; ein Icon öffnet die Liste mit Link-Typ, Key, Zusammenfassung und Status je Eintrag, und das Entfernen einer Verknüpfung läuft über einen Bestätigungsdialog. Die Liste der Link-Typen (blocks, implements, causes, relates to …) ist konfigurierbar.
- **Übertragbarkeit:** **teilweise.** Übernehmbar ist die kompakte Zeile pro Link (Typ + ID + Titel + Status) und das Öffnen der Linkliste aus der Detailansicht heraus. Nicht übernehmbar ist die Beschränkung auf ein flaches Icon-Popover: ReqogniLoom braucht Gruppierung nach Link-Typ und Richtung, sonst gehen 20 Typen in einer Liste unter.

### Q9 — Traceability (IBM Engineering Requirements Management DOORS Next 7.1.0)

- **URL:** https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors-next/7.1.0?topic=requirements-traceability
- **Kernaussage:** Traceability verknüpft Anforderungen mit Anforderungen, Entwicklungs- und Testartefakten und trägt Ableitung/Abdeckungsanalyse, Impact-Analyse, Lifecycle-Coverage, Fortschritt und Reporting. Zum Ansehen, Anlegen, Löschen und Erkunden verknüpfter Artefakte dient der **Links Explorer**; Suspect-Indikatoren markieren potenziell betroffene Artefakte, und „Link validity" bewertet, ob zwei verknüpfte Artefakte inhaltlich noch zusammenpassen.
- **Übertragbarkeit:** **teilweise.** Der Links Explorer als eigene, explorierbare Ansicht ist ein Argument dafür, die Trace-Sicht nicht nur als Panel-Tab zu führen. „Link validity" ist ein Konzept, das ReqogniLoom heute nicht hat — als Nicht-Ziel in Task 5 festhalten, nicht als Anforderung erfinden.

---

## 3. Thema (c): Diff-Darstellung und Versionshistorie

### Q10 — Comparing commits (GitHub Docs)

- **URL:** https://docs.github.com/en/pull-requests/committing-changes-to-your-project/viewing-and-comparing-commits/comparing-commits
- **Kernaussage:** Vergleiche brauchen immer zwei explizit gewählte Endpunkte (`base` und `compare`) — Branches, Tags, Commits oder Forks — und die URL ist teilbar. Datei-Historie und Repository-Historie können unterschiedliche Ergebnisse zeigen, weil Git die Historie vereinfacht; für einen vollständigen Blick muss man die Commit-Seite des Repositories nutzen.
- **Übertragbarkeit:** **ja.** Überträgt sich auf „Was hat sich seit Baseline X geändert?": Baseline und aktueller Stand sind zwei Endpunkte, und der Zustand muss in der URL bzw. im Panel-Zustand reproduzierbar sein. Der Hinweis auf abweichende Historien ist eine Warnung gegen ein zu simples „History"-Tab.

### Q11 — Branches, Abschnitt „Comparing branches in pull requests" (GitHub Docs)

- **URL:** https://docs.github.com/en/pull-requests/reference/branches
- **Kernaussage:** GitHub bietet für denselben Vergleich vier Diff-Ansichten (unified, split, rich, source), das Ignorieren von Whitespace-Änderungen und das Filtern auf relevante Dateien. Ein Drei-Punkt-Diff (`A...B`) zeigt, was der Branch seit dem Merge-Base einführt, ein Zwei-Punkt-Diff (`A..B`) verschiebt sich mit dem Basisbranch und macht die eigentliche Änderung schwerer lesbar.
- **Übertragbarkeit:** **ja.** Direkt übertragbar ist die Trennung „was habe ich geändert" (semantischer Diff gegen gemeinsame Basis) versus „was ist der Unterschied zum aktuellen Stand". Für Feld-Diffs in ReqogniLoom ist die Drei-Punkt-Semantik die richtige Voreinstellung; Whitespace-/Formatierungsrauschen braucht einen eigenen Schalter.

### Q12 — Page History and Page Comparison Views (Confluence Data Center 11.0)

- **URL:** https://confluence.atlassian.com/doc/page-history-and-page-comparison-views-139379.html
- **Kernaussage:** Confluence legt bei jeder Änderung eine Version an; die History listet Versionen, zwei beliebige Versionen lassen sich vergleichen, und der Vergleich färbt hinzugefügten Inhalt grün, gelöschten rot und Formatierungsänderungen blau. Große unveränderte Blöcke werden zu einer Auslassung zusammengezogen, und man kann per `<<`/`>>` zur benachbarten Version weitervergleichen, ohne in die Liste zurückzuspringen.
- **Übertragbarkeit:** **ja.** Das ist die kompakteste belegte Beschreibung einer lesbaren Diff-Ansicht: Farblegende, Kollabieren von Unverändertem und direktes Weiterblättern zwischen Versionen. Die Farbwerte selbst dürfen nicht übernommen werden (Token-Pflicht, Kontrast), nur die Semantik.

---

## 4. Thema (d): Barrierefreie Seitenpanels und Splitter

### Q13 — Window Splitter Pattern (WAI-ARIA Authoring Practices Guide, W3C)

- **URL:** https://www.w3.org/WAI/ARIA/apg/patterns/windowsplitter/
- **Kernaussage:** Ein Window Splitter ist ein verschiebbarer Trenner zwischen zwei Panes; das fokussierbare Element hat `role="separator"` mit `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, einem zugänglichen Namen (idealerweise `aria-labelledby` auf die primäre Pane) und `aria-controls` auf die primäre Pane. Tastatur: Pfeiltasten verschieben, `Enter` klappt die primäre Pane ein bzw. stellt sie wieder her, optional `Home`/`End` für Extremwerte und `F6` zum Pane-Wechsel; ein *fixed* Splitter lässt die Pfeiltasten weg.
- **Übertragbarkeit:** **ja.** Der Inspector ist mit 280–520 px bereits skalierbar — laut APG fehlt ihm damit die Rolle und der Tastaturvertrag. Wichtig für Task 5: „fixed" (nur zwei Positionen) ist die einfachere, normkonforme Variante und deckt Ein-/Ausklappen ab.

### Q14 — Disclosure (Show/Hide) Pattern (WAI-ARIA Authoring Practices Guide, W3C)

- **URL:** https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
- **Kernaussage:** Disclosure besteht aus genau zwei Teilen: einem Button und dem von ihm gesteuerten Inhaltsbereich; der Button trägt `aria-expanded` (true/false) und optional `aria-controls`. Ausgelöst wird per `Enter` oder `Space`, und das übliche Pfeilsymbol zeigt die Richtung des Zustands an.
- **Übertragbarkeit:** **ja.** Gilt für jede Panel-Sektion (Version, Diff, Trace, Kommentare) und für den globalen Ein-/Ausklapp-Schalter. Heute ist das Verhalten je Typ unterschiedlich — die APG macht daraus eine einheitliche, prüfbare Vorgabe.

### Q15 — Complementary Landmark (ARIA Landmarks Example, W3C WAI)

- **URL:** https://www.w3.org/WAI/ARIA/apg/patterns/landmarks/examples/complementary.html
- **Kernaussage:** Ein Complementary-Landmark ist ein unterstützender Abschnitt, der auch getrennt vom Hauptinhalt verständlich bleibt; es soll ein Top-Level-Landmark sein (nicht in einem anderen Landmark verschachtelt), und bei mehreren Complementary-Landmarks braucht jedes ein eigenes Label. Umgesetzt wird es mit `<aside>` oder `role="complementary"`, benannt über `aria-labelledby` oder `aria-label`.
- **Übertragbarkeit:** **ja.** Der Inspector ist bereits `aside role="complementary"`; offen ist die Frage nach Label, nach Top-Level-Position (nicht innerhalb von `main`) und danach, ob es je Seite nur einen geben darf. Genau diese drei Punkte muss Task 5 festlegen.

---

## 5. Muster-Katalog

Nur Muster, die durch die oben genannten Quellen gedeckt sind. Quellennummern in Klammern.

### M1 — Primary-Detail mit dauerhaftem Detailbereich

- **Problem:** Liste und Detail konkurrieren um Platz; ohne Auswahlzustand und Leerzustand weiß niemand, welches Element gerade rechts steht, und bei Mehrfachauswahl ist unklar, was das Panel zeigt.
- **Lösung:** Primärbereich (Liste/SplitView) links, Detailbereich rechts mit sichtbarem Auswahlzustand; Panes als Halbe/Drittel/Viertel der Breite, Detailhöhe 100 % des Primärcontainers; eigener Leerzustand „nichts gewählt" und eigener Leerzustand „mehrere gewählt".
- **Quellen:** Q4, Q3, Q2

### M2 — Progressive Disclosure mit höchstens zwei Ebenen

- **Problem:** Ein Inspector mit vier Panels und vielen Feldern überfordert beim Einstieg; trotzdem brauchen erfahrene Nutzer die Details.
- **Lösung:** Häufig gebrauchte Information steht initial offen, seltene hinter einem klar benannten und beschrifteten Auslöser mit starkem Information Scent; keine dritte Ebene (Panel → Unterpanel → Dialog). Der Schnitt wird aus Aufgabenhäufigkeit abgeleitet, nicht aus Datenmodell-Vollständigkeit.
- **Quellen:** Q1, Q5, Q14

### M3 — Panel-Modus nach verfügbarer Breite: inline → overlay → Vollbild

- **Problem:** Ein breites Panel verdrängt bei 768/1024 px den Inhalt; ein Overlay verdeckt ihn.
- **Lösung:** Bei viel Platz „inline/push" (Panel schiebt den Inhalt, beide bleiben sichtbar), bei mittlerer Breite „overlay" (Panel liegt über dem Inhalt), unterhalb des Breakpoints ein einziges Element pro Bildschirm: Detail fährt ein, nimmt die volle Viewport-Breite, hat klare Rück-Navigation und ist schließbar. Ein im Desktop nicht schließbares Detail wird im Mobile-Modus schließbar.
- **Quellen:** Q3, Q4, Q5

### M4 — Skalierbarer Splitter mit Tastaturvertrag (oder bewusst „fixed")

- **Problem:** Eine feste Panelbreite passt nie für alle Inhalte; ein frei ziehbarer Splitter ist ohne Tastatur- und Screenreader-Vertrag nicht bedienbar.
- **Lösung:** Fokussierbarer Trenner mit `role="separator"`, `aria-valuenow/min/max`, `aria-controls` auf die primäre Pane und einem Namen, der die Pane benennt; Pfeiltasten verschieben, `Enter` klappt ein/aus, optional `Home`/`End`; wenn nur zwei Zustände gebraucht werden, als *fixed* Splitter ohne Pfeiltasten umsetzen. Splitter nur einsetzen, wenn der Inhalt den Platz wirklich braucht.
- **Quellen:** Q13, Q3, Q4

### M5 — Panel als Landmark plus Disclosure-Button

- **Problem:** Ein neuer Aufbau ohne definierte Semantik ist für Screenreader unsichtbar und per Tastatur nicht auffindbar; zwei Panels auf einer Seite sind ohne Label nicht unterscheidbar.
- **Lösung:** Panel als Top-Level-`<aside>`/`role="complementary"` mit eigenem Label; jeder Ein-/Ausklapp-Schalter ist ein Button mit `aria-expanded` und optional `aria-controls`; Fokus wandert beim Öffnen in das Panel, `Esc` schließt (sofern der Zustand transient ist), und der Zustandswechsel wird angekündigt.
- **Quellen:** Q15, Q14, Q5

### M6 — Diff mit expliziter Basis, reduziertem Rauschen und Änderungsarten

- **Problem:** „Was hat sich geändert?" ist ohne Bezugspunkt nicht beantwortbar, und ein vollständiger Textvergleich ist unlesbar.
- **Lösung:** Zwei Endpunkte explizit wählen (Baseline ↔ aktueller Stand bzw. Merge-Base-Semantik), Basis im Zustand/URL reproduzierbar halten; unveränderte Blöcke zu einer Auslassung zusammenziehen; hinzugefügt/entfernt/umformatiert unterscheidbar machen **mit Legende**; Whitespace-/Formatierungsrauschen abschaltbar; direkter Wechsel zur benachbarten Version ohne Rückkehr in die Liste.
- **Quellen:** Q10, Q11, Q12

---

## 6. Nicht verwendete Kandidaten (Transparenz)

Diese Quellen waren am 2026-11-11 nicht verwertbar und sind deshalb **nicht** in den Katalog eingegangen — sie werden auch nicht aus dem Gedächtnis zitiert:

| Kandidat | Ergebnis | Konsequenz |
|---|---|---|
| `carbondesignsystem.com` — Side panel (Komponente/Pattern) | 404 auf beiden geprüften Pfaden | Carbon fehlt als Quelle; IBM-Seite ist nur indirekt über Q9 vertreten |
| `m3.material.io/components/side-sheets/overview` | liefert nur den Seitentitel (clientseitig gerendert, kein Textkörper) | Material Design 3 fehlt als Quelle; keine Aussage zu MD3 in diesem Dokument |
| `polaris.shopify.com/components/sheet` | leitet auf eine generische Referenzübersicht um, kein Sheet-Inhalt | Polaris fehlt als Quelle |
| IBM DOORS Next 7.0.3/7.1-Pfadvarianten | 404; nur der unter Q9 genannte Pfad war erreichbar | nur eine IBM-Quelle |

Damit fehlen in dieser Recherche: Material Design, IBM Carbon und Atlassian Design System als Design-System-Belege. Für (a) und (e) tragen stattdessen PatternFly, GitLab Pajamas und NN/g.

## 7. Grenzen dieser Recherche

- **Keine Messung.** Alle Quellen sind Hersteller- oder Methoden-Dokumentation. Sie belegen Muster, nicht den Nutzen für ReqogniLoom; die Messlatte liefert Task 3 (Usability-Prüfung), nicht dieses Dokument.
- **Typ-Unterschiede sind nicht abgedeckt.** Keine Quelle behandelt Artefakttypen ohne Diff oder ohne Trace-Spine (Glossary, ICD); die Typ-Matrix bleibt Aufgabe von Task 5.
- **Zahlen sind herstellerspezifisch.** Breakpoints, Panelbreiten (z. B. 400 px bei Q5) und Pane-Verhältnisse (Q4) sind Beispiele der jeweiligen Systeme, keine Vorgabe für ReqogniLoom.
- **Konflikt, der in Task 5 entschieden werden muss:** Q5 sagt, ein dauerhafter Detailbereich sei ein *Panel* und kein *Drawer*; Q3/Q4 behandeln denselben Bereich als Drawer im Primary-Detail. Die Spec muss den Begriff festlegen, sonst beschreibt sie zwei verschiedene Dinge mit einem Wort.
