# Umsetzungsplan: Offene Bug-/Audit-Issues nach Release 1.7.0

**Stand:** 2026-08-23 · **Basis:** `main` nach Merge des 7-Gruppen-Bugfix-Batches (PR #723, #721, #717, #725, #728, #726, #727) und 4 Dependency-Updates (#640, #639, #637, #635).

**Kernaussage:** Kein offenes Issue blockiert den 1.7.0-Release. Alle 28 offenen `bug`-Issues sind Medium/Low-Severity Polish-, i18n- oder Debt-Themen, bis auf zwei bereits untersuchte HIGH-Punkte (#708, #682), die keinen Code-Fix erfordern, sondern Re-Verifikation bzw. Test-Infra-Arbeit sind.

Gruppierung nach Code-Areal (gleiches Prinzip wie der letzte Bugfix-Batch), damit zusammenhängende Symptome in einem Rutsch behoben werden statt dieselben Dateien mehrfach anzufassen.

---

## Prioritäts-Tiers

| Tier | Bedeutung |
|------|-----------|
| **P0** | Vor nächstem Feature-Release sinnvoll, aber kein 1.7.0-Blocker |
| **P1** | Sollte in den nächsten 1-2 Bugfix-Sessions rein |
| **P2** | Polish/Debt, aufschiebbar |
| **P3** | Groß, braucht eigenes Brainstorming (architektonisch) vor Umsetzung |

---

## Gruppe H — Security-Verifikation (kein Code-Fix)

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #708 | Tenant-Last-Admin-Guard umgehbar (HIGH) | XS |

**Befund:** In Gruppe A bereits untersucht — Guard ist im aktuellen Code vorhanden und getestet (500+ Tests grün, `git log`/`git diff` zeigen keine Lücke). Wahrscheinlich Stale-QA-Image. **Aktion:** Kein Fix nötig. QA soll nach 1.7.0-Deploy gegen das echte Release-Build reverifizieren, dann Issue schließen. **Priorität: P0** (nur Verifikationsaufwand, keine Entwicklung).

---

## Gruppe I — E2E/CI-Infrastruktur

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #682 | Playwright E2E hängt/Timeout auf main (Shards 1, 2, 4) — HIGH | M |
| #711 | E2E/CI-Artefakte akkumulieren ungehindert (60+ Workspaces, 43 revoked API-Keys blockieren 10-Key-Limit) | S |
| #504 | E2E Shard 2 Baseline-Failures, teilweise durch #488 verursacht | S (Reverify) |

**Befund:** Reine Test-Infrastruktur, kein Produktbug — beeinflusst nur CI-Vertrauen. `systematic-debugging`-Skill nötig für #682 (Root-Cause vor Fix). #711 ist ein Cleanup-Script/Cronjob-Task (existierendes `cleanup_revoked_api_keys`-Command evtl. erweiterbar). #504 sollte zuerst gegen aktuellen `main` reverifiziert werden — evtl. bereits durch PR #701 (E2E-Reparatur vom 2026-08-23) erledigt. **Priorität: P1.**

---

## Gruppe J — API/Data-Edge-Cases

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #724 | Malformed `document_id` bei `baseline.create scope=document` leakt 500 via REST | XS |
| #710 | Inkonsistente UUID-Fehlerbehandlung: `requirements` → 400, `needs`/`goals` → 404 | XS (nach Produktentscheidung) |

**Befund:** #724 ist der bereits dokumentierte Follow-up aus Gruppe D — analoger Fix zu #715 (früh validieren statt in Service-Layer crashen lassen). #710 braucht zuerst eine Produktentscheidung: soll der #271-Contract (400 bei malformed pk) auf `needs`/`goals` ausgeweitet werden (Regex-Route ändern), oder ist 404 dort bewusst? Ohne diese Entscheidung riskiert ein Fix, den bestehenden `#271`-Contract zu brechen (siehe Analyse-Kommentar auf #710). **Priorität: P1** (beide klein, isoliert, gleicher Code-Bereich wie Gruppe B/D).

---

## Gruppe K — Theming/Design-Token-System (groß, P3)

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #707 | Theme-Palette und Dark/Light-Modus nicht kombinierbar (flache Liste statt zwei Achsen) | L |
| #161 | Token-System hat kaum Reichweite — 207 Inline-Styles im Code | L |
| #140 | 128 hartcodierte Hex-Farbwerte in 33 Komponenten trotz `tokens.css` | M |

**Befund:** Alle drei hängen ursächlich zusammen — das Theming-System wurde nie als echte zwei-Achsen-Struktur (Palette × Hell/Dunkel) gebaut, und dieselbe Schwäche zeigt sich in fehlender `tokens.css`-Durchsetzung. Einzeln patchen würde denselben Code mehrfach anfassen. **Empfehlung:** Ein architektonisches Brainstorming (`superpowers:brainstorming`, Pfad "architectural") für ein konsolidiertes Theming/Token-Redesign, das alle drei Issues in einem Spec/Plan abdeckt. **Priorität: P3** — bewusst zurückgestellt, wie bereits mit dir vereinbart.

---

## Gruppe L — i18n-Konsistenz (DE/EN-Sprachmix)

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #659 | Admin "Permission Defaults": englische Labels bei deutscher Sprache | XS |
| #658 | ADR-Titel-Platzhalter auf Englisch | XS |
| #657 | Import-Seite: ReqIF-Bereich komplett auf Englisch + CamelCase | S |
| #654 | Sidebar-Navigation: DE/EN-Sprachmix + inkonsistente Kapitalisierung | S |
| #653 | Sidebar i18n-Sprachmix (Fortsetzung #610) | S |
| #651 | Sidebar i18n-Sprachmix (Fortsetzung #610, Duplikat-Verdacht zu #653) | — (erst dedupen) |

**Befund:** Gleiche Ursache an verschiedenen Stellen — fehlende oder hartcodierte `t()`-Aufrufe statt i18n-Keys. #651 und #653 haben identischen Titel ("Fortsetzung #610") — vor Umsetzung prüfen, ob das ein echtes Duplikat ist (dann eines schließen). **Empfehlung:** Ein Batch-Fix analog Gruppe L des letzten Bugfix-Batches, da alle denselben `i18n-parity`-Test-Mechanismus und dieselben Locale-Dateien berühren. **Priorität: P1**, guter nächster Batch-Kandidat — klein, isoliert, hoher Symptom-Impact (sichtbar für jeden DE-Nutzer).

---

## Gruppe M — UI-Layout-/Design-Konsistenz

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #720 | Sidebar `overflowY:hidden` — bei kleiner Viewport-Höhe nicht scrollbar (6/24 Links unerreichbar) | S |
| #719 | Create-Dialoge inkonsistent: Speichern-vs-Erstellen, fehlendes Primary-Styling | S |
| #718 | Header-Höhe inkonsistent auf 6 Seiten (57–178px statt 60px) + H1 fehlt auf 4 Seiten | M |
| #664 | Chat-Support-Floating-Button zu dominant | XS |
| #663 | Workspace-Preset: uneinheitliche Notation | XS |
| #660 | `/workflows` und `/diagrams`: kein Header-Container | S |
| #661 | `/architecture` Tree-View: fehlende Tree-Lines | S |
| #656 | Design-Mix: Card-basiert (`/import`) vs. Listen/Tabellen | S |
| #655 | Header-Höhe inkonsistent: `/requirements` (134px) vs. Rest (60px) | S |
| #596 | Workflow-Editor horizontaler Overflow + `/audit` 480 KB DOM | M |
| #594 | CTA-Buttons uneinheitlich: 10+ Label-Varianten | S |

**Befund:** 11 Issues, alle Symptome derselben fehlenden Konsolidierung: kein einheitliches Header-/Card-/Button-Komponentensystem. Einzeln gefixt würde derselbe `PageHeader`/`EmptyState`/Button-Code wiederholt angefasst (wie in Gruppe G dieser Session bereits an `PageHeaderAction`/`EmptyStateAction` sichtbar). **Empfehlung:** Nicht als 11 Einzel-Tickets abarbeiten, sondern als ein Design-System-Konsolidierungsprojekt — vermutlich ebenfalls P3/architektonisch, da es faktisch eine Layout-Primitive-Vereinheitlichung ist (neuer `PageHeader`-Standard mit fester Höhe, ein Dialog-Primitive für alle Create-Flows). Kleinere isolierte Teile (#664 Chat-Button, #663 Notation, #720 Sidebar-Scroll) könnten vorab als Quick-Wins raus. **Priorität: P2 (Quick-Wins), P3 (Rest, gebündelt).**

---

## Gruppe N — Accessibility

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #667 | Navigationsbaum: ARIA Treeview-Regelverletzung durch interaktive Buttons in `role="treeitem"` | S |

**Befund:** Isoliert, betrifft nur den WorkspaceTree. Guter Kandidat für einen kleinen eigenständigen Fix, ggf. zusammen mit #720 (selbe Sidebar-Komponente). **Priorität: P1.**

---

## Gruppe O — Validation

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #662 | Workspace-Einstellungen: "Speichern" aktiv bei leerem Workspace-Namen | XS |

**Befund:** Klassischer isolierter Validierungs-Bug, ein Formularfeld. **Priorität: P1**, kleinster Quick-Win im ganzen Backlog.

---

## Gruppe P — LLM/AI-Robustheit

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #652 | `ai_derivation` (mimo-v2.5): gelegentlich "LLM response was not valid JSON" / 0 Drafts bei Cold-Start | S |
| #650 | Identischer Titel zu #652 | — (erst dedupen) |

**Befund:** #650 und #652 sehen wie Duplikate aus (identischer Titel, gleiche Komponente) — vor Fix prüfen und ggf. #650 als Duplikat von #652 schließen. Danach: Retry/Robustheits-Fix im `llm_adapter` (Cold-Start-Race, evtl. verwandt mit der in Gruppe C dieser Session gefixten Circuit-Breaker-Logik). **Priorität: P1.**

---

## Gruppe Q — Traceability/SE-Audit (groß, P3)

| Issue | Titel | Aufwand |
|-------|-------|---------|
| #414 | Zwei unüberbrückte ID-Räume (Entity-ID vs. Artifact-ID) — App wirft 404 auf eigene Artefakte | L |

**Befund:** Architektonischer SE-Methodik-Befund aus dem 2026-08-07-Audit, kein isolierter Bug. Braucht eigenes Brainstorming, da es die Artifact/Entity-ID-Modellierung betrifft (cross-cutting). **Priorität: P3.**

---

## Empfohlene Reihenfolge für zukünftige Sessions

1. **Quick-Win-Batch (P1, ~1 Session):** #662, #667, #724, #652/#650 (nach Dedup) — klein, isoliert, hoher Nutzen pro Aufwand.
2. **i18n-Batch (P1, ~1 Session):** Gruppe L (#659, #658, #657, #654, #653, #651) — nach Dedup von #651/#653.
3. **E2E/CI-Batch (P1, ~1 Session):** #682 (systematic-debugging), #711 (Cleanup-Script), #504 (Reverify — evtl. schon durch PR #701 erledigt).
4. **Produktentscheidung + Fix:** #710 (UUID-Error-Contract) — erst mit dir klären, dann XS-Fix.
5. **Design-System-Konsolidierung (P3, eigenes Brainstorming):** Gruppe M gebündelt (11 Issues) + evtl. #707/#161/#140 (Theming) als verwandtes, aber separates Projekt — beide sind UI-Grundlagenarbeit, aber unterschiedlicher Scope (Layout-Primitives vs. Farb-/Palette-System). Empfehlung: zwei getrennte Specs.
6. **SE-Methodik (P3, eigenes Brainstorming):** #414.

Nichts davon ist für 1.7.0 nötig — alles Post-Release-Backlog.
