---
adr_id: ADR-009
title: "System-Benachrichtigungen wandern als Feed-Tab in den Assistenten-Einstieg"
status: accepted
date: "2026-09-27"
deciders: [user]
affected_reqs: [REQ-L0-060, REQ-L0-005]
superseded_by: null
---

# ADR-009: System-Benachrichtigungen wandern als Feed-Tab in den Assistenten-Einstieg

**Status:** accepted
**Datum:** 2026-09-27
**Entscheider:** user
**Betroffene REQs:** REQ-L0-060 (Konsistentes UI/UX Design und Universelles Versioning),
REQ-L0-005 (Konfigurierbarer Item-Lifecycle mit Rollen und Approval-Gates)
**Bezug:** Issue **#987**; `frontend/src/components/InterviewWidget/InterviewWidget.tsx:9-14, 88`;
`frontend/src/components/NavigationShell/NavigationShell.tsx:225`;
`frontend/src/components/InterviewWidget/InterviewWidget.module.css:1-14`;
`frontend/src/components/NavigationShell/NotificationBell.module.css:29-32, 60-64`;
`frontend/src/components/NavigationShell/SidebarNavigation.tsx:760`;
`backend/application/models.py:303-310`; `backend/auth_tenancy/models.py:495-510`

---

## Kontext

**Zwei Korrekturen an den Ausgangsprämissen des Issues #987, beide gegen den Code
geprüft:**

**1. Die „AI Sprechblase" existiert.** Sie ist `InterviewWidget`
(`frontend/src/components/InterviewWidget/InterviewWidget.tsx`), in
`frontend/src/components/NavigationShell/NavigationShell.tsx:225` auf **jeder**
authentifizierten Route eingehängt. Der Code nennt sie selbst ein **„FAB"**
(`InterviewWidget.tsx:88`). Sie war nur nicht unter dem Namen zu finden: weder „Bubble"
noch „FAB" steht im Komponentennamen. Die frühere Triage hat das als Blocker
ausgewiesen — dieser Blocker war ein Suchfehler.

**2. Es gibt keine geometrische Kollision** mit der Benachrichtigungs-Glocke. Die
Glocke ist `position: absolute` **innerhalb** der Sidebar
(`NotificationBell.module.css:60`; eingehängt in `SidebarNavigation.tsx:760`), das
Widget ist `position: fixed` unten rechts **außerhalb** davon
(`InterviewWidget.module.css:1-14`). Die im Issue angenommene Überlappung existiert
nicht.

**Die Randbedingung, die die Entscheidung formt:** `InterviewWidget.tsx:9-14`
dokumentiert den Audit-Befund **S19** — das Widget „beherbergt bewusst keinen Chat",
denn ein Overlay, das über die Navigation hinweg offen bleibt und dabei Formulare
überdeckt, ist für lange Sitzungen ein UX-Problem. Ein **Chat** darf also nicht in das
Overlay wandern. Ein Benachrichtigungs-**Feed** ist kein Chat, und das Panel ist bereits
360px breit — genau die Breite, die das heutige 20rem-Dropdown verwendet
(`NotificationBell.module.css:64`).

---

## Alternativen

### Option A: Chat in das Overlay verlagern, Benachrichtigungen daneben — VERWORFEN

**Beschreibung:** Der Assistent wird zum Chat-Einstieg und um Benachrichtigungen
erweitert; die Sidebar-Zeile bleibt.

**Abwägung:** Verlässt den dokumentierten Befund **S19** (`InterviewWidget.tsx:9-14`)
ausdrücklich. Ein Chat, der über die Navigation hinweg offen bleibt und Formulare
überdeckt, ist genau das Problem, das S19 als Grund für die heutige Trennung festhält.
Man umgeht eine dokumentierte UX-Entscheidung, um ein weiteres Feature zu tragen.

**Risiko:** HOCH — revertiert einen Audit-Befund

---

### Option B: Benachrichtigungen als zusätzliche Sidebar-Zeile neben dem Widget — VERWORFEN

**Beschreibung:** Badge zusätzlich auf der Glocke, Feed bleibt in der Sidebar, das
Widget bekommt eine zweite, parallele Einstiegsmöglichkeit.

**Abwägung:** Zwei Einstiegswege für denselben Sachverhalt auf derselben Seite — genau
die Doppelung, die das Issue beseitigen wollte. Erzeugt außerdem zwei Plätze, an denen
der Unread-Zustand auseinanderlaufen kann.

**Risiko:** MITTEL

---

### Option C: Status im globalen Header neben dem Widget — VERLOREN, außerhalb des Panels

**Beschreibung:** Ein Global-Status-Icon in der Topbar, unabhängig vom Widget.

**Abwägung:** Verlässt die Entscheidung, Benachrichtigungen an den Assistenten-Einstieg
zu binden, und erzeugt ein drittes Navigations-Element. Nicht weiterverfolgt.

**Risiko:** MITTEL

