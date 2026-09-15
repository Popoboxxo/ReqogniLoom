---
type: STRATEGY
scope: Lokales Test-Gate (Backend pytest + Frontend vitest)
status: active
date: 2026-09-15
author_agent: documenter
---

# Known Reds — lokales Test-Gate

Zentraler, **fortschreibbarer** Ort für bekannte, nicht-produktbezogene Reds des
**lokalen** Test-Gate-Volllaufs. Zweck: Ein later Volllauf-Report soll einen
bekannten Red als bekannt (und damit als „kein neuer Blocker") einordnen können,
ohne jeden Fall neu zu diagnostizieren.

> **Abgrenzung:** Dieses Dokument ist **keine** Release-Historie und **kein**
> Ersatz für einen Release-Bericht. Historische Release-Berichte werden **nicht**
> rückwirkend umgeschrieben; sie bleiben als Audit-Trail unverändert. Der
> ursprüngliche Known-Issues-Abschnitt liegt in
> `docs/se/reports/RELEASE_v1.8.0-beta.11.md` §9 (KI-1, KI-2). Hier wird er
> **fortgeschrieben und korrigiert**, nicht ersetzt.

---

## 1. Ausgangslage des dokumentierten Laufs

- **Branch:** `feat/menschen-im-system`
- **HEAD:** `4b891f53`
- **Gate-Ergebnis:** **rot — aber kein Red ist branch- oder produkt-attribuierbar.**
  Jeder beobachtete Red ist isoliert grün bzw. deterministisch
  umgebungsbedingt (Live-Stack / Dev-DB bzw. Volllast-Timeout).
- **Verhältnis zur bisherigen Baseline:** Die bislang dokumentierte
  Known-Red-Baseline (KI-1, KI-2 aus beta.11) deckt die in diesem Lauf
  beobachteten Symptome **nicht** ab. KI-1 trifft zwar dieselbe Testklasse, hat
  aber einen anderen Root-Cause (Korrektur unten); F2 und F3 sind neu.

Das maßgebliche Gate (CI) ist von keinem der hier gelisteten Reds betroffen:
Alle Fälle sind in CI übersprungen oder laufen dort unter anderer Last.

---

## 2. KI-1 — **Korrektur/Ergänzung** (F1)

**Klasse/Datei unverändert:** `backend/mcp_server/tests/test_mcp_api_key_roles.py`
→ `TestMcpApiKeyRolePropagation` (7 Reds in diesem Lauf).

**Root-Cause ist ein anderer als in `RELEASE_v1.8.0-beta.11.md` §9 KI-1
beschrieben.** Die dort genannte Symptom-Erklärung (Workspace-Paginierung,
`Demo Workspace` auf Rang 152/153) führt **in die falsche Richtung** und
beschreibt diesen Lauf nicht.

**Tatsächlicher Root-Cause (verifiziert):**

- Die Tests sind Live-Stack-E2E gegen die **persistente Dev-DB** (kein
  Django-Test-Fixture-DB-Lauf).
- Der Admin hat in der Dev-DB genau **10 aktive API-Keys** — exakt das Cap. Die
  REST-API antwortet auf `POST /api-keys/` mit
  `User already has the maximum of 10 active API keys.`
- Der Helper `_revoke_all_active_keys()`
  (`backend/mcp_server/tests/test_mcp_api_key_roles.py:154-171`) sendet die
  `DELETE`s, **prüft deren Statuscodes aber nicht**. Schlägt ein `DELETE` fehl,
  greift die „Freischaufeln"-Logik **stumm nicht**; der anschließende Retry
  läuft wieder in das 10-Key-Cap und die Assertion schlägt fehl.
- **Deterministisch:** 2× isoliert reproduziert. Eine frische `DB_NAME` ist
  **wirkungslos**, weil der Test gegen den laufenden Live-Stack geht, nicht
  gegen die Test-DB.
- **In CI:** via `pytest.mark.skipif(CI or GITHUB_ACTIONS)`
  (`test_mcp_api_key_roles.py:79-90`) übersprungen.
- **Einordnung:** **nicht-produktbezogen** — ein Test-Helper-Defekt plus
  Dev-DB-Zustand, kein Produktdefekt.

**Folge-Fix (nicht Teil dieses Dokuments, kein Codeauftrag):** Status der
`DELETE`-Aufrufe in `_revoke_all_active_keys()` prüfen/asserten und ggf. auf die
10-Key-Grenze reagieren, statt stumm weiterzulaufen.

---

## 3. F2 — Frontend-Volllauf-Interferenz in `ArtifactForm.test.tsx`

- **Datei/Case:** `frontend/src/test/ArtifactForm.test.tsx` — „renders a multiple
  actor attribute as a chip list".
- **Symptom (Volllauf):** Assertion
  `expected 'Alice Admin', received 'Unbekannter Wert: u-1'`.
- **Isoliert:** 2× **48/48 grün**.
- **Datei ist branch-unverändert** (keine Änderung auf `feat/menschen-im-system`).
- **Einordnung:** Ordering-/Interferenz-Flake unter Volllast (Actor-Directory-
  Auflösung greift im Volllauf anders als isoliert), **kein Produktdefekt** und
  **nicht branch-attribuierbar**.

---

## 4. F3 — Zusätzliche Last-Timeouts außerhalb KI-2

Beobachtet: `frontend/src/test/action-labels.test.ts` und
`frontend/src/test/i18n-parity.test.ts`. Der Vitest-Timeout beträgt den
**Default 5000 ms** (`frontend/vite.config.ts` setzt keinen expliziten
`testTimeout`); isoliert laufen beide Dateien in **1,8–2,9 s** grün.

- **`action-labels.test.ts`:** Volllauf-Timeout, isoliert grün — gleiche Klasse
  wie KI-2 (load-induziert).
- **`i18n-parity.test.ts`:** Der Failure war **der Timeout**, **keine**
  Ratchet-Verletzung. Die Baseline `MISSING_KEY_BASELINE = 123`
  (`frontend/src/test/i18n-parity.test.ts:160`) **hält** (135 → 123). Explizit
  festgehalten, damit ein späterer Volllauf-Bericht diesen Red nicht als
  i18n-Regression fehldeutet.
- **Einordnung:** load-induzierte Timeouts, **kein Produktdefekt**.

---

## 5. Bereits belegt / weiterhin gültig

- **KI-2** (`frontend/src/test/design-tokens.test.ts` — Flake-Timeout in den
  Dateisystem-Scan-Tests): **reproduziert** in diesem Lauf. Root-Cause und
  Einordnung aus `RELEASE_v1.8.0-beta.11.md` §9 KI-2 bleiben unverändert gültig.
- **2 pgvector-Tests** traten in diesem Lauf **nicht** rot auf.

---

## 6. F4 — Info: nicht-UTF-8-Datei wird von ruff still übersprungen

`backend/attribute_definitions/tests/test_field_validation.py` ist **nicht
valides UTF-8** (gemischte `E2 80 94`- und `0x98`-Bereichs-Bytes) → ruff
überspringt die Datei **still bei Exit 0**. Das ist kein Test-Gate-Red, aber ein
Blind-Spot der Lint-Abdeckung: Die Datei wird derzeit nicht gelintet, ohne dass
das Gate das meldet.

---

## 7. Pflegehinweise

- Neue Known Reds datiert ergänzen, inkl. `Symptom` / `Root-Cause` / `Isoliert
  grün?` / `Branch-attribuierbar?` / `Produktdefekt?`.
- Reds, die behoben sind oder nicht mehr reproduzieren, in einen
  „Historisch"-Abschnitt verschieben statt zu löschen (Audit-Trail).
- **Release-Berichte bleiben unangetastet.**
