# Umsetzungsplan: Bugfix-Bundles (post v1.8.0-beta.10)

Stand: 2026-09-11 · Verifikations-Basis: HEAD `e8b8700e` (v1.8.0-beta.10)

Dieses Dokument plant die verbleibenden **offenen Bugs** aus dem Issue-Tracker als
thematische Bundles. Grundlage ist eine Code-Gegenprobe aller offenen Bug-Issues
(Ergebnisse als Kommentar je Issue dokumentiert). Bereits gefixte Issues wurden
geschlossen (18 Stück, siehe Abschnitt „Bereits erledigt").

> Nicht enthalten sind reine Enhancements, RFCs und SE-Methodik-/Audit-Epics
> (z. B. #393, #402, #408, #410, #426, #583, #792, #866, #871, #877–#879). Diese
> werden separat priorisiert, sind aber kein Bugfix-Stoff.

## Priorisierung (Reihenfolge)

**B4 → B1 → B2 → B3 → B5 → B6 → B7**

`B4` zuerst, weil `#911` deploy-kritisch ist (Honcho kann ohne korrekte
Embedding-Base-URL nicht embedden). `B7` (#504) ist unabhängig und kann parallel
laufen.

---

## B4 · AI/Embeddings/Ops — P0

**Issues:** #911, #826, #847, #822, #825

| Issue | Befund | Evidenz |
|---|---|---|
| #911 | Hartkodierter Platzhalter `http://<your-ollama-host>:11434/v1` in beiden Honcho-Services; `/health` meldet trotzdem `ok` | `deploy/docker-compose.yml:603,692`; `memory/honcho_backend.py:308-323`; `reqogniloom/health.py:26-100` |
| #826 | DB-Spalten bleiben `vector(384)`, Modelle 768/1536 nur noch laut (Check `W001`) | `persistence/embedding_dimensions.py:57`; `llm_adapter/checks.py:99-118` |
| #847 | Similar-Search wirft bei fehlendem Embedding `VALIDATION_ERROR` (kein lazy Backfill) | `application/requirement_service.py:790-793`; `SimilarRequirementsPanel.tsx:47-48` |
| #822 | `celery_beat` hard `STATUS_UNKNOWN` (nur erklärender Text) | `admin_ops/health_rest.py:120-140` |
| #825 | Kein unbedingter Empty-Return-Pfad gefunden → Repro nachfordern | `application/ai_derivation_service.py:562-617` |

**Akzeptanz:** #911 URL parametrisiert via `${HONCHO_EMBEDDING_BASE_URL:-…}` +
echter Embedding-Probe im Health-Pfad; #826 konfigurationsgeführte Dimension +
Migration/Backfill über 5 Spalten; #847 lazy Embedding oder sauberer, nicht
blockierender Fehler; #822 Heartbeat-basierter Status.

**Aufwand:** ~5–7 Tage (LLM/Backend/DevOps).

---

## B1 · API-Contract-Konsistenz — P1

**Issues:** #829, #864, #890, #827, #831, #832, #851

| Issue | Befund | Evidenz |
|---|---|---|
| #829 | `TestCaseSerializer` deklariert kein `change_reason`, PATCH reicht es nicht durch → 400 | `rest_api/serializers.py:927-1015`; `views.py:2330-2367` |
| #864 | `test_type` wird gelesen/gepatcht, Create lehnt aber mit 400 ab | `views.py:2250-2264,2351-2352,4203` |
| #890 | Model `description` max 10000 vs. Serializer 20000 | `persistence/models.py:2512`; `serializers.py:1383` |
| #827 | `relevance_score` bis 2.0 (kein Clamp/Normalize) | `application/search_service.py:76-80,565` |
| #831 | Glossary exponiert `lifecycle_status` statt `status` | `serializers.py:1800-1815`; `GlossaryView.tsx:62,260` |
| #832 | Trace-Link-Picker konkateniert ohne Dedup | `CreateTraceLinkDialog/create-trace-link-dialog.tsx:467-513` |
| #851 | Unknown-Field-Rejection nur für Mixin-Entities | `test_baseline_views.py:81-85` |

**Akzeptanz:** einheitliche Feldnamen/Maxlängen, Unknown-Field → 400
flächendeckend, Picker dedupliziert, `relevance_score` definiert skaliert,
`test_type`-Create-Vertrag entschieden.

**Aufwand:** ~2–3 Tage.

---

## B2 · Artefakt-/Attributfelder — P1

**Issues:** #886, #887, #889, #816, #820

| Issue | Befund | Evidenz |
|---|---|---|
| #886 | `ArtifactForm` spreadet `editable:false`-Felder weiter in den Payload | `shared/ArtifactForm/ArtifactForm.tsx:304-327,420` |
| #887 | `custom_fields` fehlen für ChangeRequest/Goal/GlossaryTerm | `serializers.py:1467-1488,1641-1671,1775-1819` |
| #889 | Category create (Enum) vs. edit (Freitext), Server ohne `choices` | `persistence/models.py:1024`; `bootstrap_attribute_definitions.py:407-422,495-518` |
| #816 | `test_type` als First-Class-Feld **und** `artifact_type`-Prefix | `application/test_service.py:122,374` |
| #820 | SQLi-Klartext → 201, XSS → 400 (inkonsistent) | `persistence/free_text.py:98-110`; `rest_api/sanitization.py:70-81` |

**Akzeptanz:** `editable:false` aus Payload entfernt; custom_fields-Roundtrip
für die drei Typen; Category-Validierung konsistent; `test_type` nur noch eine
Repräsentation (+ Migration); Sanitization-Policy entschieden und getestet.

**Abhängigkeit:** #816 überschneidet sich mit #864 (B1) — Reihenfolge abstimmen.

**Aufwand:** ~4–5 Tage.

---

## B3 · Baseline/Governance — P2

**Issues:** #821, #912

| Issue | Befund | Evidenz |
|---|---|---|
| #821 | Nur globaler Gate-Override; kein Per-Blocker-Suppress; Override nur `len>=10` | `application/baseline_facade.py:52,330-343,378-387`; `views.py:3360-3365` |
| #912 | 22× „mandatory_fields … no matching attribute — ignored" im Migrate-Log | `bootstrap_attribute_definitions.py:555-565,646-655`; `presets/registry.py:170,186-194` |

**Akzeptanz:** Per-Blocker-Waiver mit Begründung + Audit; Override-Policy
gehärtet; #912-Warnung gescopt oder `mandatory_fields` bereinigt.

**Aufwand:** ~2–3 Tage.

---

## B5 · UI-Konsistenz & Performance — P2

**Issues:** #802, #873, #596

| Issue | Befund | Evidenz |
|---|---|---|
| #802 | Need/Glossary Inline-Forms vs. `Dialog` bei anderen Entities | `NeedList.tsx:193-208`; `GlossaryView.tsx:514-515` |
| #873 | `ModalDialogBase.tsx` weiter Pseudo-Modal; tote Legacy-Komponente hält es am Leben | `ModalDialogBase.tsx:124-223`; `TestCases/TestcaseList.tsx:15` |
| #596 | `/audit`-Finding-Liste unvirtualisiert (bis 500 Findings) | `Audit/audit-dashboard.tsx:485-495,577-588` |

**Akzeptanz:** einheitliche Dialog-Nutzung; `ModalDialogBase` + Legacy-Liste
entfernt; Audit-Liste virtualisiert/paginiert.

**Aufwand:** ~3–4 Tage.

---

## B6 · Optimistic Locking — P2

**Issue:** #868

Repo-weit kein `ETag`/`If-Match`; Body-Feld `expected_version` → 409 existiert
(`serializers.py:607-640`, `views.py:982-983`), Baseline ist immutable
(`views.py:3515-3520`).

**Akzeptanz:** ETag-Header + `If-Match` (412 bei stale) auf Requirement/TestCase/
Baseline, rückwärtskompatibel zu `expected_version`, Frontend sendet ETag.

**Aufwand:** ~3–5 Tage.

---

## B7 · E2E-Verifikation — P3 (parallel)

**Issue:** #504

`review-workflow.spec.ts:40-47` setzt `acceptance_criteria`; `stakeholder-needs`
nutzt keinen Helper. Ohne echten Shard-2-Lauf nicht entscheidbar.

**Akzeptanz:** isolierter Shard-2-Lauf mit gültigen Seeds, Ergebnis dokumentiert.

**Aufwand:** ~0,5 Tag.

---

## Bereits erledigt (am 2026-09-11 geschlossen)

Verifiziert gegen HEAD und geschlossen: #449, #571, #797, #799, #824, #828,
#830, #845, #846, #848, #850, #867, #869, #870, #872, #875, #884, #885.

Teilweise/unverifiziert kommentiert, aber offen: #504, #596, #821, #825, #826,
#847, #851, #864, #865, #873.

## Verwandte offene Nicht-Bugs (separat priorisieren)

#865 (API-Key-Granularität 2 statt 3 Stufen), #866, #868 (in B6), #871, #877,
#878, #879, #393, #402, #408, #410, #424, #583, #792 · sowie die SE-Methodik-
Audits (#426 u. a.).
