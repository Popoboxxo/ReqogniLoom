---
adr_id: ADR-024
title: "Memory-Injektion je KI-Aktivität/Workspace/User und Memory-Ablagen — ADR-light mit Umsetzungsschnitt (#1339, #1317)"
status: accepted
date: "2026-10-26"
deciders: [user, documenter]
affected_reqs: [REQ-L2-PT-001, REQ-192]
superseded_by: null
---

# ADR-024: Memory-Injektion je KI-Aktivität/Workspace/User und Memory-Ablagen

**Status:** accepted (2026-10-26) — **Entscheidung: über Q1-Schlüssel** (ENT-A5 = A,
ENT-A6 = C, ENT-A7 = B); ADR-light. Nutzerentscheidung vom 2026-10-26
(`docs/plans/2026-10-21-entscheidungen-offen.md` §0b). Dieses ADR implementiert nichts; der
untenstehende Umsetzungsschnitt (#1339, #1317-Doku-Teil) **startet mit Annahme (2026-10-26)**.
**Datum:** 2026-10-26 (Entwurf: 2026-10-17)
**Entscheider:** `user`; **Text:** `documenter` (ENT-X4 = A: Texte `documenter`, Review
`concept-reviewer`, Status Nutzer). **Autor des Entwurfs:** `concept-specifier`
(Entscheidungsvorbereitung D7, Branch `docs/round5-decision-prep-d5-d7`, Basis
`origin/main @ 12cce237`; kein Commit).
**Betroffene REQs:** REQ-L2-PT-001 (Prompt-Slot-/Template-Schicht, von `prompt_slots.py`
und `prompt_resolver.py` selbst als `req_id` geführt — dort lebt die Injektionspolitik);
REQ-192 (Memory-Antwort-/Backend-Pfad; von der Ablagen-/Embedding-Kopplung aus #1317
berührt). *Anmerkung:* Eine eigenständige REQ für die Memory-Injektionspolitik existiert
nicht (Stand 2026-10-17); analog ADR-021/REQ-194 empfiehlt sich eine REQ-Neuanlage im
`requirements`-Prozess (Folgeaufgabe, nicht Teil dieses ADR).
**Bezug (Issues):** #1339 (Injektion je Aktivität/Workspace/User schaltbar), #1317 (drei
Memory-Ablagen, doppelte Embedding-Config), #1023 (Artefakt-Scope + Prompt-Injektion),
#1002 (kanonischer Memory-Store), #1300 (Lern-Kreislauf), #1336/#1337 (Honcho — Richtung D6),
#1248 (Scope-Mismatch). Plan: `docs/audit/2026-10/bugfix-round-5-plan.md` (Entscheidungsspur D7).
**Konzept:** `MEMORY_INJEKTION_KONZEPT.md` ist **nicht Teil dieses Repos** — das Issue #1339
verweist auf `/opt/data/reqogniloom-env/qa-beta20/MEMORY_INJEKTION_KONZEPT.md` auf der
QS-Instanz (172.20.5.120). Dieses ADR stützt sich auf den im Issue dokumentierten Auszug
(3-Ebenen-Modell, Minimum-Logik); das Vendoring des Konzepts ins Repo ist offener Punkt O2.

**Bezug zum Code** (verifiziert am 2026-10-17 im Arbeitsbaum, `origin/main @ 12cce237`):

