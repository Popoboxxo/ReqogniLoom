---
adr_id: ADR-024
title: "Memory-Injektion je KI-Aktivität/Workspace/User und Memory-Ablagen — ADR-light mit Umsetzungsschnitt (#1339, #1317)"
status: proposed
date: "2026-10-17"
deciders: [user, se-architect]
affected_reqs: [REQ-L2-PT-001, REQ-192]
superseded_by: null
---

# ADR-024: Memory-Injektion je KI-Aktivität/Workspace/User und Memory-Ablagen

**Status:** proposed (2026-10-17) — **Entscheidung offen** (ADR-light); dieses ADR
implementiert nichts. Der untenstehende Umsetzungsschnitt (#1339, #1317-Doku-Teil) startet
erst nach Annahme.
**Datum:** 2026-10-17
**Entscheider (vorgeschlagen):** `user`, `se-architect`; **Autor:** `concept-specifier`
(Entscheidungsvorbereitung D7, Branch `docs/round5-decision-prep-d5-d7`, Basis
`origin/main @ 12cce237`; kein Commit).
**Betroffene REQs:** REQ-L2-PT-001 (Prompt-Slot-/Template-Schicht, von `prompt_slots.py`
und `prompt_resolver.py` selbst als `req_id` geführt — dort lebt die Injektionspolitik);
REQ-192 (Memory-Antwort-/Backend-Pfad; von der Ablagen-/Embedding-Kopplung aus #1317
berührt). *Anmerkung:* Eine eigenständige REQ für die Memory-Injektionspolitik existiert
nicht (Stand 2026-10-17); analog ADR-021/REQ-194 empfiehlt sich eine REQ-Neuanlage im
`requirements`-Prozess (Folgeaufgabe, nicht Teil dieses Entwurfs).
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

- **Was ist zu entscheiden:** (1) Ob die Memory-Injektion das im Konzept (#1339)
  vorgeschlagene **Drei-Ebenen-Modell mit Minimum-Logik** erhält (System-Policy ⊂
  Workspace ⊂ User, fail-safe per UND); (2) die **Opt-out-Semantik** des neuen
  Nutzer-Schalters; (3) ob und wie der #1317-Doku-Teil (Ablagen-Inventar, Embedding-
  Kopplung) als Teil desselben Schnitts umgesetzt wird.
- **Empfehlung (Entwurf):** Drei-Ebenen-Modell **übernehmen** (Minimum gewinnt); HARD_OFF als
  Code-Konstante für Verdichtung + Selbstreferenz; `bundle_compression` verliert den
  Memory-Block; Nutzer-Schalter wirkt auf die **Aktivitäten dieses Nutzers** (nicht nur seinen
  `user`-Scope) — als Entscheidungspunkt O1 markiert; Transparenzfeld `memory_injected` in den
  Antworten; #1317 als Doku-/Härtungsteil desselben Schnitts (WP-D).
- **Konsequenz bei Annahme:** Umsetzung additiv mit **Defaults = heutigem Verhalten** (nur
  HARD_OFF und `bundle_compression` ändern die Injektion bewusst); neue Modelle/Migrationen
  (workspace `disabled_slots`/`allow_user_opt_out`, `UserMemorySettings`); neue
  REST-Route; Doku.
- **Konsequenz bei Ablehnung:** Die pauschale Injektion bleibt; Verdichtungs-Slots wie
  `bundle_compression` sehen weiteres Fremdwissen; es gibt weiterhin keinen Nutzer-Schalter.
- **Grober Aufwand:** ADR = klein; Schnitt = mittel (2 Modelle/Migrationen, Resolver-Filter,
  1 REST-Route, Tests, Doku; #1317-Teil davon überwiegend Doku + kleiner Startup-Check).
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
Rückbau nach ADR-022 entsprechend fortgeschrieben).

---

## Entscheidung (Vorschlag, ADR-light)

**Vorgeschlagene Entscheidung: Drei-Ebenen-Minimum-Modell gemäß #1339 übernehmen; `#1317`
als Doku-/Härtungsteil desselben Schnitts umsetzen.**

1. **HARD_OFF (Code-Konstante)** für die Klassen *Verdichtung* (`interview.transcript_summary`,
   `bundle_compression`) und *Selbstreferenz* (`memory.extract`). Für
   `interview.transcript_summary`/`memory.extract` ist das heute faktisch bereits so (Deklaration
   entfernt bzw. bewusst ohne) — HARD_OFF macht es **erzwingbar** (Regressionsschutz auch für
   Custom-Templates und künftige Slots). Für `bundle_compression` **ändert** es das Verhalten:
   der Slot verliert den Memory-Block (bewusste Verhaltensänderung, im Test abzusichern; kein
   unaufgelöster `{memory_context}`-Platzhalter im gerenderten Prompt).
2. **Workspace-Ebene:** `disabled_slots` (Liste von Slot-Namen) + `allow_user_opt_out`
   (Default **True** — ohne Nutzer-Settings-Zeile bleibt das Verhalten unverändert) auf
   `WorkspaceMemorySettings` (+ Migration).
3. **User-Ebene (neu):** `UserMemorySettings` (tenant-scoped, one row per user; fehlende
   Zeile = `enabled=True`), Felder `enabled` + `disabled_slots` (+ Migration).
4. **Filterlogik:** `slot_name` wird von `resolve_and_render` über `_auto_memory_context` bis
   `build_memory_context(..., slot_name=None)` durchgereicht; die UND-Regel aus §2 wird an
   **einer** Stelle ausgewertet (Default-Verhalten ohne Settings = heutiges Verhalten,
   abzüglich HARD_OFF/bundle_compression).
5. **Opt-out-Semantik (Entscheidungspunkt O1):** Empfehlung — der Nutzer-Schalter wirkt auf
   die Aktivitäten **dieses Nutzers** (seine Prompts erhalten keinen Block), nicht nur auf
   seinen `user`-Scope; Begründung im Konzept („Der Nutzer denkt in ‚ich will das nicht'",
   #1339). Final durch die Entscheider festzulegen.
6. **REST:** `GET/PUT /api/v1/memory/me/settings/` (eigene Person, analog `MemorySelfServiceView`;
   PUT erzeugt die Zeile lazy).
7. **Transparenz:** Antworten KI-führender Endpunkte/MCP-Tools tragen `memory_injected:
   {slots, scopes, count}` (analog `degraded`) — sichtbar, welcher Kontext injiziert wurde.
8. **#1317-Teil (WP-D):** Kopplung dokumentieren (`EMBEDDING_MODEL_NAME`-Wechsel zieht
   `HONCHO_EMBEDDING_MODEL` mit); **eine Quelle oder lauter Check** (Ableitung der
   `HONCHO_EMBEDDING_*` aus `EMBEDDING_*` **oder** Startup-Vergleich von Modell + Dimension mit
   lauter Warnung); Modellwechsel-Schutz (Modellname neben Embeddings persistieren und beim
   Lesen vergleichen — Design offen, O3); **Ablagen-Inventar** in der Doku (welche Backends,
   was liegt wo, was passiert beim Wechsel: bleibt/wandert/verfällt; die 57
   `mem_memory_entry`-Zeilen benennen und entscheiden — O4).

**Was diese Entscheidung nicht ist:** kein Honcho-/Qdrant-Richtungsentscheid (ADR-022/023);
keine Änderung an Defaults ohne Nutzeraktion; kein neues LLM-Feature (reine Politik +
Sichtbarkeit + Doku).

---

## Umsetzungsschnitt (Arbeitspakete, nach Annahme)

| WP | Inhalt | Dateien (Referenz) | AC |
|---|---|---|---|
| **WP1** | `HARD_OFF`-Konstante + Anwendung; `bundle_compression` aus den memory-tragenden Slots entfernen | `backend/application/prompt_slots.py` | AC-1, AC-2 |
| **WP2** | `slot_name`-Durchreichung + UND-Filter (Workspace/User/allow_user_opt_out) | `backend/application/prompt_resolver.py`, `backend/memory/context_builder.py` | AC-3, AC-4 |
| **WP3** | Modelle + Migration: `WorkspaceMemorySettings.disabled_slots`/`allow_user_opt_out`; `UserMemorySettings` | `backend/memory/models.py`, neue Migration | AC-4 |
| **WP4** | REST `GET/PUT /api/v1/memory/me/settings/`; `memory_injected` in Antworten | `backend/memory/memory_rest.py`, `backend/rest_api/urls.py`, Antwort-Wiring der KI-Services | AC-5, AC-6 |
| **WP5** | Tests: Slot-Matrix (13 Slots × 3 Ebenen), HARD_OFF, Minimum-Logik, Opt-out, Endpoint, Transparenz | `backend/application/tests/`, `backend/memory/tests/` | AC-1…AC-6 |
| **WP6** | Doku: Injektionsmodell (3 Ebenen, HARD_OFF, Opt-out-Semantik) | `deploy/README.md` o. ä. Backend-Doku | AC-6 |
| **WP-D1** | Doku-Absatz Ablagen-Inventar + `EMBEDDING_*`↔`HONCHO_EMBEDDING_*`-Kopplung | Backend-/Deploy-Doku | AC-7 |
| **WP-D2** | Ein-Quellen-Ansatz **oder** Start-Check mit lauter Warnung bei Modell-/Dimensions-Mismatch | `backend/memory/` (Embedding-Config-Pfad) | AC-7 |
| **WP-D3** | Modellwechsel-Schutz: Modellname neben Embeddings persistieren + beim Lesen vergleichen (Design offen, O3) | `backend/persistence/`, `backend/llm_adapter/` | AC-8 |
| **WP-D4** | Ablagen-Inventar „bleibt/wandert/verfällt" je Backend; Entscheidung zu den 57 pgvector-Zeilen (O4) | Doku (+ ggf. Management-Command) | AC-8 |

Reihenfolge: WP1 → WP2 → WP3 → WP4 → WP5/WP6; WP-D parallel (disjunkt). Kein WP beginnt vor
Annahme dieses ADR.

---

## Konsequenzen

**Positiv:**

- Fachlich richtige Injektion: Verdichtung und Selbstreferenz sehen nie Memory; nur die
  Konsistenz-/Ranking-Klassen bleiben an — und der Nutzer kann auf Wunsch opt-outen.
- Fail-safe per UND: Die restriktivste Ebene gewinnt; kein „spezifischstes gewinnt"-Fehler.
- Transparenz (`memory_injected`) macht sichtbar, was in Prompts fließt (analog `degraded`).
- #1317 wird nicht „irgendwann" dokumentiert, sondern Teil desselben Schnitts: Inventar,
  Kopplung, lauter Mismatch-Alarm, Entscheidung zu den Waisen-Zeilen.
- Additiv: Defaults = heutiges Verhalten (ohne Nutzer-/Admin-Aktion ändert sich nur
  `bundle_compression` — bewusst).

**Negativ:**

- **Verhaltensänderung an einem Slot** (`bundle_compression` verliert Memory) — gewollt, aber
  sichtbar; braucht sauberen Test inkl. Custom-Template-Fall.
- Neue Modelle/Migrationen + eine neue REST-Route = mehr Fläche (klein, aber real).
- Die Opt-out-Semantik (O1) muss entschieden werden; die „falsche" Wahl (nur user-Scope statt
  Nutzer-Aktivitäten) würde Nutzererwartung und Implementierung auseinanderlaufen lassen.
