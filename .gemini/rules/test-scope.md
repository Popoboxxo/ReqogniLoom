# Test-Scope — Kein unangeforderter Full-Suite-Run

**Gilt für alle code-ändernden Agenten** (developer, junior-developer, senior-developer, tester,
se-developer, se-junior-developer, se-senior-developer und alle weiteren Rollen die Quellcode modifizieren).

## Pflicht nach Code-Änderung

Nach einer Code-Änderung ausschließlich die direkt betroffenen Test-Dateien/Module ausführen:

```bash
# Backend — nur das betroffene Modul/die betroffene Datei
pytest backend/requirements_app/tests/test_<modul>.py -v

# Frontend — nur der betroffene Test-Scope
npm test -- --testPathPattern=<ComponentName>
```

**Verboten:** Ungefilterte Suite-Läufe ohne explizite User-Anfrage:

```bash
pytest          # VERBOTEN (ohne Pfad-Filter)
npm test        # VERBOTEN (ohne --testPathPattern oder Datei-Argument)
```

## Wann ein voller Suite-Lauf erlaubt ist

| Bedingung | Erlaubt? |
|-----------|----------|
| User fordert explizit an ("lass alle Tests laufen", "voller Testlauf", "run all tests") | Ja |
| Pre-Merge- oder Pre-Release-DoD-Gate schreibt es ausdrücklich vor | Ja |
| Eigene Initiative nach lokalem Bugfix | **Nein** |
| "Zur Sicherheit" ohne User-Anfrage | **Nein** |

## Verhältnis zu DoD-Kriterien

Das DoD-Kriterium "Test vorhanden und grün" (`dod-criteria.md`) gilt weiterhin — aber:
- "grün" bedeutet: die scoped Tests für die Änderung laufen fehlerfrei
- Ein voller Suite-Lauf ist kein Bestandteil des DoD, solange der User ihn nicht anfordert

## Begründung

Ein ungefilteter Full-Suite-Run (Backend `pytest`) dauert in diesem Projekt ~66 Minuten.
Gezielte Test-Execution ist schneller, aussagekräftiger und ressourcenschonender.

## Propagation

Diese Datei ist **nicht** durch sync.py verwaltet (bewusst projekt-lokal).
Manuelle Spiegelung: `.claude/rules/test-scope.md`, `.continue/rules/test-scope.md`.
