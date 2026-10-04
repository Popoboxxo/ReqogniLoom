# WP-3b Evidence 02 — i18n-Ratchet-Analyse & Korrekturvorschlag

## 1. Was prüft i18n heute?

| Datei:Zeile | Prüfung | Semantik |
|---|---|---|
| `frontend/src/i18n/locales.test.ts` | Locale-Dateien ladbar, Struktur | smoke |
| `frontend/src/test/i18n-parity.test.ts:49-62` | **DE/EN-Schlüsselmenge identisch** (flach, `.`-Sep) | hart, `toEqual([])` |
| `frontend/src/test/i18n-parity.test.ts:186` | **Code→Locale-Abdeckung** | **Ratchet, Obergrenze 116** |
| `frontend/src/test/design-system-ratchet.test.ts` | UI-Konventionen | Ratchet mit JSON-Baseline |

Der dritte Punkt ist die Antwort auf die Frage aus WP-3
(`AUD-2026-09-016`): **eine Code→Locale-Prüfung existiert bereits** (seit #619).
Der Befund ist damit in seiner Begründung zu korrigieren.

## 2. Warum lässt sie die Lücke durch? (fünf konkrete Mechanismen)

1. **Eingefrorene Obergrenze statt Null.**
   `i18n-parity.test.ts:186` `const MISSING_KEY_BASELINE = 116;`
   `expect(missing.length).toBeLessThanOrEqual(MISSING_KEY_BASELINE)`
   → die Suite ist grün, solange die Lücke nicht wächst. Ein Ratchet gegen
   einen Startwert von 116 ist per Konstruktion grün. Im Diff liest sich das
   wie eine bestandene Prüfung.

2. **Scope-Verwässerung.**
   `collectSourceFiles()` (`i18n-parity.test.ts:78-88`) schließt nur
   `/\.test\.tsx?$/` aus. Damit werden `src/test/protected-patch-fields.ts`,
   `src/test/setup.ts`, `src/test/i18n-test-helpers.ts` **mit**gescannt —
   Dateien, die keine Produktionsreferenzen enthalten.

3. **Plural-Blindspot (dokumentiert, aber als Ergebnis falsch verbucht).**
   Der Kommentar ab `i18n-parity.test.ts:150` beschreibt, dass `t('adrs.summary',
   {count})` gegen die reine Literalmenge geprüft wird, obwohl i18next zur
   Laufzeit `_one`/`_other` auflöst. Als „Fix\" wurden **5 leere Bare-Keys**
   (`adrs/risks/issues/testcases/memory .summary`) in beide Locales gelegt, damit
   der Scan zufrieden ist. Ergebnis: die Locale enthält Keys, die zur Laufzeit
   nie benutzt werden, *und* der Scanner kann Pluralformen grundsätzlich nicht
   bewerten.

4. **Kein Rückwärts-Check.** Es gibt keinen Test, der prüft, ob ein Locale-Key
   überhaupt noch referenziert wird (→ 536 tote Keys, siehe Evidence 01).

5. **Keine Coverage für dynamische Keys.** 60 Template-Literal- und
   16 Variablen-Keys sind für einen Quelltext-Scan prinzipiell unauflösbar
   (Evidence 01, Abschnitt 5).

## 3. Korrekte Prüflogik (Entwurf, NICHT implementiert)

### 3.1 Null-Basislinie statt Obergrenze

```
// frontend/src/test/i18n-coverage.test.ts (neu)
const MISSING_KEY_BASELINE = 0;
```

Schritt 1: die 116 Keys nachziehen (41 Dateien, größte Blöcke:
`canvas.*` 15, `permissions.*` 14, `baselines.*` 17, `profile.*` 9,
`settings.llm.*` 7, `export/import.*` 12).
Schritt 2: `MISSING_KEY_BASELINE` auf 0 setzen — **im selben Commit**, sonst
ist der Ratchet ein weiteres Mal ein Blinder.

### 3.2 Zwei Richtungen, zwei Checks

```
// (1) coverage — jeder referenzierte Key existiert
missing = referencedLiteralKeys(prodFiles) − (deKeys ∪ enKeys)
expect(missing).toEqual([])

// (2) liveness — jeder Locale-Key wird benutzt
dead = (deKeys ∪ enKeys) − referencedLiteralKeys(prodFiles)
       − dynamicPrefixKeys(prodFiles)
       − justifiedDeletions            // EXPLIZIT_GELÖSCHT.json
expect(dead).toEqual([])
```

`EXPLIZIT_GELÖSCHT.json` analog zu `design-system-ratchet.baseline.json`:
```json
{ "attributes.oldLabel": " entfernt in <Commit>; Komponente <Pfad> geloescht" }
```
Begründungspflicht + Staleness-Detektor (`toBe` auf die gemessene Zahl),
Re-Baseline nur via `I18N_RATCHET_DUMP=1`.

### 3.3 Plural-Awareness

Vor dem Missing-Check die Pluralformen auflösen:

```
resolve(k) = k_one/k_other vorhanden      → OK (Bare-k NICHT erforderlich)
             nur k vorhanden              → OK, aber WARN „Plural fehlt"
             k und k_one/k_other          → Bare-k ist toter Ballast → (2)
```

Damit entfallen die 5 Phantom-Bare-Keys und die 27 echten
Bare-Keys (Evidence: `wp3b-01`, Abschnitt Plural) werden als *eigene*
Fehlerklasse sichtbar statt als Missing-Key.

### 3.4 Coverage-Lücke für dynamische Keys schließen

*Statisch:* für jeden Template-Key `` t(`PREFIX.${…}`) `` muss
`PREFIX.*` in beiden Locales nicht-leer sein.

```
for each prefix in dynamicPrefixes(prodFiles):
    expect(keysMatching(prefix + ".")).not.toHaveLength(0)
```
Aktuell betroffen: 60 Stellen in 34 Dateien.

*Laufzeit:* `i18n.init({ missingKeyHandler })` in `frontend/src/i18n/index.ts`
mit Dev-Overlay bzw. Telemetrie. Das ist der einzige Weg,
`` t(`sections.${x}`) `` vollständig abzusichern.

### 3.5 Scope

```ts
function collectProdSourceFiles(dir: string): string[] {
  // ausschliessen: /test/, /__tests__/, /__mocks__/, *.test.ts(x), *.spec.ts(x)
}
```

## 4. Reihenfolge der Umsetzung (Vorschlag)

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | `canvas.*` (15 Keys, 1 Datei) + `permissions.*` (14) | −29 |
| 2 | `baselines.*` (17) | −17 |
| 3 | `profile.*` + `settings.llm.*` (16) | −16 |
| 4 | `export/import.*` (12) | −12 |
| 5 | Rest + `baselines.fieldChangesCount` | −42 |
| 6 | `MISSING_KEY_BASELINE = 0` | Check scharf |
| 7 | Liveness-Check (536 tote Keys) | eigener Ratchet |
| 8 | Plural-Awareness (27 Bare-Keys) | eigener Ratchet |
| 9 | Prefix-Coverage (76 dynamische Keys) | Lücke geschlossen |

Die Reihenfolge ist nach Datei gebündelt, damit jede Zeile des Locales und
jede Datei in einem Review-Diff lesbar bleibt.