- WP-D3 (Modellname-Persistenz) ist ein Schema-Thema und verlangt ein sauberes Design
  (Dimension bleibt die Härtegrenze; der Modellname ist ein Weich-Signal) — als offener Punkt
  geführt, nicht im Entwurf festgelegt.
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
      selbst wenn User-Settings `enabled=true`.
- [ ] **AC-4 (Defaults):** Given keine Settings-Zeilen (Workspace leer, User leer); when ein
      Konsistenz-Slot rendert; then Verhalten wie heute (Memory injiziert), außer HARD_OFF/
      `bundle_compression`.
- [ ] **AC-5 (REST):** Given authentifizierter Nutzer; when `GET`/`PUT /api/v1/memory/me/settings/`;
      then liest/schreibt er **nur** seine eigenen Settings (kein Fremdzugriff), PUT legt die
      Zeile lazy an.
- [ ] **AC-6 (Transparenz):** Given ein KI-Aufruf mit Injektion; when die Antwort geprüft wird;
      then enthält sie `memory_injected` mit Slots/Scopes/Count.
- [ ] **AC-7 (Kopplung, WP-D1/D2):** Given `EMBEDDING_MODEL_NAME` wird geändert, während
      `HONCHO_EMBEDDING_MODEL` abweicht; when die App startet/der Check läuft; then **laute
      Warnung** (oder Ableitung aus einer Quelle) — kein stilles Weiterrechnen; die Doku nennt
      die Kopplung.
