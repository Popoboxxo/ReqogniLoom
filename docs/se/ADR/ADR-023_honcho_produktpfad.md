---
adr_id: ADR-023
title: "Honcho-Produktpfad — Richtungsentscheidung nach dem Dialektik-Befund (Dream #1336, ungenutzte Fähigkeiten #1337, Pin #1315)"
status: proposed
date: "2026-10-17"
deciders: [user, se-architect]
affected_reqs: [REQ-192]
superseded_by: null
---

# ADR-023: Honcho-Produktpfad — Richtungsentscheidung nach dem Dialektik-Befund

**Status:** proposed (2026-10-17) — **Entscheidung offen**; dieses ADR implementiert nichts.
**Zurückgestellt bis zur Annahme:** **#1336** (Dream) und **#1337** (sechs ungenutzte
Honcho-Fähigkeiten) werden bis zu dieser Entscheidung **nicht umgesetzt**; bei Annahme von
Option B zusätzlich erst nach den benannten Triggern (T1/T2).
**Datum:** 2026-10-17
**Entscheider (vorgeschlagen):** `user`, `se-architect`; **Autor:** `concept-specifier`
(Entscheidungsvorbereitung D6, Branch `docs/round5-decision-prep-d5-d7`, Basis
`origin/main @ 12cce237`; kein Commit).
**Betroffene REQs:** REQ-192 (MCP `memory.ask`, `docs/REQUIREMENTS.md:273-279`).
**Bezug (Issues):** #1336 (Dream konfiguriert, läuft nie), #1337 (6 Fähigkeiten ohne Aufrufer),
#1247 (REGRESSION: `memory.ask` weiter degraded) / #1153 (Dialektik HTTP 500, wieder geöffnet),
#1315 (Honcho `latest` ohne stabilen Tag), #1155 (RFC Langzeitgedächtnis), #1248
(Scope-Mismatch), #1186 (Preflight-Smoke), #1300 (Lern-Kreislauf). Plan:
`docs/audit/2026-10/bugfix-round-5-plan.md` (Entscheidungsspur D6, §6).
**Upstream-Befund:** separat dokumentiert in `docs/audit/2026-10/honcho-dialectic-upstream-note.md`
(Defekt, Evidenz, Pin-Status, Upstream-Stand, nächste Schritte). Dieses ADR entscheidet die
**Richtung**, die Notiz dokumentiert den **Fremddefekt**.
**Vorgänger im Geist:** ADR-020 (Qdrant-Optionalität, `accepted`); Honcho und Qdrant sind
orthogonale Achsen (Derivation/Dialektik vs. ANN-Index, ADR-020 §4).

**Bezug zum Code / zur Kette** (verifiziert am 2026-10-17 im Arbeitsbaum, `origin/main @ 12cce237`):

- `backend/memory/honcho_backend.py` — `HonchoMemoryBackend`; `ask` (ab `:1364`) liefert bei
  Engine-/Transportfehlern `MemoryAnswer(degraded=True)` mit `detail = "engine_error:<ExceptionClass>"`
  (`_degraded_detail`, `:328`) — **laut degradiert, nie still leer** (F9).
- `backend/memory/backends.py` — `MemoryBackend.ask`-Vertrag (`:446`, `:823`) inkl.
  `degraded`/`detail`-Semantik.
- `deploy/docker-compose.yml:1224, :1286, :1409` — **alle drei** Honcho-Services
  (`honcho`, `honcho-deriver`, `honcho-migrate`) tragen denselben Image-Verweis; auf `main`
  heute `ghcr.io/plastic-labs/honcho:latest@sha256:350b778a…` (Digest, aber beweglicher Tag).
- `backend/memory/tests/test_honcho_deploy_contract.py` — Deploy-Guard (Digest-Pin, Shim,
  neun Modul-Header).
- `docs/DEPLOY_RUNBOOK.md` §3.1 — Upstream-Grenze + Eskalationsschritte (3a–3d, Step 1/2);
  `deploy/README.md` (Stale-Image-Abschnitt, Tag+Digest-Pin-Block) — in PR #1414 auf den
  v3.3.0-Pin umgestellt.
