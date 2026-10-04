# WP-3b Evidence 06 — `data-testid`-Abdeckungsmatrix & e2e-Abgleich

## 1. Zählweise

* **Interaktiv** = natives interaktives DOM-Element (`button`, `a`, `input`,
  `select`, `textarea`, `summary`, `form`) **oder** Element mit
  `role="button|tab|menuitem|switch|option"` **oder** kleingeschriebenes Tag
  mit `onClick|onDoubleClick|onMouseDown|onPointerDown|onTouch*|onSubmit|onKey*|onInput|onChange`.
* **Kapitalisierte Komponenten-Tags sind ausgeschlossen** — `<Widget onChange={…}>`
  ist kein natives DOM-Element und würde die Quote verfälschen
  (mit Komponenten: 935 statt 804 interaktiv, 83,7 % statt 93,5 % Abdeckung).
* Scope: Produktionsdateien ohne Kommentare, 370 Dateien.

## 2. Abdeckung

| Metrik | Wert |
|---|---:|
| Interaktive DOM-Elemente (Prod) | **804** |
| davon mit `data-testid` | **752** |
| **Abdeckung** | **93,5 %** |
| ohne `data-testid` | **52** |
| `input`/`select` mit `type="hidden"` (von der Pflicht ausgenommen) | mitgezählt |

Nicht-interaktive Elemente mit `data-testid` (Container, Statuszeilen,
Assertions-Anker wie `route-suspense-fallback`) sind **nicht** Teil der Quote —
sie dienen E2E-Assertions und sind korrekt.

## 3. Naming-Konvention

| Metrik | Wert |
|---|---:|
| Distinct Test-IDs (aus Interaktiv-Scan) | 528 |
| davon `^[a-z0-9]+(-[a-z0-9]+)*$` (kebab-case) | **528 / 528 = 100 %** |

→ Die Benennungs-Konvention ist **sauber durchgesetzt**. Kein Befund.

## 4. Datei-lokale Dubletten (Playwright-Strict-Mode-Risiko)

| Datei | Test-ID | Anzahl |
|---|---|---:|
| `components/shared/CustomFieldsEditor.tsx` | `custom-field-value` | 2 |
| `components/RequirementEditors/ReqTraceLinkPanel.tsx` | `req-tracelink-delete-btn` | 2 |
| `components/WorkflowEditor/TransitionDialog.tsx` | `workflow-transition-to` | 2 |
| `components/GlossaryView/GlossaryView.tsx` | `glossary-form` | 2 |

In `ReqTraceLinkPanel.tsx` ist die Dublette erwartbar (eine Zeile pro
Trace-Link in einer Liste) und per `nth()`/`filter()` adressierbar. Sie ist
kein Defekt, aber ein Trefferrisiko für `getByTestId(...)` ohne Filter.

## 5. Bereiche mit der schlechtesten Abdeckung (Auswahl)

| Datei | fehlende TIDs | Bemerkung |
|---|---:|---|
| `components/shared/ArtifactForm/ArtifactForm.tsx:1168-1244` | 11 | generische Feld-Widgets (`TextField`, `NumberField`, `BooleanToggle`, `EnumSelect`, `MultiEnum`, `DateField`, `ReferencePicker`, `UserPicker`, `ActorPicker`, `TextArea`, `MarkdownTabGroup`) — alle nehmen `testId` als Prop, richten ihn aber nicht auf dem Wurzel-Element auf |
| `components/WorkspaceSettings/PromptVariablesSection.tsx:577` | 1 | `testId="prompt-variable-new-value"` am Wrapper, nicht am Control |
| `components/AdrEditors/AdrEditors.tsx:271` | 1 | `<form id="adr-create-form" onSubmit=…>` ohne TID |
| `components/ArchitectureEditors/ArchitectureEditors.tsx:432` | 1 | Reload-`<button>` ohne TID |
| `components/shared/ArtifactInspector/RightSidebar.tsx:353,362,372` | 3 | Icon-only-Buttons (`collapsedIconButton`) mit `aria-label`, ohne TID |

## 6. e2e-Selektor-Abgleich

| Menge | Zahl |
|---|---:|
| Literal-Test-IDs in `frontend/src` (ohne `*.test.*`) | 1 146 |
| E2E-Literal-Selektoren (`getByTestId(...)` + `[data-testid="…"]`, extrahiert) | 353 |
| davon ohne Zeichenkette in `frontend/src` | 41 |
| davon nach Abzug dynamisch konstruierter Muster | **≥ 6 verifiziert stale** |

### 6.1 Dynamisch konstruiert (kein Befund)

| Selektor | Erzeugung |
|---|---|
| `system-settings-tab-*` | `SystemSettings.tsx:125` → `` data-testid={`system-settings-tab-${tab.id}`} `` |
| `language-option-*` | `WorkspaceSettings.tsx:486` → `` data-testid={`language-option-${lang}`} `` |
| `entity-type-*` | verschiedene, `` `entity-type-${t}` `` |
| `baseline-scope-*` | `baseline-scope-${data.scope}` |
| `create-trace-link-type-option-*` | Template in `create-trace-link-dialog.tsx` |
| `review-list-item-<uuid>` | pro Review-ID |

### 6.2 Verifiziert stale — widerlegt die WP-3-Aussage „0 veraltete Selektoren"

| Selektor | Vorkommen in `e2e/` | Treffer in `frontend/src` |
|---|---|---|
| `login-form` | div. | **0, repo-weit** |
| `main-header` | div. | **0, repo-weit** |
| `visibility-row-diagrams` | visibility-Specs | **0** (UI in Task 27 entfernt) |
| `visibility-checkbox-diagrams` | visibility-Specs | **0** |
| `visibility-reset-diagrams` | visibility-Specs | **0** |
| `todo-item` | div. | **0** |

Zusatzbefund: `create-trace-link-source-element-undefined` ist als Selector
literal im E2E-Code — das ist ein zur Laufzeit generierter String, der in einen
E2E-Selektor geraten ist (Test-Smell, kein UI-Bug).

### 6.3 Fehlender Guard

Es existiert **kein** Test, der die Selektoren aus `e2e/` gegen `frontend/src/`
prüft. Ein solcher Test wäre trivial:

```
for each literal selector S in e2e/**:
    expect(S).toMatch(/\$\{/ || prodSource.includes(`data-testid="` + S))
```

Damit wäre die Drift sofort rot.

## 7. Gegenprobe zur Repo-Konvention

`AGENTS.md` fordert „`data-testid` auf allen interaktiven UI-Elementen
(E2E-Pflicht für Playwright)". Gemessen: **93,5 %** der nativen interaktiven
DOM-Elemente erfüllen das. Die verbleibenden 52 sind in der
Design-System-Ratchet-Baseline nicht als TID-Lücke erfasst — diese prüft nur
`btn-*`-Klassen, nicht TIDs.