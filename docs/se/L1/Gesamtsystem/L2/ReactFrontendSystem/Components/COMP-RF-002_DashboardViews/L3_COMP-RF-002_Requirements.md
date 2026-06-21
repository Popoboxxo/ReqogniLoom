# L3 DashboardViews Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-002 — DashboardViews
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Workspace-Uebersicht mit Projekt-Karten, Requirements-Zaehlern, Anzahl offener Punkte und aktivem Terminologie-Profil.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-002 | Dashboard mit Projektübersicht und offenen Punkten |
| REQ-L2-RF-009 | UI-Performance |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RF-INT-001 | eingehend | COMP-RF-001 | Routing-Events, View-Activation |
| IF-RF-INT-002 | eingehend | COMP-RF-006 | Translation-Keys (`t(key, params)`), Terminologie-Profil-Labels |

## Externe Schnittstellen (Systemgrenze)

Keine direkte externe Schnittstelle; Kommunikation mit dem Backend erfolgt ausschliesslich ueber IF-RF-EXT-OUT-001 via NavigationShell-koordiniertem REST-API-Layer.

## L3 Komponenten-Anforderungen

### REQ-L3-RF002-001: Workspace-Kartenliste mit Metriken

Die DashboardViews-Komponente MUSS nach Aktivierung durch die NavigationShell alle dem authentifizierten Nutzer zugänglichen Workspaces als Kartenliste darstellen. Jede Karte MUSS die Anzahl der Requirements, die Anzahl offener Punkte (Requirements im Initial-State ohne TraceLink) und das aktive Terminologie-Profil enthalten. Die gesamte Kartenliste MUSS innerhalb von 2 Sekunden nach Aktivierung vollständig gerendert sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Dashboard renders within 2 seconds after login/activation
- [ ] Each workspace card shows: workspace name, requirement count, open item count, active terminology profile
- [ ] Workspace with zero open items shows counter "0" (not empty/hidden)
- [ ] Integration test: Login → dashboard visible → workspace cards contain correct counters

---

### REQ-L3-RF002-002: Terminologie-Profil-Label-Rendering im Dashboard

Die DashboardViews-Komponente MUSS das aktive Terminologie-Profil (Dev-Modus / SE-Modus) aus dem I18nService beziehen und alle Labels in der Workspace-Karte (z.B. Bezeichnung fuer Requirements, offene Punkte) entsprechend des aktiven Profils darstellen. Ein Profilwechsel MUSS ohne Seiten-Reload wirksam werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Dev-Modus active: card labels use development terminology (e.g., "Stories", "Backlog Items")
- [ ] SE-Modus active: card labels use SE terminology (e.g., "Requirements", "Open Items")
- [ ] Profile switch → dashboard labels update immediately without page reload
- [ ] Unit test: Render DashboardViews with mock i18n context → labels match active profile

---

### REQ-L3-RF002-003: Navigation von Dashboard zu Workspace-Detail

Die DashboardViews-Komponente MUSS bei Klick auf eine Workspace-Karte die NavigationShell ueber IF-RF-INT-001 informieren, den ausgewaehlten Workspace zu aktivieren und zur Artefakt-Navigation oder zum Requirements-Editor weiterzuleiten.

**Priority:** desired
**Acceptance Criteria:**
- [ ] Click on workspace card → navigation to artifact tree for that workspace
- [ ] Active workspace is persisted in router state for back-navigation
- [ ] Browser back button from workspace view returns to dashboard

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
