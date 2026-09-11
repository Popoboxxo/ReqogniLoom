# Attribut-Modell (3 Stufen) — Konzept, Migrationssystematik, Verifikation

Einstiegspunkt für das **3-Stufen-Attributmodell** über alle 11 Artefakt-Typen, die zugehörige
**Migrationssystematik** und das **Verifikationsprotokoll**.

| Datei | Inhalt |
|---|---|
| `attribut-modell-3-stufen.md` | **Hauptreport (v2, challenged).** Bestandsaufnahme (live gemessen), Vorarbeiten im Repo/GitHub, 9-Punkte-Challenge, korrigierter 3-Stufen-Vorschlag mit Begründung je Attribut, Umsetzungsreihenfolge mit Abhängigkeiten |
| `attribut-detailtabellen.md` | Einzeltabellen je Artefakt-Typ aus dem ersten Entwurf (Anhang; **wo sie dem Hauptreport widersprechen, gilt der Report**) |
| `attribut-migrationssystematik.md` | **AWMS** — wie Attribute und Inhalte zwischen Definitionen, Feldern und Scopes bewegt werden (deklarativer Plan, Transform-Registry, Rollback, Schnittstellen) |
| `attribut-verifikationsprotokoll.md` | Jede tragende Aussage einzeln nachgeprüft, inkl. des präzisierten `uid`-Befunds |
| `docs/se/attribut/verify_all.py` | Ausführbare Re-Verifikation (13 Prüfungen gegen API + Codestand) |

## Kurzfassung

1. **Es gibt heute kein Stufenmodell.** Attributliste und `required`-Flags sind über
   `minimal`/`standard`/`extended` **identisch** — die Presets unterscheiden nur Features.
2. **Vorschlag:** drei Stufen — *Basissatz* (nur absolut Notwendiges), *gehobene Stringenz*
   (wer will es, warum, wie prüfen wir es, wie wichtig), *Full-Blown SE* (vollständige
   Rückverfolgbarkeit, Risiko, Kritikalität, MOP/TPM, Change Control).
3. **Träger:** Kernattribute als Modellfelder (API-/MCP-Contract), alles Weitere als
   `kind="extended"`-Attribute der Attribut-Definition v2 (konfigurierbar je Tier/Tenant).
4. **Zwei Vorbedingungen** sind noch offen: `uid`-Autogenerierung (**#583**) und
   `mandatory_fields` je `(item_type, preset)` (**#912**). Zwei weitere (#409, #394) sind erledigt.
5. **AWMS** ist die fehlende zweite Hälfte der Attribut-Definition v2: v2 verwaltet *Definitionen*,
   AWMS bewegt *Daten*.

## Zugehörige GitHub-Issues

- [#929](https://github.com/Popoboxxo/ReqogniLoom/issues/929) — 3-Stufen-Attributmodell (dieser Report)
- [#930](https://github.com/Popoboxxo/ReqogniLoom/issues/930) — Attribut- & Wert-Migrationssystematik
- [#871](https://github.com/Popoboxxo/ReqogniLoom/issues/871) — INCOSE-Kernattribute (`rationale`, `source`, `owner`, `priority`)
- [#583](https://github.com/Popoboxxo/ReqogniLoom/issues/583) — IEEE-29148-Pflichtfelder, `uid`
- [#408](https://github.com/Popoboxxo/ReqogniLoom/issues/408) — Pflichtfelder je Rigor-Stufe
- [#393](https://github.com/Popoboxxo/ReqogniLoom/issues/393) — MOE/MOP/TPM (`Measure`-Entität)
- [#912](https://github.com/Popoboxxo/ReqogniLoom/issues/912) — `mandatory_fields` je Preset
- [#920](https://github.com/Popoboxxo/ReqogniLoom/issues/920) — Artefakt-/Attributfelder konsistent

Vorarbeiten: `docs/archive/audits/SYSTEMAUDIT_SE_METHODOLOGY_2026-08-07.md` (P4-17, P4-20),
`docs/superpowers/specs/2026-09-11-attribute-definition-v2-design.md`.

## Verifikation reproduzieren

```bash
cd <repo>            # Checkout v1.8.0-beta.10 oder neuer
python3 docs/se/attribut/verify_all.py
```

Voraussetzungen: `.env` mit `SYSTEM_ADMIN_PASSWORD`, Backend auf `127.0.0.1:8001`
(override via `RL_BASE`).

**Basis aller Messungen:** v1.8.0-beta.10 (`b4c3a910`), QS-Instanz `172.20.5.120`. PROD wurde nicht angefasst.