- `backend/requirements.txt:169` `honcho-ai==2.5.1` vs. `backend/requirements.lock:66`
  `honcho-ai==2.3.0` — SDK-Drift (im Runbook §3.1 als offen benannt).

**Prüfstand des Pins (W15d):** PR **#1414** (Branch `fix/w15-release-dx`, **offen** am
2026-10-17) pinnt alle drei Services auf `ghcr.io/plastic-labs/honcho:v3.3.0@sha256:5bb8cf7a…`
und zieht Guard/README/Doku mit; auf dem Stand dieses Entwurfs ist der Pin **noch nicht** in
`main`. Der Pin ist Sofortmaßnahme (unabhängig von A/B/C) und ersetzt `latest` als beweglichen Tag.

**Vermerk zur Ablage:** `docs/se/ADR/` ist die gelebte Konvention. Dieses ADR ändert keine
REQ-Datei, keine Kaskaden-Datei und keinen Code; REQ-192 bleibt `Proposed`.

---

## Entscheidungsvorlage

- **Was ist zu entscheiden:** Ob und wie Honcho als **Produktpfad** des Langzeitgedächtnisses
  weiterbetrieben wird — angesichts (a) des Dialektik-Defekts (#1247/#1153, nicht in-repo
  heilbar; Upstream-Grenze), (b) Dream als bezahlter, aber nie ausgeführter Konsolidierung
  (#1336), (c) sechs nachweislich funktionierender Fähigkeiten ohne einen einzigen Aufrufer
  (#1337). Konkret: **Vollausbau jetzt (A) / bedingter Ausbau mit Triggern (B) / Abkündigung (C)**.
- **Empfehlung (Entwurf):** **Option B — bedingter Ausbau.** Sofort und unabhängig: Pin
  (#1414), Upstream-Issue + Notiz, ehrliche Doku, degradierten Pfad laut halten. **Dream
  (#1336) und Fähigkeiten (#1337) erst nach zwei Triggern:** **T1** = der Dialektik-Pfad
  funktioniert end-to-end nachweislich (Header erreicht den Provider; `memory.ask`
  `degraded:false`) via Upstream-Fix, Workaround oder Provider ohne Pflicht-Header; **T2** =
  belegter Produktnutzen (Messplan/Konzept, z. B. aus dem Lern-Kreislauf #1300).
- **Konsequenz bei Annahme (B):** Honcho bleibt **optionales** Backend (Default bleibt
  pgvector); keine Ausbau-Investition auf einem defekten Sollpfad; die Entscheidung über Dream
  und die Fähigkeiten wird auf T1/T2 vertagt und mit Messgrößen versehen.
- **Konsequenz bei Annahme (A):** #1336/#1337 werden sofort geplant; man akzeptiert, dass
  Dialektik vorerst defekt bleibt (nur Upstream-Pfad) und Dream/Fähigkeiten auf ungeprüftem
  Fundament starten.
- **Konsequenz bei Annahme (C):** Rückbau des Honcho-Profils/Backends; REQ-192 wird auf
  pgvector (`graceful degradation`/`unsupported`, AC(3)) zurückgestuft; die Live-Inhalte
  (108 documents/18 peers auf der QS, #1317) verlieren ihren Pfad.
- **Grober Aufwand:** Entscheidung = klein; Sofortmaßnahmen laufen bereits (#1414 offen);
  Dream (B, nach T1/T2) = mittel; Fähigkeiten (B, nach T1/T2) = mittel–groß je Fähigkeit;
  Vollausbau (A) = groß mit Risiko; Abkündigung (C) = mittel–groß (Daten-/Pfad-Rückbau).
- **Offene Punkte:** s. §Offene Entscheidungen (O1–O5).

---

## Kontext

**1. Honcho ist heute ein optionales, aber real genutztes Backend.** Default der Memory-
Schicht ist `pgvector`; die QS-Instanz betreibt `MEMORY_BACKEND=honcho` (Container-Profil
`honcho`: `honcho`, `honcho-deriver`, `honcho-migrate`). #1155 hat Honcho als Engine für
Derivation/Dialektik etabliert; #1156/Plugin-Hälften bauen darauf auf. Damit ist Honcho nicht
„Experiment", sondern ein betriebener Pfad mit Live-Daten.

**2. Der Dialektik-Pfad ist derzeit defekt — und die Grenze liegt upstream.** Auf der QS
konfiguriert (alle fünf `DIALECTIC_LEVELS` + Deriver tragen
`…PROVIDER_PARAMS__EXTRA_HEADERS__x-opencode-session`), dennoch endet der Dialektik-Aufruf in
`400 MissingSessionID` → HTTP 500 → `memory.ask` antwortet
`degraded:true, detail:"engine_error:ServerError"`. Gegenprobe: Der **Deriver-Pfad** mit
identischer Header-Konfiguration kommt durch (Provider antwortet — 429 Quote). Die
verbleibende Lücke (Dialektik wendet `MODEL_CONFIG__OVERRIDES__PROVIDER_PARAMS__EXTRA_HEADERS`
nicht an) liegt **im Vendor-Image** und ist in-repo nicht heilbar (Runbook §3.1; Details und
Belege: Upstream-Notiz). **Sofort-Regel:** Die Degradation bleibt laut (kein stilles leeres
Ergebnis) — sie ist der ehrliche Zustand, kein Bug in der Antwortform.

**3. Dream ist konfiguriert und bezahlt, läuft aber nie (#1336).** `DREAM_ENABLED=true`,
Induktions-/Deduktionsmodelle konfiguriert, `schedule_dream`-Endpunkt vorhanden — aber null
Log-Treffer und kein Scheduler-Task. Folge: Die Working Representation wächst additiv
(5.742 Zeichen, 5 Updates an zwei Tagen), sie **konsolidiert nichts**. Dream ist Honchos
Mechanismus, aus Einzel-Observations verknüpftes Wissen abzuleiten — ohne ihn bleibt die
„memory"-Qualität unter dem, wofür das Backend bezahlt wird.

**4. Sechs Fähigkeiten liefern, das Produkt fragt nicht (#1337).** Live mit 200 geprüft, ohne
Aufrufer in ReqogniLoom: Peer-Suche (semantisch), Workspace-Suche, Peer-Context-Sammelabruf,
Session-Summaries, Honcho-Scopes (7 Endpunkte; die App baut Scope-Trennung stattdessen über
Peer-ID-Strings nach — Ursache des Zugriffsfehlers in #1248), Webhooks. Dazu ungenutzt:
`messages/upload`, `sessions/{s}/clone`, `workspace/chat`, `peers/{p}/sessions`, Card-PUT.

**5. Upstream-Stand.** Eine gezielte Suche im Upstream-Repo (`plastic-labs/honcho`) am
2026-10-17 fand **kein offenes Issue** zum Dialektik-/`extra_headers`-Defekt; das thematisch
verwandte #1171 („OpenCode Go requests fail without a conversation session header") ist
**geschlossen**. Das bedeutet: **Upstream-Issue steht aus** — Sofortmaßnahme, siehe
Upstream-Notiz §Nächste Schritte. (Nebenbei: offenes Upstream-#1358 „Optional time-of-day
window for automatic dreams" ist für #1336 relevant, aber kein Ersatz für den Trigger.)

**6. Threat-Model (4 Fragen, verkürzt; Honcho ist bereits in ADR-020 §4 abgegrenzt):**

1. *Was gebaut?* Ein optionaler Memory-Backend-Pfad (Honcho) neben pgvector; Dialektik als
   LLM-Generierungsfläche (`memory.ask`), Asynchron-Konsolidierung (Deriver/Dream).
2. *Was schiefgeht?* (a) Kostenpflichtige LLM-Calls auf defektem Pfad (bereits real: Ask
   degradiert, Dream verbrennt nichts, weil er nie läuft); (b) Vertrauensverlust durch
   halb-funktionale „Gedächtnis"-Zusagen; (c) Provider-Abhängigkeit (Session-Header) als
   Single Point of Failure; (d) SDK/Image-Drift.
3. *Gegenmaßnahme?* Pin + Guard (Tag+Digest, PR #1414); ehrliche `degraded`-Semantik;
   Upstream-Eskalation; Träger-Entscheidung (dieses ADR): keine Feature-Investition auf
   defektem Pfad; SDK-Drift bereinigen/dokumentieren.
4. *Konsequenz?* Mit Gegenmaßnahmen: Honcho bleibt nutzbar, wo er funktioniert
   (write/query/digest), und ehrlich begrenzt, wo nicht (Dialektik); ohne: Ausbau auf
   wackeligem Fundament.

---

## Alternativen

### Option A: Vollausbau jetzt — Dream aktivieren + Fähigkeiten heben + upstream

**Beschreibung:** #1336 (Dream periodisch anstoßen bzw. konfigurieren, danach Representation-
Qualität messen) und #1337 (Fähigkeiten priorisieren und verdrahten, beginnend mit Suche +
Scopes) werden sofort umgesetzt; der Dialektik-Fix bleibt Upstream.

**Abwägung:** Maximale Produktgeschwindigkeit, falls Honcho ohnehin der Zielpfad ist. Aber:
zwei der drei Ausbaustücke hängen an der Dialektik-Qualität (Scopes/Suche speisen sich aus
demselben Verarbeitungspfad; #1248-Scope-Fehler zeigt den unfertigen Zustand); der Nutzen ist
nicht belegt (kein Messplan); und Ausbau-Investitionen wären schwerer zu rechtfertigen, falls
die Richtung später Richtung C kippt. Risiko, auf einem defekten Sollpfad zu bauen.

**Risiko:** MITTEL–HOCH (Investition ohne belegten Nutzen; Abhängigkeit von Upstream).

### Option B: Bedingter Ausbau mit Triggern (EMPFOHLEN)

**Beschreibung:** Sofort: Pin (#1414), Upstream-Issue + Notiz im Repo, ehrliche Doku
(Runbook/README), SDK-Drift klären, degradierten Pfad laut halten. **Ausbau erst nach T1/T2:**
T1 = Dialektik funktioniert end-to-end nachweislich (Header am Provider belegt; `memory.ask`
nicht degradiert); T2 = belegter Produktnutzen (Messplan/Konzept; Kandidat: Lern-Kreislauf
#1300). Danach: #1336 (Dream), dann #1337 mit priorisierter Reihenfolge
(Semantische Suche → Scopes als Ersatz für Peer-ID-Strings → Summaries/Context) — jeweils mit
Messgröße.

**Abwägung:** Repariert/belegt zuerst, baut danach. Erhält Optionalität (pgvector bleibt
Default), respektiert die Upstream-Grenze, verhindert Investitionen ohne Fundament und ohne
Nutzen. Nachteil: Honchos Stärken bleiben bis T1/T2 ungenutzt — bewusst, weil sie sonst auf
halb funktionierender Basis gebaut würden.

**Risiko:** NIEDRIG–MITTEL (Ausbau-Chance bleibt; Verzögerung ist explizit gewollt).

### Option C: Honcho abkündigen

**Beschreibung:** Honcho-Profil/Backend zurückbauen; pgvector wird der einzige Memory-Pfad;
`memory.ask` degradiert dort vertragskonform (`unsupported`/graceful, REQ-192 AC(3)).

**Abwägung:** Konsistent mit dem pgvector-Default; entfernt die Upstream-Abhängigkeit. Aber:
verwirft betriebene Live-Inhalte (108 documents/18 peers), die bereits geleistete
#1155/#1156-Integration und die Option auf ein stärkeres Langzeitgedächtnis (Dream,
semantische Suche, Scopes) — vor einer belegten Nutzenmessung ist das eine Vorwegnahme.
Sinnvoll nur, wenn T2 dauerhaft negativ bleibt oder der Betrieb sich nicht rechtfertigt.

**Risiko:** MITTEL–GROSS (unumkehrbarer Pfad-/Datenrückbau; Optionalität entfällt).

---

## Entscheidung

**Vorgeschlagene Entscheidung: Option B — bedingter Ausbau. Sofortmaßnahmen jetzt; Dream
(#1336) und Fähigkeiten (#1337) erst nach T1 (Dialektik nachweislich funktionsfähig) und
T2 (belegter Produktnutzen).**

Sofortmaßnahmen (unabhängig von der Restentscheidung, soweit nicht schon laufend):

1. **Pin landen:** PR #1414 (Tag+Digest `v3.3.0`, drei Services, Guard/README/Doku) — ohne
   ihn ist jede Diagnose gegen einen beweglichen `latest`-Build nicht reproduzierbar.
2. **Upstream-Issue stellen** (Repo `plastic-labs/honcho`): Dialektik-Pfad wendet
   `MODEL_CONFIG__OVERRIDES__PROVIDER_PARAMS__EXTRA_HEADERS` nicht an (Repro aus #1153/#1247,
   Deriver-Gegenprobe); Verweis auf Runbook §3.1 Step 1/2. Notiz im Repo:
   `docs/audit/2026-10/honcho-dialectic-upstream-note.md`.
3. **Doku ehrlich halten:** Runbook §3.1 + deploy/README nennen den Zustand (`degraded`,
   nicht still leer); #1153 bleibt offen, bis der Wire-Nachweis existiert.
4. **SDK-Drift klären:** `honcho-ai` in `requirements.txt` (2.5.1) vs. `requirements.lock`
   (2.3.0) — welche Version importiert der laufende Backend-Container? Bereinigen oder
   begründet dokumentieren (Folgeaufgabe).
5. **Nach dem Pin re-testen:** Runbook §3.1 Step 1 gegen `v3.3.0`; wenn grün, Step 2
   (`memory.ask` live). Ergebnis entscheidet T1.

Trigger für den Ausbau:

- **T1 — Funktionsnachweis Dialektik:** `x-opencode-session` erreicht den Provider im
  Dialektik-Pfad; `memory.ask` liefert `degraded:false`. (Upstream-Fix, ein nachgewiesener
  Workaround — z. B. Dialektik-Provider ohne Header-Pflicht — oder Providerwechsel.)
- **T2 — Nutzennachweis:** ein knapper Messplan/Proof (z. B. über #1300: Was verbessert
  konsolidiertes Wissen konkret? Welche Abfragen gewinnen?) liegt vor; Dream wird erst damit
  aktiviert (#1336), die Fähigkeiten (#1337) danach priorisiert.

**Was diese Entscheidung nicht ist:** kein Votum gegen Honcho (Option C bleibt möglich, wenn
T1/T2 dauerhaft scheitern), keine Zusage auf Dream/Features vor den Triggern, und keine
Änderung an REQ-192 (die Anforderung bleibt in beiden Fällen gültig; auf pgvector greift ihr
AC(3)).

---

## Konsequenzen

**Positiv (Option B):**

- Keine Investition auf einem defekten Sollpfad; Upstream-Grenze wird respektiert statt umgangen.
- Reproduzierbare Diagnose durch Tag+Digest-Pin; Guard-Test schützt vor Drift.
- Optionalität bleibt: Honcho bleibt nutzbar (write/query/digest), pgvector bleibt Default.
- Dream/Fähigkeiten werden datengetrieben priorisiert (T2) und messbar gemacht — statt Feature-
  Bau nach Gefühl.
- Die Degradation ist ehrlich (`degraded:true` + `detail`) und wird nach dem Pin gegen `v3.3.0`
  erneut geprüft — der Zustand ist damit befristet diagnostiziert, nicht „vergessen".

**Negativ (Option B):**

- Honchos stärkste Fähigkeiten (Dream-Konsolidierung, Scopes, semantische Suche) bleiben auf
  unbestimmte Zeit ungenutzt — abhängig von einem Fremd-Prozess (Upstream).
- Der Dialektik-Ausfall bleibt sichtbar (kein Fix in-repo möglich) — die Produktzusage
  „Gedächtnis" ist auf der QS-ähnlichen Konfiguration einschränkt.
- Ein zweiter Entscheidungspunkt (T1/T2) muss aktiv nachgehalten werden, sonst entsteht
  faktisch Option C durch Stillstand.

**Positiv (Option A, falls gewählt):** Schnellster Weg zu Dream/Konsolidierung und den
Zusatzfähigkeiten; volle Ausschöpfung des bezahlten Backends — sobald T1/T2 ohnehin positiv
wären.

**Negativ (Option A):** Bau auf defektem Pfad; Nutzen unbelegt; höheres Risiko, Aufwand in
einer Richtung zu verbrennen, die später (C) revidiert wird.

**Positiv (Option C, falls gewählt):** Eine Memory-Wahrheit; keine Upstream-Abhängigkeit;
klare Produktzusage (`memory.ask` als dokumentiertes `unsupported`).

**Negativ (Option C):** Verlust der Live-Inhalte und der Optionalität; Rückbau des
#1155/#1156-Pfads; REQ-192 verliert den produktiven Dialektik-Pfad ersatzlos.

---

## Abnahmekriterien

> Bezogen auf **Entscheidung und Sofortmaßnahmen**, nicht auf Produktcode.

- [ ] **AC-ADR:** Richtung (A/B/C) ist dokumentiert; dieses ADR steht auf `accepted`
      (Freigabe `user`/`se-architect`).
- [ ] **AC-Pin:** Alle drei Honcho-Services tragen denselben `vX.Y.Z@sha256:`-Verweis
      (PR #1414 gemergt); `test_honcho_deploy_contract.py` grün; kein `latest` mehr.
- [ ] **AC-Upstream:** Upstream-Issue ist gestellt und im Repo verlinkt (Notiz-Datei,
      Runbook §3.1); der Retest gegen `v3.3.0` (Step 1/2) ist ausgeführt und dokumentiert.
- [ ] **AC-Degraded:** `memory.ask` liefert im defekten Fall weiterhin `degraded:true` mit
      nicht-leerem `detail` (kein stilles Leer, kein rohes 500) — durch Test/Verhalten belegt.
- [ ] **AC-Trigger (bei B):** #1336 wird erst nach dokumentiertem T1+T2 begonnen; #1337 erst
      danach, mit priorisierter Liste und je einer Messgröße.
- [ ] **AC-SDK:** `honcho-ai`-Drift bereinigt oder als begründete Ausnahme dokumentiert
      (Runbook §3.1).
- [ ] **AC-Status:** #1336/#1337 bleiben bis Annahme + Trigger unangetastet (kein Code).

---

## Offene Entscheidungen

1. **O1 — SDK-Autorität:** Ist `honcho-ai==2.5.1` (requirements.txt) oder `2.3.0`
   (requirements.lock) die importierte Version? Vor jeder weiteren Diagnose feststellen;
   Folgeentscheidung: Lock nachziehen.
2. **O2 — Workaround-Pfad:** Existiert für T1 ein zulässiger Workaround (z. B. ein
   Dialektik-Provider ohne `x-opencode-session`-Pflicht, projekt-/deployment-seitig), oder
   hängt T1 ausschließlich am Upstream? (Im Entwurf offen — keine Lösung vorwegnehmen.)
3. **O3 — Dream-Trigger (#1336):** periodisch (`schedule_dream`) vs. nach N Messages/M Minuten;
   erst nach T2 zu entscheiden, dann mit Messgröße (Representation-Qualität, nicht -Länge).
4. **O4 — Scope-Modell (#1337):** Ob Honchos Scopes die Peer-ID-String-Konstruktion (Ursache
   #1248) strukturell ersetzen, ist vor der Fähigkeiten-Priorisierung zu klären.
5. **O5 — Sichtbarkeit im Produkt:** Ob die Degradation (über `degraded`/`detail` hinaus) einen
   UI-Hinweis erhalten soll („Dialektik derzeit nicht verfügbar") — kleine, eigene Entscheidung.

---

## Review-Round-Trail

**Kein Review durchgeführt.** Dieses ADR ist ein **Entwurf** (Entscheidungsvorbereitung D6);
es liegt kein `concept-reviewer`-/`se-critic`-RVW-Protokoll vor, und es wird keines
vorgetäuscht. Verbindlicher Pfad zur Annahme: `concept-reviewer`-Review (Protokoll unter
`docs/se/reviews/`) → Findings/Iterationen → User-Freigabe → `se-architect` setzt den Status.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| — | — | nicht durchgeführt (Entwurf, 2026-10-17) | — | — |

---

*Erstellt durch `concept-specifier` am 2026-10-17 als Entscheidungsvorbereitung D6 der
Bugfix-Runde 5 (`docs/audit/2026-10/bugfix-round-5-plan.md`). Enthält keinen Produktcode,
keine Migration, keine Config-Änderung, keine REQ-Datei-Änderung und keinen Commit.*
