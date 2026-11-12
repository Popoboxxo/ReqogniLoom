---
adr_id: ADR-028
title: "Allokation wird ein Objekt mit Lebenszyklus; Freigabe kaskadiert rigor-abhängig"
status: accepted
date: 2026-11-12
deciders: [se-architect, user]
affected_reqs: [REQ-L0-039, REQ-L0-019]
superseded_by: null
---

# ADR-028: Allokation wird ein Objekt mit Lebenszyklus; Freigabe kaskadiert rigor-abhängig

## Kontext

ADR-027 leitet die Spezifikationsebene eines Requirements leaf-relativ aus der
Allokation auf ein Architekturelement ab. Die Allokation selbst ist aber
weiterhin nur eine `TraceLink(allocated-to)`-Kante: sie hat keinen Status,
keine Version, keinen Lebenszyklus. Daraus folgen drei Lücken (Konzept #1670):

1. **Kein Freigabebegriff für Allokationen.** Ein freigegebenes Element schützt
   heute nur seine Position im Baum (`application/artifact_freeze.py`), nicht
   die Zugehörigkeit der allozierten Requirements und nicht deren Inhalt.
2. **Mehrfachallokation ist undefiniert.** D9 verlangt, den Konflikt zu zeigen
   statt ihn zu rechnen; heute gibt es dafür weder eine Regel noch eine
   Konfiguration.
3. **Kein Change-Request-Pfad.** Ein Änderungsversuch nach Freigabe endet in
   einem 409 ohne Verweis, was der Nutzer als Sackgasse erlebt.

Der Rigor-Grad (minimal/standard/extended) ist bereits ein Workspace-Preset,
steuert aber weder Ordnung noch Freigabe noch Inhaltsfreeze.

## Alternativen

- **Nur Kante behalten (Ist-Zustand).** Kein Migrationsaufwand, aber Status,
  Freigabe und Impact-Vorschau bleiben unmöglich. Abgelehnt.
- **Allokation nur aus der Kante ableiten (Objekt als View).** Kein
  Dual-Write-Risiko, aber ein Status lässt sich nicht speichern, ohne die Kante
  zu verändern; ein `revoked`-Zustand bräuchte eine zweite Kante. Abgelehnt.
- **Objekt + Dual-Write mit Invariante (gewählt).** `Allocation` trägt Status
  und Freigabestand, die Kante bleibt die Graph-Wahrheit für alle bestehenden
  Leser (Coverage, Baseline, Audit, MCP). Ein Test und eine
  Konsistenzprüfung sichern „jede Kante hat genau ein Objekt und umgekehrt".
- **Mehrfachallokation mit min/max-Rechenregel (abgelehnt).** Würde eine
  fachlich willkürliche Ebene erfinden; D9 verlangt, den Konflikt sichtbar zu
  machen (Ebene `unresolved`, Audit-Befund), nicht ihn zu glätten.
- **Nur Element-Release (abgelehnt).** Requirement ohne Container bliebe
  unreleasbar; D10 verlangt beide Pfade mit Vorrangregel.
- **Inhalt immer einfrieren (abgelehnt).** Auf minimal/standard wäre das eine
  Verhaltensänderung ohne Rigor-Bezug; D12 koppelt den Inhaltsfreeze an
  `extended`.

## Entscheidung

- **D9 — Mehrfachallokation, per Konfiguration schaltbar.** Zwei
  Q1-Preferences je Workspace, Änderungen auditiert:
  `allocation.cardinality` = `single` (Default, heutiges Verhalten, 409
  `AllocationConflictError` bei der zweiten Allokation) oder `multiple`;
  `allocation.conflict_severity` = `info` | `warning` (Default) | `blocker`.
  Bei `multiple` gibt es **keine Rechenregel**: ohne genau eine führende Kante
  (`Allocation.is_primary`) bleibt die Ebene `unresolved`
  (`multiple_allocations`), und der Audit meldet `allocation.multiple` mit dem
  eingestellten Schweregrad. Zwei führende Kanten werden abgelehnt. Der Wechsel
  `multiple → single` ist gesperrt, solange Mehrfachallokationen existieren
  (409 mit Anzahl).
- **D10 — Freigabeeinheit: beides.** Element-Release (kaskadiert) und
  optionaler Einzel-Release je Requirement. Ein Element-Release umfasst seine
  Requirements; der Einzel-Release bleibt der Spezialfall ohne
  Element-Release. Eine Sperre kann durch keinen der beiden Pfade umgangen
  werden.
- **D12 — Inhaltsfreeze abhängig vom Rigor.** `extended`: Inhaltsversion der
  allozierten Requirements wird eingefroren. `standard`/`minimal`: nur
  Struktur und Kanten.
- **Freigabe:** Das Element-Release pinnt die Ebene (`tier_key`) im
  Release-Stand; Baselines erben den gepinnten Wert (Stufe 4).

## Statuswechsel

- 2026-11-12: `proposed` → `accepted` (Freigabe durch Daniel, Gate aus Phase E Task 2; Spec `docs/superpowers/specs/2026-11-10-allokation-objekt-release-design.md` mit freigegeben).

## Konsequenzen

- **Positiv:** Ein Requirement hat einen expliziten Allokationsstatus; die
  Kante bleibt unverändert lesbar für alle bestehenden Pfade; Freigaben werden
  rigor-gerecht (minimal/standard ohne Verhaltensänderung); Konflikte werden
  sichtbar statt still geglättet; Änderungen nach Freigabe haben einen
  CR-Pfad mit 409 + Verweis statt einer Sackgasse.
- **Negativ:** Zwei Schreibpfade (Kante und Objekt) brauchen eine Invariante
  und einen Backfill; jede Migration muss idempotent sein. D9 bringt zwei neue
  Preferences und einen Audit-Regelpfad. Der Inhaltsfreeze auf `extended`
  erzeugt zusätzliche `ArtifactVersion`-Zeilen und verlängert Release-Läufe.
- **Risiko:** Direkte Kanten-Schreibpfade (generischer TraceLink, Import,
  Baseline-Restore) können das Objekt umgehen — deshalb Invariante plus
  Konsistenzprüfung als Pflichtteil der Umsetzung.
