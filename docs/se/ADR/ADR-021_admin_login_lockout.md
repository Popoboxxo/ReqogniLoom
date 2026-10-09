---
adr_id: ADR-021
title: "Login-Lockout für den Django-Admin (Brute-Force-Schutz) — DB-gestützte Fehlversuchs-Sperre statt django-axes"
status: proposed
date: "2026-10-09"
deciders: [user, senior-developer]
affected_reqs: [SEC-04, AUD-2026-09-223, AUD-2026-09-N1]
superseded_by: null
---

# ADR-021: Login-Lockout für den Django-Admin (Brute-Force-Schutz) — DB-gestützte Fehlversuchs-Sperre statt django-axes

**Status:** proposed (2026-10-09) — Dokumentation einer **bereits getroffenen** (D3) und
**bereits ausgelieferten** Entscheidung. Nicht angenommen: es hat noch kein
`concept-reviewer`-Review stattgefunden (s. §Review-Round-Trail).
**Datum:** 2026-10-09
**Entscheider (vorgeschlagen):** `user`, `senior-developer`; **Autor:** `senior-developer`.

**Betroffene REQs:** SEC-04 (Epic „Security & Authorization",
`docs/audit/2026-09/SEC-04_privileged_key_revocation.md`), Finding AUD-2026-09-223
(`docs/audit/2026-09/AUDIT_SECURITY.md:47`, **HIGH**, CVSS 7.1, CWE-307/489) und AUD-2026-09-N1
(ebd., SEC-04 §1). Diese Bezeichner sind Audit-/Findings-IDs, keine REQ-L*-Dateien; dieses ADR
ändert **keine** REQ-Datei.