- [ ] **AC-8 (Inventar, WP-D4):** Given die Doku; when ein Betreiber den Backend-Wechsel plant;
      then findet er je Ablage (pgvector/Honcho/Qdrant) „bleibt/wandert/verfällt" und eine
      Entscheidung/Begründung zu den 57 `mem_memory_entry`-Zeilen.

---

## Offene Entscheidungen

1. **O1 — Opt-out-Semantik (final):** Wirkt der Nutzer-Schalter auf die Aktivitäten dieses
   Nutzers (Empfehlung des Entwurfs, #1339) oder nur auf seinen `user`-Scope?
2. **O2 — Konzept-Vendoring:** `MEMORY_INJEKTION_KONZEPT.md` liegt nur auf der QS
   (`/opt/data/reqogniloom-env/qa-beta20/`). Ins Repo übernehmen (z. B. `docs/concepts/`),
   damit der Schnitt ohne QS-Zugriff nachvollziehbar ist.
3. **O3 — Modellwechsel-Schutz-Design (WP-D3):** Wo wird der Modellname persistiert
   (Spalte je Tabelle vs. zentrale Embedding-Metadaten-Tabelle)? Dimension bleibt die
   Härtegrenze; der Modellname ist ein Weich-Signal — Design durch `database-engineer`.
4. **O4 — Die 57 pgvector-Zeilen:** behalten (bei Rückwechsel sichtbar), reaktivieren oder
   löschen? Entscheidung gehört in WP-D4 und hängt am Backend-Pfad (ADR-023).
5. **O5 — Reihenfolge zu D5/D6:** Der Schnitt ist unabhängig lauffähig; die Ablagen-Inventur
   (WP-D4) sollte aber **nach** ADR-022/023 festgeschrieben werden, damit sie keine
   überholten Backend-Statusse dokumentiert.

---

## Review-Round-Trail

**Kein Review durchgeführt.** Dieses ADR ist ein **Entwurf** (ADR-light, Entscheidungsvorbereitung
D7); es liegt kein `concept-reviewer`-/`se-critic`-RVW-Protokoll vor, und es wird keines
vorgetäuscht. Verbindlicher Pfad zur Annahme: `concept-reviewer`-Review (Protokoll unter
`docs/se/reviews/`) → Findings/Iterationen → User-Freigabe → `se-architect` setzt den Status.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| — | — | nicht durchgeführt (Entwurf, 2026-10-17) | — | — |

---

*Erstellt durch `concept-specifier` am 2026-10-17 als Entscheidungsvorbereitung D7 der
Bugfix-Runde 5 (`docs/audit/2026-10/bugfix-round-5-plan.md`). Enthält keinen Produktcode,
keine Migration, keine Config-Änderung, keine REQ-Datei-Änderung und keinen Commit.*