---

### Option D: Badge auf dem Widget; Feed als Tab im bestehenden 360px-Panel; Sidebar-Zeile entfällt (GEWÄHLT)

**Beschreibung:** Solange ungelesene Benachrichtigungen existieren, zeigt
`InterviewWidget` ein Badge. Der Feed ist ein **Tab im Panel des Widgets**. Die
Sidebar-Zeile entfällt. Das Opt-out wird an das bestehende
`GET`/`PATCH /api/v1/users/me/notification-preferences/` verdrahtet. Der Unread-Zähler
bleibt über `aria-live` zugänglich.

**Vorteile:**
- Das Widget existiert bereits, ist global eingehängt und hat exakt die benötigte
  Breite (360px) — **kein** neues Träger-UI
- Die Sidebar wird um ein Element entlastet
- Das Opt-out ist **Verdrahtung, keine neue Backend-Arbeit**: die vier Schalter
  existieren bereits (`backend/application/models.py:303-310`: `transition_pending`,
  `suspect_flagged`, `assigned`, `comment_added`) und haben heute **keine** UI
- Kein Chat im Overlay — S19 bleibt gewahrt

**Nachteile:**
- Die Sidebar-Zeile und das Panel sind zwei verschiedene Eingriffsorten
- Der Badge wird zum **einzigen** Unread-Signal auf der Seite — er muss also
  zuverlässig und per `aria-live` announced werden

**Risiko:** NIEDRIG

---

## Entscheidung

1. Ein Benachrichtigungs-**Badge** erscheint auf `InterviewWidget`, solange ungelesene
   Benachrichtigungen existieren.
2. Der Feed ist ein **Tab im 360px-Panel** des Widgets — nicht im 20rem-Sidebar-Dropdown.
3. **Die Sidebar-Zeile entfällt.**
4. Das **Opt-out** wird an das bestehende `GET`/`PATCH /api/v1/users/me/notification-preferences/`
   verdrahtet — vier Schalter, die bereits existieren und heute keine UI haben. Das ist
   Verdrahtung, **keine** neue Backend-Arbeit.
5. Der **Unread-Zähler bleibt über `aria-live` zugänglich**, da das Badge nun das
   einzige Signal ist.

---

## Konsequenzen

**Positiv:**

- Die Sidebar verliert ein Element; der Assistenten-Einstieg wird zum einzigen Ort für
  Interaktion und Benachrichtigungen.
- Das Opt-out ist sofort vollständig funktionsfähig, weil Backend **und** Semantik der
  vier Schalter bereits existieren — die UI-Lücke schließt sich ohne Backend-Änderung.
- Kein Chat im Overlay: der Audit-Befund **S19** bleibt gewahrt, und die
  20rem-Dropdown-Fläche in der Sidebar entfällt.
- Der Badge wird zum einzigen Unread-Signal und ist damit `aria-live`-pflichtig — das
  ist eine **Verschärfung** der Barrierefreiheitsanforderung an genau dieses Control.

**Negativ:**

- **Korrektur zur Ausgangsaussage des Issues:** Der 26px-„Ghost-Bell" ist **heute
  nicht mehr** der am wenigsten standardisierte Control. Die Token-Abgleichung wurde
  bereits durch **#986** abgeschlossen — `NotificationBell.module.css:29-32`
  dokumentiert, dass der Bell *früher* 26px/Radius 0 war und **jetzt** die geteilte
  Control-Skala nutzt (`--btn-h-sm`, `--radius-btn`, `--control-font-size`). Die
  Design-System-Ratchet zieht daher **nicht** eine reparierte Glocke nach, sondern die
  **zwei neuen** Controls: das Badge auf dem FAB und der Feed-Tab im Panel. Genau die
  beiden sind neu und müssen tokenisiert werden.
- **Ehrlichkeitsnotiz, die zu prüfen ist:** Der `localStorage`-Open-State-Key des
  Widgets ist vom Benachrichtigungs-Setting **getrennt**, und der Preference-Endpunkt
  ist **konto-skaliert** (`UserNotificationPreference`, `OneToOne` auf `User`,
  „across every tenant and workspace", `backend/auth_tenancy/models.py:495-510`), das
  Widget ist dagegen **global**. Beide Zustände müssen auseinander bleiben können, ohne
  dass sie sich widersprechen — das ist vor der Umsetzung zu verifizieren.
- Das Entfernen der Sidebar-Zeile ist ein **sichtbarer** UI-Bruch: Nutzer, die
  Benachrichtigungen bisher dort gesucht haben, finden den Einstieg erst nach dem Öffnen
  des Assistenten-Panels. Der Badge ist der einzige Hinweis auf dessen Existenz.
- Der Badge trägt jetzt die volle Signal-last für „ungelesen". Fällt er aus oder wird
  er nicht announced, ist der Unread-Zustand für Screenreader-Nutzer nicht mehr
  wahrnehmbar.

---
