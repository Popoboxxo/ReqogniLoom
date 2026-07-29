decomposition_status: terminal

# L3 COMP-ICD-002_ContractValidator Architecture

> **Level:** L3 (Component internal design)
> **System:** IcdManagementSystem (ARCH-L1-014)
> **Component:** COMP-ICD-002_ContractValidator
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further architecture decomposition.

---

## 1. Verantwortlichkeit

Die Komponente `ContractValidator` ist ein statusloses Modul, das die semantischen Regeln des Design-by-Contract durchsetzt. Sie vergleicht Vorbedingungen (Preconditions), Nachbedingungen (Postconditions) und Invarianten zwischen ICD-Versionen, um Inkompatibilitäten (Breaking Changes) präzise zu erkennen.

---

## 2. Internal White-Box Design (Klassen & Datenstrukturen)

Da diese Komponente terminal ist, wird hier ihr internes Software-Design spezifiziert.

### 2.1 Klassen und Hauptmethoden

**Klasse `ContractValidator`**
Eine statuslose Service-Klasse für semantische Vergleiche.

- `validate_syntax(payload: dict) -> bool`
  - Prüft das eingehende DTO strukturell auf das Vorhandensein der Pflichtfelder (Richtung, Typ, Vor-/Nachbedingungen, Invarianten).
- `validate_contract(old_version: IcdVersion, new_version: IcdVersion) -> ValidationResult`
  - Analysiert die Änderungen im Vertrag zwischen alter und neuer Version.
  - Prüft Regel 1 (Covariance/Contravariance): Vorbedingungen dürfen nur aufgeweicht, nicht verschärft werden.
  - Prüft Regel 2: Nachbedingungen dürfen nur verschärft, nicht aufgeweicht werden.
  - Prüft Regel 3: Invarianten müssen erhalten bleiben.
  - Erkennt Breaking Changes in der Payload-Datenstruktur (z.B. gelöschte Pflichtfelder).

### 2.2 Datenstrukturen

- `ValidationResult`:
  - `is_breaking: bool` — Indikator, ob ein Kompatibilitätsbruch vorliegt.
  - `breaking_changes: list[str]` — Eine Liste von Beschreibungen, welche vertraglichen Zusagen gebrochen wurden (z.B. "Vorbedingung 'requires_auth' wurde neu hinzugefügt").

---

## 3. Erfüllung der L3 Anforderungen

| REQ-ID | Erfüllung durch Design |
|--------|------------------------|
| REQ-L3-ICD-002-001 | Die Methode `validate_syntax` stellt die strukturelle Korrektheit des Design-by-Contract Modells sicher und weist fehlerhafte Inputs ab. |
| REQ-L3-ICD-002-002 | Die Hauptmethode `validate_contract` setzt den semantischen Vergleich um und befüllt das `ValidationResult`-Objekt mit expliziten Fehlerbeschreibungen bei Breaking Changes. |

---

## 4. Schnittstellen Mapping

| IF-ID | Implementierung in Code |
|-------|-------------------------|
| IF-ICD-INT-001 | Der `IcdManager` nutzt die Methode `validate_contract` synchron, um den Status vor der Aktualisierung zu prüfen. |

---

*Erstellt durch se-architect-Agent | 2026-06-21*