**Bezug:** Issue #1135 (Leit-Issue; Entscheidung D3 im Kommentar 2026-10-04 — *pre-verified by
orchestrator research, nicht selbst gelesen*), PR #1172 (Merge-Commit `ee98e592`), Commit
`a70e88a9` (feat(auth): add DB-backed brute-force lockout for admin login),
`CHANGELOG.md:82-83` (Eintrag „D3"). HARD STOP:
`docs/audit/2026-09/SEC-04_privileged_key_revocation.md` §7 („Brute-Force-Schutz für
/admin/login/ … nicht umgesetzt"). Dependency-Sign-off-Gate:
`docs/audit/2026-10/bugfix-round-plan.md:81`. Separater Folge-Slot:
`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:221` (ADR-Kandidat *ii*, Workspace vs.
Tenant) sowie SEC-04-Dokument `:66-70` (ADR-011 Punkt 6 → eigene Ownership-/Governance-ADR).
LAN-Framing (Self-hosted On-Prem, kein TLS im gebündelten Stack) — *pre-verified by
orchestrator research*.

**Bezug zum Code** (alle `file:line` vom Autor am 2026-10-09 im Branch
`feat/1135-admin-lockout-decision` gelesen):

- Modell `AdminLoginLockout`: `backend/auth_tenancy/models.py:780-869` — Tabelle
  `at_admin_login_lockout` (`:842`), Unique-Key `(client_ip, username_digest)`
  (`uq_admin_lockout_ip_user`, `:843-848`), SHA-256-Username-Digest, 32 Hex-Zeichen
  (`:824-827`), Felder `failure_count`/`first_failure_at`/`last_failure_at`/`locked_until`
  (`:829-839`), Indizes `idx_admin_lockout_last`/`idx_admin_lockout_locked_until` (`:849-860`),
  Scope GLOBAL ohne Tenant-FK (`:804-812`), absichtlich **nicht** im Django-Admin registriert
  (`:865`).
- Evaluator: `backend/auth_tenancy/admin_lockout.py` — IP-Auflösung `REMOTE_ADDR` default, XFF
  nur bei gesetztem `NUM_PROXIES` (`:97-110`, `:161-178`), `register_failure` (`:392`), Fenster
  verankert auf `first_failure_at` (`:395-397`), WARNING beim Sperren (`:400`), fail-open bei
  DB-Fehler mit WARNING-Log (`:289-308`, `:338`, `:450`, `:473-482`).
- Gate: `backend/auth_tenancy/admin_login.py` — `admin.site.login_form`-Swap (`:187-198`,
  Warnung bei fremd vorgesetztem `login_form` `:189-201`), Receiver `user_login_failed`
  (`:141`) / `user_logged_in` (`:159`), Pfad-Scope auf `admin:login` (`:88`), Pre-Auth-Check im
  `clean()` (`:102-107`).
- Settings: `backend/reqogniloom/settings.py:557-582`
  (`ADMIN_LOGIN_LOCKOUT_ENABLED` / `_THRESHOLD=5` / `_WINDOW_SECONDS=900` /
  `_DURATION_SECONDS=900`, env-overridable). Gegenprobe DRF: `backend/rest_api/throttling.py:382`
  (`LoginRateThrottle`) / `:395` (`LoginIpRateThrottle`), gebunden an `LoginView`
  (`backend/rest_api/auth_views.py:210-233`, `throttle_classes` `:233`), Raten `login` 10/min
  prod (`settings.py:520-521`), `login_ip` 60/min prod (`:526-527`), failure-only (`:649-650`),
  `DEFAULT_THROTTLE_RATES` (`:646-663`); Route `backend/reqogniloom/urls.py:47-48`.
- Migrationen: `backend/auth_tenancy/migrations/0016_admin_login_lockout.py`,
  `0017_admin_lockout_expiry_index.py`, `0018_merge_auth_tenancy_leaves.py`.
- Tests: `backend/auth_tenancy/tests/test_admin_login_lockout.py` — **25 Testfunktionen**
  (eigene Zählung des Autors; die Orchestrator-Recherche nannte 27 — *pre-verified, Differenz
  im Review zu klären*). QS-Verifikation (Sperre ab dem 6. Versuch, 302 nach Abkühlen,
  REST-Isolation) datiert 2026-10-05 — *pre-verified by orchestrator research*; das Verhalten
  ist durch Tests im File belegt (u. a. `:99-115`, `:124-133`, `:162-187`, `:236`, `:253`).

**Vermerk zur Ablage:** `docs/se/ADR/` ist die gelebte Konvention (ADR-001…020). Dieses ADR
dokumentiert eine Entscheidung **nach** ihrer Auslieferung (ungewöhnliche Reihenfolge, in
§Entscheidungsvorlage und §Review-Round-Trail begründet). Es ändert keine REQ-Datei, keine
Kaskaden-Datei, kein Audit-Dokument und keinen Code.

---

## Entscheidungsvorlage

- **Was ist zu entscheiden:** Ob und wie `/admin/login/` gegen Brute-Force geschützt wird —
  bereits entschieden als **D3** (custom DB-backed lockout, keine neue Abhängigkeit) und
  ausgeliefert (PR #1172, `a70e88a9`, `CHANGELOG.md:82-83`). Dieses ADR bildet die Entscheidung
  nachträglich ab und hebt den HARD STOP aus `SEC-04` §7 **für den Lockout-Teil**.
- **Empfehlung (bereits entschieden, hier abgebildet):** Option C — eigene, DB-gestützte
  Fehlversuchs-Sperre; `django-axes` (Option A) und reine Risiko-Akzeptanz (Option B) sind
  verworfen.
- **Konsequenzen bei Annahme:** Status `proposed → accepted` erst nach
  `concept-reviewer`-Review und User-Freigabe (s. §Review-Round-Trail); der HARD STOP ist für
  den Lockout-Teil formal aufgehoben; der SEC-04-Rest (Tenant-Scoping der übrigen
  Admin-Registrierungen, Read-only Secret) bleibt **OFFEN**.
- **Konsequenzen bei Ablehnung:** die ausgelieferte Implementierung (Code, Migrationen, 25
  Testfunktionen, QS-Nachweis) stünde ohne ADR da — ein Widerspruch zur HARD-STOP-Regel „keine
  Entscheidung außerhalb ADR-011/013" (SEC-04 §7). Eine Ablehnung wäre faktisch ein
  Rollback-Beschluss, kein Status quo.
- **Grober Aufwand:** ADR = klein; Umsetzung ist erfolgt und QS-verifiziert (pre-verified).
  Restaufwand: Review-Durchlauf + Statuswechsel durch `se-architect`.
- **Offene Punkte:** s. §Offene Entscheidungen (O1–O6).

---

## Kontext

**1. Ausgangslage: ein offenes HIGH-Finding mit Brute-Force-Bezug.** Finding AUD-2026-09-223
(HIGH, CVSS 7.1, CWE-307/489) hält fest: „Django-Admin exponiert, 500-er, ohne
Brute-Force-Schutz" (`docs/audit/2026-09/AUDIT_SECURITY.md:47`). Das zugehörige Threat Model
SEC-04 führt die Befunde AUD-2026-09-223, AUD-2026-09-N1
(`docs/audit/2026-09/SEC-04_privileged_key_revocation.md`, Frontmatter `:10`, §1 `:23-27`) und
führt in der Szenario-Tabelle S6 „Brute-Force gegen /admin/login/" mit der Gegenmaßnahme
„**Nicht implementiert** — siehe §7" (`:136-147`).

**2. Warum die vorhandenen DRF-Throttles hier nicht greifen.** Die Brute-Force-Drosselung des
Repos existiert — aber nur für den REST-Login: `LoginRateThrottle` / `LoginIpRateThrottle`
(`backend/rest_api/throttling.py:382/395`) sind DRF-Throttles, ausschließlich gebunden an
`LoginView` (`backend/rest_api/auth_views.py:210-233`, `throttle_classes` `:233`) mit
`POST /api/v1/auth/login/`; konfiguriert in `settings.py:646-663` mit `login` 10/min prod
(`:520-521`) und `login_ip` 60/min prod (`:526-527`), failure-only (`:649-650`), Redis-Cache,
ohne persistente Zeilen. Der Admin-Login läuft über `django.contrib.auth`
(`backend/reqogniloom/urls.py:47-48`, `path("admin/", admin.site.urls)`) und erreicht die
DRF-Throttle-Kette **nie**. `/admin/login/` war damit die eine Auth-Fläche ohne
Fehlversuchs-Zähler.

**3. Threat-Framing: Self-hosted On-Prem-LAN, kein TLS im gebündelten Stack** (*pre-verified by
orchestrator research*). In diesem Betriebsmodell ist `/admin/login/` im internen Netz
erreichbar; ein Login ohne Sperre erlaubt unbegrenzte Passwort-Rates gegen Staff-Konten. Die
Eingrenzung „nur LAN" ist eine Deployment-Annahme, keine technische Kontrolle.

**4. 2FA fehlt vollständig — Residuum.** Keine Paket-Abhängigkeit für `django-axes`,
`django-otp` oder Two-Factor in `backend/requirements.txt` bzw. `backend/pyproject.toml` (vom
Autor geprüft); die INSTALLED_APPS gelten als frei von 2FA-Apps (*pre-verified by orchestrator
research*). Ein zweiter Faktor steht als Ausgleich nicht zur Verfügung — dieses ADR erfindet
**keine** Kompensation.

**5. Die Entscheidung war durch einen HARD STOP blockiert — und ist längst gefallen.** SEC-04
§7 (`:175-184`) stoppt den Brute-Force-Schutz ausdrücklich: „nicht umgesetzt. Grund:
`django-axes` o. ä. erfordert eine **neue Abhängigkeit plus Migrationen** und ist eine
Entscheidung über die *Authentifizierungs*-Drosselung — nicht über die *Autorisierungsachse*
von ADR-011/13." Issue #1135 hielt die Entscheidung offen (`CHANGELOG.md:137`: „OPEN, decision
pending"). Entscheidung D3 (Kommentar 2026-10-04, *pre-verified*) und Auslieferung via PR #1172
folgten danach. Dieses ADR ist die nachgelagerte Dokumentation.

**6. Threat-Model (4 Fragen, Login-Lockout):**

1. *Was gebaut?* Eine DB-gestützte Fehlversuchs-Sperre für `/admin/login/`: Tabelle
   `at_admin_login_lockout` (`models.py:780-869`), Evaluator `admin_lockout.py`, Gate
   `admin_login.py` (`login_form`-Swap + `django.contrib.auth`-Signale), Settings-Block
   (`settings.py:557-582`), drei Migrationen. Kein neues Paket, kein 2FA, keine Änderung an der
   REST-Auth.
2. *Was kann schiefgehen?* (a) Brute-Force/Password-Spraying gegen Staff-Konten über die zweite
   Auth-Fläche (SEC-04 S6). (b) **Sperre als DoS-Waffe**: ein Angreifer sperrt einen legitimen
   Admin; der Schlüssel `(client_ip, username_digest)` begrenzt das auf ein Paar — ein
   geteilter Bucket hinter einer nicht-umschreibenden Proxy-Kette hebelt die Begrenzung aus.
   (c) **Fail-open**: bei DB-Ausfall werden Fehlversuche nicht gezählt
   (`admin_lockout.py:289-308`) — der Schutz schaltet still auf null. (d) **Header-Spoofing**:
   XFF ist client-kontrolliert, daher nur bei gesetztem `NUM_PROXIES` genutzt (`:97-110`).
   (e) **Betreiber-Blindheit**: die Tabelle ist absichtlich nicht im Django-Admin registriert
   (`models.py:865`).
3. *Gegenmaßnahme?* Schwelle 5 Fehlversuche, Fenster 900 s, Sperrdauer 900 s; serverseitiges
   Zählen vor dem Auth-Check; Schlüssel `(client_ip, username_digest)` mit SHA-256-Digest (kein
   Klartext-Username); `REMOTE_ADDR` als unforgeable Default; dokumentiertes Fail-open mit
   WARNING; zentraler Toggle.
4. *Konsequenz?* Mit Gegenmaßnahmen: der Lockout-Teil eines HIGH-Findings ist geschlossen, das
   2FA-Residuum bleibt. Ohne: unveränderte Brute-Force-Exposition auf der privilegiertesten
   Fläche des Systems.

---

## Alternativen

### Option A: `django-axes` (oder ein gleichwertiges Paket) — VERWORFEN

- **Dependency-Policy:** eine neue Abhängigkeit ist in diesem Repo sign-off-pflichtig — HARD
  STOP (`docs/audit/2026-10/bugfix-round-plan.md:81`). Supply-Chain-Gates (Secret-Scanning,
  gepinnte Actions — Findings AUD-2026-09-224/-225) gelten für jede neue Dependency.
- **Django-6.1-Support:** **UNVERIFIED** — die Research konnte ihn nicht belegen. Expliziter
  **OPEN CHECK** (PyPI-Prüfung im Review, O1); hier wird nichts behauptet.
- **Ersatzlast:** die ausgelieferte Implementierung (Modell, Evaluator, Gate, 25
  Testfunktionen, QS-Nachweis) müsste ersetzt oder durch einen zweiten State kontraproduktiv
  gedoppelt werden.
- **Operations:** zusätzliches Paket-Update-Risiko und eine eigene Migrationskette neben der
  vorhandenen Tabelle.
- **Testbarkeit:** die vorhandenen Testfälle (Fail-open, IP-Auflösung, Fenster-Semantik,
  REST-Isolation) müssten komplett neu geschrieben und der QS-Nachweis wiederholt werden.
- **Aufwand:** Austausch + Re-QS = mittel bis groß — für ein bereits verifiziertes Feature.

### Option B: explizite Risiko-Akzeptung plus kompensierende Kontrollen — VERWORFEN

- **Realität:** Kompensation existiert faktisch nicht — kein 2FA (Pakete und INSTALLED_APPS
  geprüft/pre-verified), kein Netzwerk-Gate im Repo. „Nur LAN" (pre-verified) ist eine
  Deployment-Annahme, keine technische Kontrolle.
- **Folge:** das HIGH-Finding AUD-2026-09-223 bliebe offen; eine Akzeptung ohne jede
  Gegenmaßnahme ist nicht vertretbar.

### Option C: eigene, DB-gestützte Fehlversuchs-Sperre (= Entscheidung D3) — GEWÄHLT (CONFIRMED)

- **Evidenz** (vom Autor gelesen): `models.py:780-869` (Tabelle, Unique-Key, Digest,
  GLOBAL-Scope), `admin_lockout.py` (`register_failure:392`, Fenster `:395-397`, Lock-WARNING
  `:400`, Fail-open `:289-308`), `admin_login.py` (`login_form`-Swap `:187-198`, Receiver
  `:141/:159`, Scope `admin:login` `:88`), `settings.py:557-582`, Migrationen 0016/0017/0018.
- **Warum besser als A/B:** (i) keine neue Abhängigkeit — der HARD STOP aus
  `bugfix-round-plan.md:81` wird respektiert statt umgangen; (ii) Wiederverwendung der
  Django-auth-Signale und der Repo-Muster (Digest-Form analog
  `rest_api.throttling._username_digest`, `admin_lockout.py:194`) statt Fremdlogik daneben;
  (iii) DB-backed — der Sperr-State überlebt Cache-/Redis-Ausfall und ist per SQL inspizierbar;
  (iv) isoliert vom REST-Throttle-State (Tests `:236/:253`); (v) bereits ausgeliefert und
  QS-verifiziert (pre-verified, 2026-10-05).

---

## Entscheidung

**Custom DB-backed Login-Lockout für `/admin/login/` — keine neue Abhängigkeit (D3).**

1. **Mechanismus:** eigene, DB-gestützte Fehlversuchs-Sperre auf `AdminLoginLockout`
   (`backend/auth_tenancy/models.py:780-869`, Tabelle `at_admin_login_lockout`), ausgewertet in
   `backend/auth_tenancy/admin_lockout.py`, eingehängt in
   `backend/auth_tenancy/admin_login.py`.
2. **Schwelle:** 5 Fehlversuche führen zur Sperre (`ADMIN_LOGIN_LOCKOUT_THRESHOLD`,
   `settings.py:574-576`); der 6. Versuch wird abgewiesen — auch mit korrektem Passwort
   (Pre-Auth-Gate, `admin_login.py:102-107`).
3. **Fenster:** 900 s (`ADMIN_LOGIN_LOCKOUT_WINDOW_SECONDS`, `:577-579`), verankert auf
   `first_failure_at` (`admin_lockout.py:395-397`) — ein langsames Trickle verlängert das
   Fenster nicht.
4. **Sperrdauer:** 900 s (`ADMIN_LOGIN_LOCKOUT_DURATION_SECONDS`, `:580-582`); nach Ablauf der
   Sperre ist ein Login mit korrekten Credentials wieder erfolgreich (302).
5. **Schlüssel:** `(client_ip, username_digest)` — Unique-Key `uq_admin_lockout_ip_user`
   (`models.py:843-848`); SHA-256-Digest des Usernamens, 32 Hex-Zeichen (`:824-827`);
   Roh-Usernames werden nie persistiert. Die Granularität ist **bewusst pro (IP, Username)**:
   sie vermeidet NAT-Cross-Lockouts (ein Angreifer sperrt nicht alle Admins hinter einem NAT)
   und erschwert Username-Enumeration über unterschiedliche Sperrmuster.
6. **IP-Auflösung:** `REMOTE_ADDR` (unforgeable) als Default; `X-Forwarded-For` nur bei
   gesetztem `NUM_PROXIES` (`admin_lockout.py:97-110`, `:161-178`).
7. **State-Trennung:** der Lockout-State ist vom REST-Login-Throttle getrennt; Admin-Zähler
   beeinflussen `/api/v1/auth/login/` nicht und umgekehrt (Tests `:236`, `:253`).
8. **Serverseitiges Zählen:** die Sperre wird **vor** dem Auth-Check geprüft, der Fehlversuch
   danach über die Receiver `user_login_failed` / `user_logged_in` gezählt
   (`admin_login.py:141/159`); das `login_form`-Gate (`:102-107`, `:187-198`) ist die
   Vor-Auth-Sperre.
9. **Fail-open bei DB-Ausfall:** ein DB-Fehler macht keinen Login zum 500; der Vorfall wird
   mit WARNING geloggt und der Auth-Pfad normal fortgesetzt
   (`admin_lockout.py:289-308`, `:338`, `:450`, `:473-482`) — dokumentierte Policy, konsistent
   zu `rest_api.throttling`.
10. **Toggle:** `ADMIN_LOGIN_LOCKOUT_ENABLED` schaltet das Gesamtfeature ab
    (`settings.py:571-573`); alle vier Werte sind env-overridbar (`decouple`).

**Was diese Entscheidung nicht ist:** kein 2FA, keine Änderung der Autorisierungsachse
(ADR-011), kein Eingriff in SEC-03/RLS und kein Ersatz für die offenen SEC-04-Reste.

---

## Konsequenzen

**Positiv:**

- Der Lockout-Teil des HIGH-Findings AUD-2026-09-223 ist adressiert; der HARD STOP aus SEC-04
  §7 ist für diesen Teil aufgehoben.
- Keine neue Abhängigkeit — das Dependency-Sign-off-Gate bleibt intakt
  (`bugfix-round-plan.md:81`).
- Redis-unabhängig: DB-backed überlebt Cache-Flush/-Outage; der State ist per SQL
  inspizierbar.
- 25 Testfunktionen decken Fail-open, Fenster-Semantik, IP-Auflösung, REST-Isolation und die
  Nicht-Registrierung im Admin ab (`tests/test_admin_login_lockout.py`).
- Env-konfigurierbar ohne Code-Änderung (vier Knöpfe, `settings.py:557-582`).
- Wiederverwendung existierender Muster (SHA-256-Digest-Form analog
  `rest_api.throttling._username_digest`).

**Negativ:**

- **Shared Bucket:** bei ungesetztem `NUM_PROXIES` teilen alle Admins hinter einer
  nicht-umschreibenden Proxy-Kette einen Bucket — ein Angreifer kann legitime Admins mit
  sperren (`admin_lockout.py:97-110`).
- **Keine Betreiber-Sichtbarkeit:** die Tabelle ist absichtlich **nicht** im Django-Admin
  registriert (`models.py:865`, Test `:620`); Einblick nur per SQL / WARNING-Logs.
- **DB-Wachstum:** eine Zeile pro `(ip, username)`-Paar; die Expiry-Indizes
  (`idx_admin_lockout_last`, `idx_admin_lockout_locked_until`, `models.py:849-860`) und der
  opportunistische Cleanup (`admin_lockout.py:244-275`) mildern es, eliminieren es nicht.
- **Verfügbarkeits-Abwägung:** Password-Spraying kann einen legitimen, NAT-hinterlegten Admin
  aussperren — by design in Kauf genommen wegen der `(ip, username)`-Granularität.
- **Modell nicht tenant-gescopet:** GLOBAL-Scope ist auf dem Pre-Auth-Pfad erzwungen
  (`models.py:804-812`); es gibt keine Tenant-Achse, an die RLS andocken könnte.
- **Gate-Fallback:** ist ein fremdes `login_form` vorgesetzt, wird nur gewarnt, nicht
  erzwungen (`admin_login.py:189-201`).
- **2FA bleibt aus:** das Residuum steht unverändert.

---

## Abnahmekriterien

> QS-Verifikation 2026-10-05 — *pre-verified by orchestrator research*; das Einzelverhalten ist
> durch die Test-Suite belegt. AC beziehen sich auf die **bereits ausgelieferte** Umsetzung;
> dieses ADR implementiert nichts.

- [ ] **AC-Lock:** Sperre greift ab dem 6. Fehlversuch (Schwelle 5) — Test `:99-115`
      („Threshold failed admin logins lock (IP, username); next attempt is blocked").
- [ ] **AC-Blocked:** Während der Sperre wird auch das korrekte Passwort abgewiesen, keine
      302, kein Session-Aufbau — Test `:124-133`.
- [ ] **AC-Cool-down:** Nach Ablauf der Sperrdauer ist ein Login mit korrekten Credentials
      wieder erfolgreich (302) — Test `:162-187`.
- [ ] **AC-REST-Isolation:** Admin-Lockout verändert `/api/v1/auth/login/` nicht und umgekehrt
      — Tests `:236`, `:253`.
- [ ] **AC-Settings:** Defaults `ENABLED=True`, `THRESHOLD=5`, `WINDOW=900`, `DURATION=900`,
      env-overridable (`settings.py:557-582`).
- [ ] **AC-Fail-open:** DB-Fehler führt nicht zum 500, WARNING-Log — Tests `:361`, `:373`.
- [ ] **AC-Review:** Statuswechsel `proposed → accepted` erst nach `concept-reviewer`-Review
      und User-Freigabe (s. §Review-Round-Trail).

---

## Offene Entscheidungen

1. **O1 — `django-axes` Django-6.1-Support:** UNVERIFIED. Im Review via PyPI zu prüfen; ein
   positives Ergebnis würde nur eine *spätere* Ersatz-Diskussion begründen, nicht diese
   Entscheidung.
2. **O2 — Betreiber-Sichtbarkeit des Lockout-State:** heute nur SQL/WARNING-Logs (Tabelle
   absichtlich nicht im Admin). Eine Read-only-Ansicht oder ein Management-Command wäre eine
   eigene, kleine Folgeentscheidung.
3. **O3 — SEC-04-Rest (Admin-Härtung):** Tenant-Scoping der übrigen Admin-Registrierungen
   (SEC-04 §6, `:163-173`) und das Read-only-Secret sind **nicht** Gegenstand dieses ADR und
   bleiben OFFEN.
4. **O4 — Workspace-vs-Tenant-Achse:** separater ADR-Slot
   (`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:221`, Kandidat ii; SEC-04 `:66-70`
   verweist auf ADR-011 Punkt 6 → eigene Ownership-/Governance-ADR). Ausdrücklich **nicht**
   dieses ADR.
5. **O5 — 2FA-Residuum:** bleibt offen; dieses ADR erhebt keinen Kompensations-Anspruch.
6. **O6 — Issue #1135 und `CHANGELOG.md:137`:** das Issue ist **nicht** geschlossen und der
   CHANGELOG-Vermerk „OPEN, decision pending" (`:137`) ist **nicht** aktualisiert — beides ist
   Folgeaufgabe nach `accepted`, nicht Teil dieses Dokuments.

---

## Review-Round-Trail

**Kein Review durchgeführt.** Zum Zeitpunkt der Erstellung (2026-10-09) liegt **kein**
`concept-reviewer`-/`se-critic`-RVW-Protokoll vor; es wird keines vorgetäuscht. Verbindlicher
Pfad zur Annahme: `concept-reviewer`-Review (Protokoll unter `docs/se/reviews/`) → Findings →
ggf. Iteration → User-Freigabe → `se-architect` setzt `status: accepted`. Solange bleibt der
Status `proposed`. Die ungewöhnliche Reihenfolge (ADR nach Code) ist in §Entscheidungsvorlage
begründet: D3 war entschieden und ausgeliefert, bevor dieses ADR geschrieben wurde; das ADR
soll den Zustand formal belegen, nicht die Historie umschreiben.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| — | — | nicht durchgeführt (Stand 2026-10-09) | — | — |

---

*Erstellt durch `senior-developer` am 2026-10-09 als nachgelagerte Dokumentation der
Entscheidung D3 (Issue #1135, PR #1172, Commit `a70e88a9`). Enthält keinen Produktcode, keine
Migration, keine Config-Änderung; Issue #1135 bleibt offen, das Audit-Dokument bleibt
uneditiert.*
