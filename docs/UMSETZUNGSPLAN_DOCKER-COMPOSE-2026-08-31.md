# Umsetzungsplan: Docker-Compose-Optimierung & Backup-Integration

**Datum:** 2026-08-31
**Ausgangspunkt:** GitHub Issue [#792](https://github.com/Popoboxxo/ReqogniLoom/issues/792) — "[RFC] System-Wide Improvements: Deployment, Security, Operations & DX"
**Auslöser:** Produktions-Incident vom 2026-08-31 (QS/PROD-Port-Verwechslung, Datenverlust). RFC wurde von einer fremden KI verfasst und enthält teils veraltete/falsche Annahmen über den Ist-Stand — siehe Abschnitt "Ist-Stand-Check" unten.
**Prozess:** Kompakte Task-Liste je Sub-Projekt (kein formales Spec-Dokument), abgestimmt mit dem Projektverantwortlichen per Brainstorming-Dialog. Passt zum DoD-Preset `rapid-prototyping` dieses Projekts.
**Priorität lt. Nutzer:** Backup, Named Volumes, saubere Env-Handhabung bei Neuinstallation, Admin-User/Passwort via ENV. Named Volumes und Admin-Creds sind bereits erledigt (siehe unten) — Fokus liegt daher auf Backup-Härtung und Install-Sauberkeit.
**Best-Practice-Check (2026-08-31):** Plan gegen aktuelle Docker-Compose-Best-Practices per Web-Recherche geprüft, auf expliziten Nutzerwunsch ("so simpel wie möglich"). Ergebnis: YAML-Anchors und `profiles` für optionale Services sind der offiziell dokumentierte Weg (docs.docker.com/reference/compose-file/fragments/) und bleiben wie geplant. Ein Punkt aus dem RFC war falsch und wurde korrigiert — siehe Sub-Projekt A.

---

## Ist-Stand-Check (vor Planung verifiziert)

| RFC-Punkt | Behauptung der fremden KI | Tatsächlicher Ist-Stand | Bewertung |
|---|---|---|---|
| Named Volumes | (implizit fehlend) | 3 Named Volumes vorhanden: `postgres_data`, `postgres_backup_data`, `backend_dr_backups` | ✅ bereits erledigt |
| #9 Admin-Creds via ENV | "muss manuell erstellt werden" | `SYSTEM_ADMIN_USERNAME`/`_EMAIL`/`_PASSWORD` bereits ENV-basiert, idempotent (create-only) via `post_migrate`-Receiver (`backend/application/self_init.py`) | ✅ bereits erledigt |
| #3 Backup | "Backup ist over-engineered, kein Django-Command" | Backup läuft bereits als Sidecar (`postgres-backup`) mit `backend/scripts/backup_postgres.sh`, Retention, gzip-Dump. Funktioniert, ist aber nicht verifiziert/alarmiert. | 🟡 teilweise — härten statt neu bauen |
| #6 `.env.example` | "fehlt komplett" | Existiert bereits, 300+ Zeilen, gut kommentiert | 🟡 teilweise — Lücken schließen |
| #4 Frontend tmpfs/user:root | "muss manuell konfiguriert werden" | Bereits Default in `docker-compose.yml` (non-root Image, `tmpfs` gesetzt) | ✅ bereits erledigt |
| #14 RLS: App-User muss Superuser sein | "RLS blockiert Non-Superuser" | Falsch. `DB_APP_USER` ist bewusst `NOSUPERUSER` (Migration `0048_app_role.py`, ADR-03). RLS ist genau so konzipiert, dass es *ohne* Superuser funktioniert. | ❌ verworfen — RFC irrt |
| Compose-Image-Tags | (nicht erwähnt) | `docker-compose.yml` zeigt `1.7.0`, aktueller Stand ist `1.8.0-beta.5` | 🐛 echter Bug, on top gefunden |
| #5 Honcho Single-Stack | "muss gemergt werden" | ENV-Variablen (`MEMORY_BACKEND`, `HONCHO_BASE_URL`, `HONCHO_API_KEY`) bereits vorbereitet. UI zur Konfiguration/Anzeige (`MemorySystemSettingsSection.tsx`) existiert bereits vollständig. Es fehlt nur die optionale Compose-Einbindung des Honcho-Service selbst. | 🟡 teilweise — nur Compose-Wiring fehlt |
| #15 FIELD_ENCRYPTION_KEY Auto-Gen | "muss automatisch generiert und in Datei persistiert werden" | Aktuell Pflichtfeld ohne Default (`config("FIELD_ENCRYPTION_KEY")`, crasht ohne). Auto-Gen + Datei-Persistenz ist riskant: Volume-Verlust = Daten dauerhaft unrettbar verschlüsselt. **Entscheidung des Nutzers: Pflicht bleibt, nur besser dokumentiert/generiert bei Erstsetup.** | 🔴 bewusst nicht wie RFC vorgeschlagen umgesetzt |

Reale, ungeprüfte Duplikation bestätigt: `backend`, `celery`, `celery-beat` teilen sich fast identische `environment`-Blöcke (~20 Zeilen je Service) — YAML-Anchors sind hier ein echter Gewinn.

---

## Sub-Projekte

Der volle Umfang aus Issue #792 (18 Einzelpunkte) wurde auf Wunsch des Nutzers vollständig übernommen, aber in sechs unabhängig umsetzbare, sequentiell abzuarbeitende Sub-Projekte zerlegt. Jedes Sub-Projekt bekommt einen eigenen Branch und einen eigenen PR (Conventional Commits, `feat/`, `fix/`, `refactor/`, `chore/`, `docs/` je nach Art — nie direkt auf `main`, siehe `.claude/rules/branch-guard.md`). Git-Mutationen (Branch, Commit, Push) laufen über den `git`-Agent, nicht direkt im Main-Chat.

**Reihenfolge:** A → B → C → D → E → F (vom Nutzer bestätigt).

### A — Compose-Kern (`refactor/compose-cleanup`)

RFC-Punkte: #1, #2 (revidiert), #4 (bereits erledigt), #18, + Image-Tag-Bugfix

> **Korrektur nach Best-Practice-Check:** RFC-Punkt #2 (Migrate → Entrypoint) ist **kein** Best Practice, sondern erhöht das Risiko. Mehrere unabhängige Quellen (u. a. pythonspeed.com "Decoupling database migrations from server startup") empfehlen einen dedizierten Migrate-Service mit `condition: service_completed_successfully`, gerade um Race Conditions bei mehreren Replicas zu vermeiden. Das bestehende Setup macht das schon richtig — inkl. sauberem, einmaligem Admin-Self-Init. **Migrate bleibt eigener Service.** Nur die Duplikation wird per Anchor entfernt.

- [ ] `x-logging`-Anchor: einheitlicher `json-file`-Logging-Block für alle 8 Services
- [ ] `x-django-env`-Anchor: gemeinsamer Environment-Block für `backend`/`celery`/`celery-beat`/`migrate` (DB-Connection, Redis, LLM-Provider-Defaults); service-spezifische Overrides (z. B. `migrate`s `DB_STATEMENT_TIMEOUT_MS`, `SYSTEM_ADMIN_*`) bleiben lokal im jeweiligen Service
- [ ] Image-Tags von `1.7.0` auf aktuellen Stand (`1.8.0-beta.5` bzw. env-steuerbar via `${IMAGE_TAG:-...}`) korrigieren — in `backend`, `migrate`, `celery`, `celery-beat`, `frontend`
- [ ] `migrate`-Service **bleibt bestehen** (Best Practice, siehe oben) — keine Änderung an der Architektur, nur Anchor-Anwendung
- [ ] `docker-compose.override.yml`-Warnung: Entrypoint prüft beim Start, ob die Datei existiert, und gibt eine deutliche Warnung aus (kein automatisches Verschieben — nur Hinweis)
- [ ] Verifikation: `docker compose config` validiert fehlerfrei, Stack hochfahren, alle Healthchecks grün, Migration läuft weiterhin genau einmal beim Deploy über den dedizierten Service

### B — Install-Sauberkeit (`chore/setup-script`)

RFC-Punkte: #6 (Rest), #7, #8, #12

- [ ] `setup.sh`: `.env` aus `.env.example` erzeugen (falls nicht vorhanden), Secrets generieren (`SECRET_KEY`, `AUTH_JWT_SECRET`, `DB_PASSWORD`, `DB_APP_PASSWORD`, `API_KEY_PEPPER`), Named Volumes anlegen, Postgres hochfahren + warten, Migration anstoßen
- [ ] Port-Check vor dem Start: prüft `BACKEND_PORT`/`FRONTEND_PORT` auf Kollisionen, bricht mit klarer Fehlermeldung ab statt kryptischem Docker-Fehler
- [ ] `.env.example`: Diff gegen tatsächlich in `settings.py` gelesene `config(...)`-Variablen, fehlende Variablen ergänzen
- [ ] README: Systemanforderungen-Tabelle (Memory/CPU je Service) — Werte aus den bereits in `docker-compose.yml` gesetzten `deploy.resources.limits` übernehmen, nicht neu erfinden

### C — Secrets-Bootstrap (`docs/encryption-key-warning`)

RFC-Punkt: #15 (abgewandelt — siehe Ist-Stand-Check)

- [ ] Keine Auto-Generierung mit Datei-Persistenz (Nutzer-Entscheidung, Datenverlustrisiko)
- [ ] `setup.sh` (Sub-Projekt B) generiert `FIELD_ENCRYPTION_KEY` einmalig beim allerersten `.env`-Erzeugen und gibt einen unübersehbaren Warnhinweis aus ("Sichere diesen Key außerhalb des Volumes — ohne ihn sind verschlüsselte Felder für immer unlesbar")
- [ ] README/CLAUDE.md: Abschnitt "Was passiert, wenn `FIELD_ENCRYPTION_KEY` verloren geht" (Konsequenzen, Backup-Empfehlung)

### D — Backup-Härtung (`fix/backup-hardening`)

RFC-Punkte: #3 (abgewandelt), #13, #17

- [ ] `backup_postgres.sh`: Verify-Step nach jedem Dump (z. B. `gzip -t` auf das Ergebnis)
- [ ] Fehlschlag beim Dump oder Verify → sichtbarer Exit-Code ungleich 0 in `docker logs`, optionaler Alert-Hook (Webhook, falls `BACKUP_ALERT_WEBHOOK_URL` gesetzt ist)
- [ ] Pre-Wipe-Snapshot-Helper: Skript, das vor destruktiven Operationen (`docker compose down -v`) automatisch einen Snapshot zieht bzw. explizit warnt
- [ ] Django-Admin-Action "Backup erstellen" — nutzt den bestehenden Backup-Mechanismus, kein neuer Codepfad
- [ ] Restore-Doku im README: Schritt-für-Schritt-Anleitung (`gunzip -c ... | psql ...`, existiert als Kommentar in `docker-compose.yml`, muss ins README)

### E — Healthcheck-Erweiterung (`feat/healthcheck-db-redis`)

RFC-Punkt: #16 (schlanker als vorgeschlagen — kein neues Package, da unnötige Abhängigkeit)

- [ ] `/health/`-Endpoint erweitern: zusätzlich zu "Prozess läuft" auch DB-Check (`SELECT 1`) und Redis-Check (`PING`)
- [ ] Bestehender Compose-Healthcheck (`curl -f http://localhost:8000/health/`) bleibt unverändert, wird aber aussagekräftiger

### F — Honcho-Compose-Profile (`feat/honcho-compose-profile`)

RFC-Punkte: #5, #10, #11 (stark reduziert — UI und ENV-Grundgerüst existieren bereits)

- [ ] `honcho`, `honcho-postgres`, `honcho-redis` als Services in `docker-compose.yml`, alle mit `profiles: ["honcho"]`
- [ ] Default-Verhalten (`docker compose up`) bleibt ohne Honcho — `MEMORY_BACKEND=pgvector` bleibt Default
- [ ] `docker compose --profile honcho up` startet den Honcho-Stack zusätzlich mit
- [ ] Envs (`HONCHO_DB_PASSWORD`, Embedding-/LLM-Pinning) sind in `.env.example` bereits vorbereitet — nur an den neuen Compose-Service anbinden
- [ ] Kein neuer UI-Code nötig — `MemorySystemSettingsSection.tsx` deckt Backend-Auswahl und Verbindungsstatus bereits ab; nur End-to-End-Test der Verbindung (bundled und extern gehostet)

---

## Offene Punkte / bewusst nicht übernommen

- **RFC #14** (App-User muss Superuser für RLS sein): verworfen, siehe Ist-Stand-Check. Architektur ist korrekt so wie sie ist.
- **RFC #15** (Auto-Gen `FIELD_ENCRYPTION_KEY` in Datei): abgelehnt zugunsten von Sub-Projekt C (Pflicht bleibt, nur besser dokumentiert).

## Nächster Schritt

Start mit Sub-Projekt A (Compose-Kern) nach Freigabe.
