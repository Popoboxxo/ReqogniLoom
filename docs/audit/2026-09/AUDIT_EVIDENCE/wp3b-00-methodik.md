# WP-3b Evidence 00 — Methodik & Fehlerkorrekturen

## Zweck

WP-3 hat mit einem Regex-Messfehler zwei Phantom-Findings produziert
(`AUD-2026-09-021`: „441 Hex-Literale / 74 Verstöße", tatsächlich nach
Kommentar-Stripping 0). WP-3b hat deshalb **jede** Zählung gegen die drei
bekannten Fehlerklassen abgesichert und jede Korrektur dokumentiert.

## Schutzmaßnahmen (in allen Scans)

1. **Block-Kommentare entfernen** — `/\*[\s\S]*?\*/` (JSDoc, `/* */`, JSX `{/* */}`).
   Ersetzt durch Zeilenumbrüche, damit Zeilennummern gültig bleiben.
2. **Zeilen-Kommentare entfernen** — `//` außerhalb von `"`, `'`, `` ` ``.
3. **Test-Dateien getrennt zählen** — `*.test.ts(x)`, `*.spec.ts(x)`,
   `src/test/`, `src/__tests__/`, `src/__mocks__/`, `vite-env.d.ts`,
   `jsx-global.d.ts`.
4. **Regex-Vorzeichenprüfung** — ein Treffer `t(` wird verworfen, wenn das
   Zeichen davor zu `[A-Za-z0-9_$'"\`.]` gehört. Ohne diese Prüfung erzeugen
   `query.set("status")`, `document.createElement("a")`, `.split("_")`,
   `await import("mermaid")` 72 Fehltreffer (gemessen: 2 474 → 2 402).

## Fehlerklasse A — Regex-Zeichenklasse

**Symptom:** erste Zählung meldete 480 Hex-Literale in Produktion.
**Ursache:** die Kommentar-Strip-Regex wurde als `[\sS]` gebaut (Zeichenklasse
aus `Whitespace` ∪ **literalem `S`**) statt `[\s\S]` (`\s` ∪ `\S`). Damit
strippte sie nichts und JSDoc-Zeilen wie `* ARCH-L1-001 ... (#936, ...)` landeten
in der Zählung — exakt die WP-3-Fehlerklasse.
**Korrektur:** `[\s\S]`, danach 37 Treffer in 5 Dateien.

> Nebenbefund für die Methodik-Doku: `re.search('/\\*[\\s\\S]*?\\*/', s)`
> liefert für eine Datei mit gültigem Blockkommentar `None`, während
> `re.search('/\\*.*?\\*/', s, re.S)` korrekt matcht. Der Unterschied ist
> ein echter Python-`re`-Unterschied und keine Scanner-Beschädigung —
> der Effekt war identisch (kein Strip).

## Fehlerklasse B — Substring statt Mengenoperation

**Symptom:** `t()`-Vorzeichenprüfung ließ `params.set("status")` durch.
**Ursache:** `"e" not in "[A-Za-z0-9_...]"` prüft **Substring**, nicht
Zeichenmitgliedschaft — `e` kommt in der Zeichenklasse nicht wörtlich vor.
**Korrektur:** explizites Alphabet `set("ABC…xyz0123456789_$'\"`.")`.
Danach 2 402 statt 2 474 Prod-Treffer.

## Fehlerklasse C — Shell-Quoting vs. Scanner-Regex

Beim Erzeugen der Scan-Skripte wurde `~` als Platzhalter für `'` benutzt und
per `tr '~' '\047'` übersetzt. Grund: die Kommando-Ebene (Windows `cmd`) parst
`"` als quoting-Charakter und leitet Redirects (`<`, `>`, `|`, `&`) **vor**
der Shell-Auswertung aus — ein `(` in einer Regex (`(?<!`) brach dadurch jedes
Kommando. Diese Dateien lagen außerhalb des Repos
(`%TEMP%\wp3b\`) und wurden **nicht** ins Repo geschrieben (Audit-Auftrag:
keine Code-Änderungen).

## Reproduktion

Alle Zahlen dieses Berichts stammen aus zwei Skripten in
`%TEMP%\wp3b\` (`i18n.py` für i18n, `a4.py`/`a5.py` für Token/testid).
Kernstück des Kommentar-Strippings und der t()-Erkennung:

```
CMT  = /\[\s\S]\*\?\\\*/
BAD  = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$'\"`."
TCORE= t\( \s* ['"`] ([a-zA-Z0-9_.]+) ['"`]
okp(s,i) = (i == 0) or (s[i-1] not in set(BAD))
```

## Gegenprobe gegen die Repo-eigene Ratchet-Baseline

Die unabhängige Zählung „116 fehlende Keys" deckt sich **exakt** mit der im
Repo eingefrorenen Konstante `MISSING_KEY_BASELINE = 116`
(`frontend/src/test/i18n-parity.test.ts:186`). Zwei voneinander unabhängige
Zählwege — der des Repos (ohne Kommentar-Stripping, `*.test.*` ausgeschlossen,
`src/test/*.ts`-Helfer **mit** eingeschlossen) und der von WP-3b (mit
Kommentar-Stripping, alle Test-Verzeichnisse ausgeschlossen, zusätzlich
`<Trans i18nKey>`) — kommen auf dieselbe Zahl. Das ist der stärkste
einzelne Validierungspunkt dieses Berichts.

Gegenprobe 2: `STYLE_BRACE_BASELINE = 3` (`ui-ratchet.test.ts:747`) —
`grep -rn 'style={{' --include=*.tsx --include=*.ts frontend/src | grep -v test`
liefert genau 3 Treffer, **alle drei in Kommentaren**
(`ArchitectureEditors.tsx:741`, `RequirementTreeNode.tsx:82`,
`WorkspaceSettings.tsx:21`). Reale Inline-Styles: 0.

Gegenprobe 3: `HEX_LITERAL_OCCURRENCE_BASELINE = 17` / `..._FILE_BASELINE = 3`
(`ui-ratchet.test.ts:955-956`) — `.tsx`-Prod ohne Kommentar-Stripping:
`CanvasEditor.tsx` 15 + `GraphEdge.tsx` 1 = 16 in 2 Dateien; die 17. Datei
(`SidebarNavigation.tsx`, `#317`) ist ein Issue-Nummern-Fehlpositiv.
Hinzu kommen 21 Hex-Literale in drei `.ts`-Produktionsdateien, die der
Ratchet wegen `collectNonTestTsxFiles()` (`ui-ratchet.test.ts:47`, nur `.tsx`)
nie sieht.