- `backend/application/prompt_slots.py`
  - `:66-116` `_DATA_VARIABLES_BY_SLOT` — **12 benannte Slots** plus die geteilte
    `INTERVIEW_PROTOCOL_DATA_VARIABLES`-Menge (`:47-54`) deklarieren `memory_context`
    (von #1339 als „13 KI-Aktivitäten" gezählt).
  - `:63-65` **`interview.transcript_summary` ist bereits bewusst memory-frei** („must not
    introduce outside facts into that digest").
  - `:108` `interview.transcript_summary` ohne `memory_context`; `:110-115` **`memory.extract`
    ist bereits bewusst ohne `memory_context`** (Selbstreferenz = Feedback-Schleife).
  - `:85` **`bundle_compression` trägt `memory_context`** — der verbleibende Ausreißer gegen
    das eigene Prinzip (Verdichtung darf kein Fremdwissen sehen).
- `backend/application/prompt_resolver.py`
  - `:225-257` `_auto_memory_context(ctx, workspace_id, artifact_id, entity_type, data_kwargs)`
    — Fail-open; **kein** `slot_name`-Parameter.
  - `:260-300` `resolve_and_render(slot_name, …)` — hier existiert `slot_name`; die
    Auto-Injektion erfolgt, wenn der Slot `memory_context` deklariert (`:296-299`).
- `backend/memory/context_builder.py:128-184` — `build_memory_context(tenant_id, workspace_id,
  user_id, query_text, *, artifact_id=None, entity_type="")`; **kein** `slot_name`;
  Workspace-Toggle-Check `_is_workspace_memory_enabled`; `_search_targets` liest **bereits**
  den `user`-Scope (`:187-194`).
- `backend/memory/models.py:137-150` — `WorkspaceMemorySettings` (OneToOne `workspace` +
  `enabled`, fehlende Zeile = AN) — der **einzige** Schalter heute; **kein**
  `UserMemorySettings`-Modell.
- `backend/memory/memory_rest.py:1420-1442` — `MemorySelfServiceView` für
  `/api/v1/memory/me/` (GET/DELETE/POST, eigene Person); **keine** Settings-Unterseite.
- `backend/rest_api/urls.py:664-665` — Route `memory/me/`.

**Vermerk zur Ablage:** `docs/se/ADR/` ist die gelebte Konvention. Dieses ADR ändert keine
REQ-Datei, keine Kaskaden-Datei und keinen Code.

---

## Entscheidungsvorlage

> **Überholt (historischer Wert, Stand Entwurf 2026-10-17).** Der Nutzer hat am 2026-10-26
> entschieden (`docs/plans/2026-10-21-entscheidungen-offen.md` §0b): **ENT-A5 = A** (Schalter
> als Q1-Schlüssel, `WorkspaceMemorySettings` nur Fassade), **ENT-A6 = C** (Datengrenzen für
> alle Memory-Blöcke, Budget-Default 0), **ENT-A7 = B** (`user`-Scope bleibt bei
> `allow_user_opt_out=false` aus). Die Entwurfs-Empfehlung bleibt nur als Audit-Trail stehen;
> maßgeblich ist §Entscheidung dieses ADR.

- **Was ist zu entscheiden:** (1) Ob die Memory-Injektion das im Konzept (#1339)
  vorgeschlagene **Drei-Ebenen-Modell mit Minimum-Logik** erhält (System-Policy ⊂
  Workspace ⊂ User, fail-safe per UND); (2) die **Opt-out-Semantik** des neuen
  Nutzer-Schalters; (3) ob und wie der #1317-Doku-Teil (Ablagen-Inventar, Embedding-
  Kopplung) als Teil desselben Schnitts umgesetzt wird.
- **Empfehlung (Entwurf, überholt):** Drei-Ebenen-Modell **übernehmen** (Minimum gewinnt);
  HARD_OFF als Code-Konstante für Verdichtung + Selbstreferenz; `bundle_compression` verliert
  den Memory-Block; Nutzer-Schalter wirkt auf die **Aktivitäten dieses Nutzers** (nicht nur
  seinen `user`-Scope) — als Entscheidungspunkt O1 markiert; Transparenzfeld `memory_injected`
  in den Antworten; #1317 als Doku-/Härtungsteil desselben Schnitts (WP-D).
- **Konsequenz bei Annahme — so entschieden am 2026-10-26, ENT-A5 = A:** Umsetzung additiv mit
  **Defaults = heutigem Verhalten** (nur HARD_OFF und `bundle_compression` ändern die Injektion
  bewusst); **kein eigenes `UserMemorySettings`-Modell** — stattdessen Q1-Schlüssel
  (`memory.enabled` auf user-Ebene, `memory.disabled_slots` global/workspace/user,
  `memory.allow_user_opt_out` auf Workspace-Ebene) und `WorkspaceMemorySettings` nur als Fassade
  (ENT-A5 = A); neue REST-Fassade über `PreferenceService.set_level`; Doku.
  *Historischer Entwurfsstand dieser Zeile (überholt): „Konsequenz bei Annahme: eigenes
  `UserMemorySettings`-Modell + Migration für die Nutzer-Ebene" — mit ENT-A5 = A entfallen
  Modell und Migration.*
- **Konsequenz bei Ablehnung:** Die pauschale Injektion bleibt; Verdichtungs-Slots wie
  `bundle_compression` sehen weiteres Fremdwissen; es gibt weiterhin keinen Nutzer-Schalter.
- **Grober Aufwand:** ADR = klein; Schnitt = mittel (2 Modelle/Migrationen, Resolver-Filter,
  1 REST-Route, Tests, Doku; #1317-Teil davon überwiegend Doku + kleiner Startup-Check).
  *Mit ENT-A5 = A entfällt die Modell-/Migrationshälfte; übrig bleiben Q1-Schlüssel +
  Fassade.*
- **Offene Punkte:** s. §Offene Entscheidungen (O1–O5).

---

## Kontext

**1. Injektion ist heute ein Slot-Property — und fachlich zu pauschal.** Jeder Slot, der
`memory_context` deklariert, bekommt automatisch den Memory-Block (Workspace/Artifact/User,
artifact-first; `prompt_resolver.resolve_and_render`). Regeln existieren nur implizit im Code:
`interview.transcript_summary` und `memory.extract` sind bereits bewusst ausgenommen;
**`bundle_compression` aber nicht** (`prompt_slots.py:85`) — ein Verdichtungs-Slot, der dem
eigenen Prinzip widerspricht. Einen Nutzer-Schalter gibt es nicht, obwohl der `user`-Scope
bereits gelesen wird (`context_builder._search_targets`); der einzige Schalter ist
`WorkspaceMemorySettings.enabled` (an/aus für alles).

**2. #1339 schlägt drei Ebenen vor, Minimum gewinnt:**

```
injiziere(slot, user) =
      slot ∉ HARD_OFF                      # Code-Konstante: Verdichtung + Selbstreferenz
  AND slot ∈ system.default_injection_slots
  AND workspace.enabled
  AND slot ∉ workspace.disabled_slots
  AND (user.enabled OR NOT workspace.allow_user_opt_out)
  AND slot ∉ user.disabled_slots
```

Auflösung per **UND (restriktivste Ebene entscheidet)** — konsistent zur bestehenden
Fail-Safe-Logik (`_is_workspace_memory_enabled`: deaktivierter Workspace liefert leer, selbst
wenn Fakten existieren). Memory ist Ergänzung, kein Erfordernis.

*Umsetzungshinweis (Nutzerentscheidung 2026-10-26, ENT-A5 = A): Die Ebenen-Schalter liegen als
**Q1-Schlüssel** vor — `memory.enabled` (Ebene `user`, Default `true`, Formelterm `user.enabled`),
`memory.disabled_slots` auf global/workspace/user, `memory.allow_user_opt_out`
auf Workspace-Ebene; `WorkspaceMemorySettings` bleibt nur Fassade (keine eigene Wahrheit).*

**3. #1317: drei Ablagen, doppelte Embedding-Konfiguration — ohne Migrations-/Kopplungshinweis.**
Gemessen auf der QS: Honcho aktiv (108 documents, 18 peers), pgvector-`mem_memory_entry` mit 57
Einträgen = **Waise aus der pgvector-Zeit**, Qdrant 1 Testpunkt. Beim Backend-Wechsel bleiben
die alten Ablagen stehen; es gibt keinen dokumentierten Migrations-/Aufräum-Pfad. Parallel:
`EMBEDDING_*` und `HONCHO_EMBEDDING_*` sind **zwei getrennte Konfigurationen für dieselbe
Sache**; heute zufällig deckungsgleich (768d, `nomic-embed-text`). Ein Modellwechsel bei
gleicher Dimension (768→768) fällt nicht auf; nur die Dimensionsprüfung greift
(`assert_collection_dimension`). Vektoren verschiedener Modelle sind nicht vergleichbar —
ein stiller Fehler wäre die Folge.

**4. Abgrenzung.** Dieses ADR berührt **nicht** die Qdrant-Richtung (ADR-022) und **nicht** den
Honcho-Produktpfad (ADR-023): Es regelt, **wer** Memory zu sehen bekommt (Injektionspolitik)
und **wie** die Ablagen/Kopplung dokumentiert und abgesichert werden. Schnittstellen existieren
nur dort, wo die Ablagen-Inventur den Qdrant-/Honcho-Status beschreiben muss (WP-D4; bei
Vollbetrieb nach ADR-022 entsprechend fortgeschrieben).

---

## Alternativen

### Option A: Drei-Ebenen-Minimum-Modell über Q1-Schlüssel — GEWÄHLT

**Beschreibung:** Injektion wird je Slot über drei Ebenen (System-Policy ⊂ Workspace ⊂ User)
per UND entschieden; HARD_OFF als Code-Konstante für Verdichtung/Selbstreferenz. Die
Ebenen-Schalter werden als **Q1-Schlüssel** geführt (`memory.disabled_slots` auf
global/workspace/user, `memory.allow_user_opt_out` auf Workspace-Ebene);
`WorkspaceMemorySettings` bleibt Fassade. `<memory>`-Datengrenzen gelten für **alle**
Memory-Blöcke inkl. `{memory_context}`; Budget-Default bleibt **0** (keine stille Kürzung) —
ENT-A6 = C. Bei `allow_user_opt_out=false` wird der `user`-Scope **nie** injiziert;
erzwingbar sind nur Workspace-/Artefakt-Memory — ENT-A7 = B.

**Abwägung:** Fachlich richtige Injektion (Verdichtung/Selbstreferenz sehen nie Memory),
Nutzer-Souveränität, ein einziger ausgewerteter Filterpfad und keine zweite
Settings-Wahrheit. Preis: Verhaltensänderung an `bundle_compression`, neue
Filter-/Fassadenfläche.

**Risiko:** NIEDRIG–MITTEL (Verhaltensänderung an einem Slot; mehr Fläche, aber klein).

### Option B: Heutige pauschale Injektion beibehalten — VERWORFEN

**Beschreibung:** Jeder Slot, der `memory_context` deklariert, bekommt den Memory-Block; kein
HARD_OFF für `bundle_compression`, kein Nutzer-Schalter; nur
`WorkspaceMemorySettings.enabled` als globaler Schalter.

**Abwägung:** Verworfen. Verdichtungs-Slots wie `bundle_compression` sähen weiteres
Fremdwissen (Widerspruch zum eigenen Prinzip), und es gäbe weiterhin keinen Nutzer-Schalter —
obwohl der `user`-Scope bereits gelesen wird. **Abgrenzung zu Option C:** In B bliebe
zusätzlich der **#1317-Teil** offen (Ablagen-Inventar, doppelte `EMBEDDING_*`/
`HONCHO_EMBEDDING_*`-Konfiguration, 57 pgvector-Waisen). B beantwortet damit nur die
Injektionsfrage mit „alles bleibt" und führt die Ablagen-Frage unbeantwortet mit; C lehnt den
Schnitt als Ganzes ab bzw. vertagt ihn.

**Risiko:** NIEDRIG im Aufwand, HOCH in der fachlichen Schieflage (Fremdwissen in
Verdichtung; keine Nutzerkontrolle).

### Option C: Schnitt ablehnen/vertagen — VERWORFEN

**Beschreibung:** Keine Änderung der Injektionspolitik; #1339 und der #1317-Teil bleiben
undokumentiert/offen.

**Abwägung:** Verworfen. Die Injektion bliebe pauschal, die Ablagen-Kopplung
(`EMBEDDING_*` vs. `HONCHO_EMBEDDING_*`) und die 57 pgvector-Waisen blieben ohne
dokumentierten Pfad — die Frage würde nur verschoben.

**Risiko:** NIEDRIG im Aufwand, HOCH darin, die Frage offen zu lassen (undokumentierte
Ablagen, stiller Modellwechsel).

---

## Entscheidung

**Entschieden: Drei-Ebenen-Minimum-Modell gemäß #1339 übernehmen — umgesetzt über
Q1-Schlüssel, ohne eigenes `UserMemorySettings`-Modell; `#1317` als Doku-/Härtungsteil
desselben Schnitts.**

**Grundlage:** Nutzerentscheidung vom 2026-10-26
(`docs/plans/2026-10-21-entscheidungen-offen.md` §0b): **ENT-X2 = A** (Entwurfstexte an die
Nutzerentscheidung anpassen, dann `accepted`), **ENT-A5 = A** (Q1-Schlüssel),
**ENT-A6 = C** (Datengrenzen für alle, Budget 0), **ENT-A7 = B** (`user`-Scope bleibt aus bei
`allow_user_opt_out=false`).

1. **HARD_OFF (Code-Konstante)** für die Klassen *Verdichtung* (`interview.transcript_summary`,
   `bundle_compression`) und *Selbstreferenz* (`memory.extract`). Für
   `interview.transcript_summary`/`memory.extract` ist das heute faktisch bereits so (Deklaration
   entfernt bzw. bewusst ohne) — HARD_OFF macht es **erzwingbar** (Regressionsschutz auch für
   Custom-Templates und künftige Slots). Für `bundle_compression` **ändert** es das Verhalten:
   der Slot verliert den Memory-Block (bewusste Verhaltensänderung, im Test abzusichern; kein
   unaufgelöster `{memory_context}`-Platzhalter im gerenderten Prompt).
2. **Workspace-Ebene (Q1):** `memory.disabled_slots` (Liste von Slot-Namen) und
   `memory.allow_user_opt_out` (Default **True** — ohne Setzen bleibt das Verhalten unverändert)
   liegen als **Q1-Schlüssel** auf Workspace-Ebene. `WorkspaceMemorySettings` bleibt **nur
   Fassade** — keine eigene Wahrheit, keine zweite Schreibwahrheit.
3. **User-Ebene (Q1, kein eigenes Modell):** `memory.disabled_slots` und `memory.enabled`
   (bool, Default `true`) als Q1-Schlüssel auf **user**-Ebene (fehlender `disabled_slots` =
   nichts deaktiviert; fehlendes `enabled` = Memory an). `memory.enabled=false` gatet den
   **gesamten** Memory-Block dieses Nutzers — **alle Scopes** —, solange
   `allow_user_opt_out=true` (Default); das ist der Formelterm `user.enabled` aus §Kontext
   Punkt 2. Ein eigenes `UserMemorySettings`-Modell entfällt (ENT-A5 = A).
4. **Filterlogik:** `slot_name` wird von `resolve_and_render` über `_auto_memory_context` bis
   `build_memory_context(..., slot_name=None)` durchgereicht; die UND-Regel aus §2 wird an
   **einer** Stelle ausgewertet, gespeist aus den Q1-Schlüsseln (Default-Verhalten ohne
   Settings = heutiges Verhalten, abzüglich HARD_OFF/`bundle_compression`).
5. **Opt-out-Semantik (entschieden, ENT-A7 = B):** Bei `allow_user_opt_out=false` wird der
   `user`-Scope **nie** injiziert; erzwingbar sind nur Workspace-/Artefakt-Memory. Das regelt
   ausschließlich den Fall eines **verbotenen** Opt-outs und beantwortet **nicht** die Frage
   nach dem Wirkungsbereich des User-Schalters — dieser folgt aus der UND-Regel
   (§Kontext Punkt 2, O1).
6. **REST (Fassade):** `GET/PUT /api/v1/memory/me/settings/` (eigene Person) ist eine **dünne
   Fassade über `PreferenceService.set_level`** — keine eigene Settings-Wahrheit; PUT schreibt
   die Q1-Schlüssel auf user-Ebene.
7. **Transparenz:** Antworten KI-führender Endpunkte/MCP-Tools tragen `memory_injected:
   {slots, scopes, count}` (analog `degraded`) — sichtbar, welcher Kontext injiziert wurde.
8. **#1317-Teil (WP-D) + Datengrenzen:** Kopplung dokumentieren
   (`EMBEDDING_MODEL_NAME`-Wechsel zieht `HONCHO_EMBEDDING_MODEL` mit); **eine Quelle oder
   lauter Check** (Ableitung der `HONCHO_EMBEDDING_*` aus `EMBEDDING_*` **oder** Startup-
   Vergleich von Modell + Dimension mit lauter Warnung); Modellwechsel-Schutz (Modellname neben
   Embeddings persistieren und beim Lesen vergleichen — Design offen, O3); **Ablagen-Inventar**
   in der Doku (welche Backends, was liegt wo, was passiert beim Wechsel: bleibt/wandert/
   verfällt; die 57 `mem_memory_entry`-Zeilen benennen und entscheiden — O4). Ergänzend aus
   **ENT-A6 = C**: `<memory>`-Datengrenzen gelten für **alle** Memory-Blöcke (auch
   `{memory_context}`); der Budget-Default bleibt **0** (keine stille Kürzung).

**Was diese Entscheidung nicht ist:** kein Honcho-/Qdrant-Richtungsentscheid (ADR-022/023);
keine Änderung an Defaults ohne Nutzeraktion; kein neues LLM-Feature (reine Politik +
Sichtbarkeit + Doku).

---

## Umsetzungsschnitt (Arbeitspakete, startet mit Annahme 2026-10-26)

| WP | Inhalt | Dateien (Referenz) | AC |
|---|---|---|---|
| **WP1** | `HARD_OFF`-Konstante + Anwendung; `bundle_compression` aus den memory-tragenden Slots entfernen | `backend/application/prompt_slots.py` | AC-1, AC-2 |
| **WP2** | `slot_name`-Durchreichung + UND-Filter aus den **Q1-Schlüsseln** (Workspace/User/`memory.enabled`/`allow_user_opt_out`) | `backend/application/prompt_resolver.py`, `backend/memory/context_builder.py` | AC-3, AC-4 |
| **WP3** | **Q1-Schlüssel** verdrahten: `memory.enabled` (user, Default `true`), `memory.disabled_slots` (global/workspace/user) + `memory.allow_user_opt_out` (Workspace); `WorkspaceMemorySettings` als **Fassade** — **keine Migration für ein eigenes `UserMemorySettings`-Modell** | Q1-Preference-Verdrahtung, `backend/memory/models.py` (Fassade) | AC-4 |
| **WP4** | REST-**Fassade** `GET/PUT /api/v1/memory/me/settings/` über `PreferenceService.set_level`; `memory_injected` in Antworten | `backend/memory/memory_rest.py`, `backend/rest_api/urls.py`, Antwort-Wiring der KI-Services | AC-5, AC-6 |
| **WP5** | Tests: Slot-Matrix (13 Slots × 3 Ebenen), HARD_OFF, Minimum-Logik, Opt-out, Endpoint, Transparenz, Datengrenzen | `backend/application/tests/`, `backend/memory/tests/` | AC-1…AC-6, AC-9 |
| **WP6** | Doku: Injektionsmodell (3 Ebenen, HARD_OFF, Opt-out-Semantik) | `deploy/README.md` o. ä. Backend-Doku | — |
| **WP-D1** | Doku-Absatz Ablagen-Inventar + `EMBEDDING_*`↔`HONCHO_EMBEDDING_*`-Kopplung | Backend-/Deploy-Doku | AC-7 |
| **WP-D2** | Ein-Quellen-Ansatz **oder** Start-Check mit lauter Warnung bei Modell-/Dimensions-Mismatch | `backend/memory/` (Embedding-Config-Pfad) | AC-7 |
| **WP-D3** | Modellwechsel-Schutz: Modellname neben Embeddings persistieren + beim Lesen vergleichen (Design offen, O3) | `backend/persistence/`, `backend/llm_adapter/` | — (O3) |
| **WP-D4** | Ablagen-Inventar „bleibt/wandert/verfällt" je Backend; Entscheidung zu den 57 pgvector-Zeilen (O4) | Doku (+ ggf. Management-Command) | AC-8 |

Reihenfolge: WP1 → WP2 → WP3 → WP4 → WP5/WP6; WP-D parallel (disjunkt). Die Arbeitspakete
**starten mit Annahme (2026-10-26)** — die frühere Klausel „kein WP beginnt vor Annahme" ist
damit erfüllt und entfällt.

---

## Konsequenzen

**Positiv:**

- Fachlich richtige Injektion: Verdichtung und Selbstreferenz sehen nie Memory; nur die
  Konsistenz-/Ranking-Klassen bleiben an — und der Nutzer kann auf Wunsch opt-outen.
- Fail-safe per UND: Die restriktivste Ebene gewinnt; kein „spezifischstes gewinnt"-Fehler.
- Transparenz (`memory_injected`) macht sichtbar, was in Prompts fließt (analog `degraded`).
- **Keine stille Kürzung (ENT-A6 = C):** `<memory>`-Datengrenzen gelten für alle Memory-Blöcke;
  der Budget-Default **0** macht sichtbar, dass nichts unbemerkt abgeschnitten wird.
- **Eine Wahrheit statt zwei (ENT-A5 = A):** Die Schalter liegen als Q1-Schlüssel vor;
  `WorkspaceMemorySettings` bleibt Fassade — kein zweites Settings-Modell.
- #1317 wird nicht „irgendwann" dokumentiert, sondern Teil desselben Schnitts: Inventar,
  Kopplung, lauter Mismatch-Alarm, Entscheidung zu den Waisen-Zeilen.
- Additiv: Defaults = heutiges Verhalten (ohne Nutzer-/Admin-Aktion ändert sich nur
  `bundle_compression` — bewusst).

**Negativ:**

- **Verhaltensänderung an einem Slot** (`bundle_compression` verliert Memory) — gewollt, aber
  sichtbar; braucht sauberen Test inkl. Custom-Template-Fall.
- Neue Q1-Schlüssel + eine neue REST-**Fassade** = mehr Fläche (klein, aber real); **kein**
  eigenes `UserMemorySettings`-Modell und keine Migration dafür (ENT-A5 = A).
- Die Opt-out-Semantik ist durch **ENT-A7 = B** entschieden: bei `allow_user_opt_out=false`
  wird der `user`-Scope nie injiziert. Nutzererwartung ist damit bewusst auf Workspace-/
  Artefakt-Memory begrenzt — das muss die Doku klar sagen (kein offener Punkt mehr).
- WP-D3 (Modellname-Persistenz) ist ein Schema-Thema und verlangt ein sauberes Design
  (Dimension bleibt die Härtegrenze; der Modellname ist ein Weich-Signal) — als offener Punkt
  geführt, nicht in diesem ADR festgelegt.
- Hängen an Nachbar-Entscheiden: Die Ablagen-Inventur (WP-D4) muss den Qdrant-Status aus
  ADR-022 und den Honcho-Status aus ADR-023 abbilden — bei späterem Richtungswechsel
  fortzuschreiben.

---

## Abnahmekriterien

**Given/When/Then, je testbar:**

- [ ] **AC-1 (HARD_OFF):** Given ein Slot aus HARD_OFF (Verdichtung/Selbstreferenz); when ein
      KI-Aufruf ihn rendert (auch mit Custom-Template, das `{memory_context}` nennt); then
      enthält der gerenderte Prompt **keinen** Memory-Inhalt und keinen unaufgelösten
      Platzhalter.
- [ ] **AC-2 (bundle_compression):** Given `bundle_compression`; when gerendert; then kein
      Memory-Block (Vorher/Nachher-Test).
- [ ] **AC-3 (Minimum-Logik):** Given Workspace `enabled=true`, aber `disabled_slots=[X]`; when
      Slot X rendert; then kein Memory — und umgekehrt liefert `workspace.enabled=false` leer,
      selbst wenn user-seitig nichts deaktiviert ist. Ebenso: `memory.enabled=false`
      (user-Ebene) unterdrückt bei `allow_user_opt_out=true` (Default) den **gesamten** Block
      (alle Scopes); bei `allow_user_opt_out=false` erscheint der `user`-Scope **nie** im Block
      (ENT-A7 = B).
- [ ] **AC-4 (Defaults/Q1):** Given keine Q1-Schlüssel gesetzt (Workspace leer, User leer); when
      ein Konsistenz-Slot rendert; then Verhalten wie heute (Memory injiziert), außer HARD_OFF/
      `bundle_compression`.
- [ ] **AC-5 (REST-Fassade):** Given authentifizierter Nutzer; when `GET`/`PUT
      /api/v1/memory/me/settings/`; then liest/schreibt er **nur** seine eigenen Einstellungen
      (kein Fremdzugriff); PUT schreibt die Q1-Schlüssel über `PreferenceService.set_level`
      (keine eigene Settings-Zeile).
- [ ] **AC-6 (Transparenz):** Given ein KI-Aufruf mit Injektion; when die Antwort geprüft wird;
      then enthält sie `memory_injected` mit Slots/Scopes/Count.
- [ ] **AC-7 (Kopplung, WP-D1/D2):** Given `EMBEDDING_MODEL_NAME` wird geändert, während
      `HONCHO_EMBEDDING_MODEL` abweicht; when die App startet/der Check läuft; then **laute
      Warnung** (oder Ableitung aus einer Quelle) — kein stilles Weiterrechnen; die Doku nennt
      die Kopplung.
- [ ] **AC-8 (Inventar, WP-D4):** Given die Doku; when ein Betreiber den Backend-Wechsel plant;
      then findet er je Ablage (pgvector/Honcho/Qdrant) „bleibt/wandert/verfällt" und eine
      Entscheidung/Begründung zu den 57 `mem_memory_entry`-Zeilen.
- [ ] **AC-9 (Datengrenzen, ENT-A6 = C):** Given ein Memory-Block; when er gerendert wird; then
      liegt er in `<memory>`-Datengrenzen (auch `{memory_context}`), und ohne explizit gesetztes
      Budget wird **nichts** gekürzt (Budget-Default 0).

---

## Offene Entscheidungen

1. **O1 — Wirkungsbereich des User-Schalters — durch die UND-Regel des Dokuments beantwortet,
   nicht durch ENT-A7 = B:** Die Entwurfsfrage lautete, ob der Nutzer-Schalter nur auf den
   `user`-Scope oder auf die **Aktivitäten dieses Nutzers** wirkt. Antwort der **UND-Regel**
   (§Kontext Punkt 2): `memory.enabled` (Q1-Schlüssel, **user**-Ebene, Default `true`;
   Formelterm `user.enabled`) gatet den **gesamten** Memory-Block dieses Nutzers — **alle
   Scopes** —, solange `allow_user_opt_out = true` (Default). `user.enabled=false` unterdrückt
   den Block damit vollständig; die Entwurfs-Alternative „Schalter wirkt auf die Aktivitäten
   dieses Nutzers" ist also **die umgesetzte Semantik**, nicht die verworfene. **ENT-A7 = B
   regelt einen anderen Sachverhalt:** Bei `allow_user_opt_out = false` wird der `user`-**Scope**
   nie injiziert; erzwingbar bleiben Workspace-/Artefakt-Memory. ENT-A7 = B entscheidet O1
   damit **nicht** und wird hier nicht als dessen Auflösung zitiert. *Nicht gelöscht, um den
   Entwurfsstand nachvollziehbar zu halten.*
2. **O2 — Konzept-Vendoring:** `MEMORY_INJEKTION_KONZEPT.md` liegt nur auf der QS
   (`/opt/data/reqogniloom-env/qa-beta20/`). Ins Repo übernehmen (z. B. `docs/concepts/`),
   damit der Schnitt ohne QS-Zugriff nachvollziehbar ist.
3. **O3 — Modellwechsel-Schutz-Design (WP-D3):** Wo wird der Modellname persistiert
   (Spalte je Tabelle vs. zentrale Embedding-Metadaten-Tabelle)? Dimension bleibt die
   Härtegrenze; der Modellname ist ein Weich-Signal — Design durch `database-engineer`.
4. **O4 — Die 57 pgvector-Zeilen:** behalten (bei Rückwechsel sichtbar), reaktivieren oder
   löschen? Entscheidung gehört in WP-D4 und hängt am Backend-Pfad (ADR-023).
5. **O5 — Reihenfolge zu D5/D6:** Der Schnitt ist unabhängig lauffähig; die Ablagen-Inventur
   (WP-D4) sollte aber **nach** den nun getroffenen Entscheidungen aus ADR-022/023
   festgeschrieben werden, damit sie keine überholten Backend-Statusse dokumentiert.

---

## Review-Round-Trail

**Governance-Pfad (ENT-X4 = A):** Texte: `documenter`; Review: `concept-reviewer`; Status:
Nutzer. Diese Textfassung (2026-10-26) setzt die Nutzerentscheidung aus
`docs/plans/2026-10-21-entscheidungen-offen.md` §0b um; das `concept-reviewer`-Review ist
**durchgeführt** (Iteration 1 `CHANGES_REQUESTED`, Iteration 2 `APPROVED`, beide 2026-10-26) und
sein Ergebnis ist **in der Trail-Tabelle dieses Abschnitts** protokolliert; eine separate
Protokoll-Datei wurde bewusst nicht angelegt.
**Accepted vor Review — Reihenfolge bewusst gemäß ENT-X2 = A** („Texte anpassen, dann
`accepted`"); das Review ist nachgelagerte Qualitätssicherung, Korrekturen erfolgen als
Git-Amendment.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| `concept-reviewer` | 1 | `CHANGES_REQUESTED` (2026-10-26) | 1 MAJOR (M1: O1 als „durch ENT-A7 = B verworfen" dargestellt, obwohl `user.enabled` laut UND-Formel den gesamten Block gatet und der Q1-Schlüssel `memory.enabled` nirgends etabliert war), 1 MINOR (m2: WP↔AC-Zuordnung — WP6 auf AC-6, WP-D3 auf AC-8), 3 NIT (NIT-3: „Konsequenz bei Annahme" ohne Entscheidungs-Marker; NIT-4: Option B und C nicht abgegrenzt; NIT-5: Trail-Reihenfolge accepted-vor-Review) | M1 behoben (O1 neu gefasst, `memory.enabled` in §Entscheidung Punkt 3, §Kontext Punkt 2, WP2/WP3 und AC-3; Punkt 5 korrigiert); m2 behoben (WP6 `—`, WP-D3 `— (O3)`, WP-D4 `AC-8`); NIT-3/NIT-4/NIT-5 eingearbeitet — in dieser Fassung |
| `concept-reviewer` | 2 | APPROVED (2026-10-26) | — | keine offenen Findings; M1/m2 + NIT-3/NIT-4/NIT-5 bestätigt behoben, keine Regression |

---

*Erstellt durch `concept-specifier` am 2026-10-17 als Entscheidungsvorbereitung D7 der
Bugfix-Runde 5 (`docs/audit/2026-10/bugfix-round-5-plan.md`). Enthält keinen Produktcode,
keine Migration, keine Config-Änderung, keine REQ-Datei-Änderung und keinen Commit.*

*Am 2026-10-26 durch `documenter` an die Nutzerentscheidung (ENT-X2 = A, ENT-A5 = A,
ENT-A6 = C, ENT-A7 = B) angepasst und auf `accepted` gestellt: Die Schalter laufen als
Q1-Schlüssel (kein eigenes `UserMemorySettings`-Modell), die Opt-out-Semantik ist entschieden,
die Datengrenzen gelten für alle Memory-Blöcke. Der Abschnitt „Alternativen" wurde aus dem
vorhandenen Material ergänzt (MADR-Minimal).*
