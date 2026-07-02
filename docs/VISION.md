# ReqFlow — Vision & Konzept

> **Status:** Konsolidiert (Zusammenführung aus ehemals VISION.md und KONZEPT.md)
> **Letzte Aktualisierung:** 2026-07-02
>
> *Hinweis: Alle formalen Anforderungen (Requirements), Architekturentscheidungen und Schnittstellen (MCP) wurden in die SE-Kaskade (`docs/se/`) migriert. Dieses Dokument dient ausschließlich als strategischer Einstieg (North Star).*

---

## 1. Executive Summary

**ReqFlow** ist ein AI-natives Requirements-Management- und Systems-Engineering-Tool. Es verbindet die Leichtigkeit moderner Agile-Tools mit der Strenge regulierter Systems-Engineering-Prozesse (Traceability, Baselines, Audit-Trails). 

Das zentrale Alleinstellungsmerkmal (USP) ist die **AI-Nativität**: ReqFlow behandelt AI-Agenten nicht als nachträgliche Chatbot-Integration, sondern als First-Class-Clients. Das System ist primär darauf ausgelegt, von Agenten gelesen und beschrieben zu werden (via Model Context Protocol - MCP).

## 2. Das Problem & Die Lösung

### Die Pain Points
1. **Das AI-Context-Gap:** Coding-Agenten (z.B. Cline, Cursor) generieren Code oft ohne Kenntnis der fachlichen Anforderungen. Ihnen fehlt eine maschinenlesbare Single-Source-of-Truth.
2. **Die Tool-Lücke im Systems Engineering (SE):** Agile-Tools (Jira) sind zu schwach für komplexes SE (Traceability, Versionierung). Klassische ALM-Tools (Polarion, DOORS) sind überkomplex, teuer und haben enormen Vendor-Lock-in.
3. **Mangelnde Traceability:** Teams verlieren den Faden zwischen Requirement, Code-Änderung und Test.

### Die Lösung
ReqFlow bietet:
- Einen eingebauten **MCP-Server**, der AI-Agenten direkten, strukturierten Zugriff auf den Requirements-Graphen gibt.
- **Configurable Rigor:** Das Tool skaliert von einfachem Task-Tracking (Startup) bis zu striktem Baseline- und Approval-Management (MedTech/Automotive) – auf derselben Plattform.
- **Dual-Audience-Strategy:** Software-Entwickler sprechen von "Epics" und "Stories". Systems Engineers sprechen von "System Requirements" und "Component Specs". ReqFlow nutzt ein gemeinsames generisches Datenmodell (Artefakte & TraceLinks) mit konfigurierbaren Terminologie-Layern.

## 3. Architektur-Prinzipien

- **API-First & MCP-First:** Jeder Use Case im Frontend ist zu 100% via REST API und MCP abbildbar. 
- **Strikte Traceability:** Alles ist verlinkbar (Requirements ↔ Architecture ↔ Tests ↔ Glossary).
- **Unveränderliche Baselines:** Für Audits und Reviews können unteilbare "Snapshots" der Requirements erzeugt werden.
- **Self-Hosted & Open Source:** Docker-Compose basierter Stack (Django + React + PostgreSQL) gegen Vendor-Lock-in.
- **Multi-Tenancy Ready:** Row-Level-Isolation ab Tag 1, um spätere SaaS-Modelle ohne Schema-Umbau zu ermöglichen.

## 4. MCP-Integration (Die "AI-Nativität")

ReqFlow stellt einen Model Context Protocol (MCP) Server bereit. 
Dies erlaubt Entwickler-Tools (z.B. Claude Desktop, VS Code Plugins), direkt auf die ReqFlow-Datenbank zuzugreifen. 

**Primäre AI-Workflows:**
1. **Context Fetching:** Ein Entwickler fragt die IDE: *"Was sind die Anforderungen für Feature X?"* Der Agent holt den Baum via MCP.
2. **Decomposition:** Ein Agent analysiert ein L1-System-Requirement und schlägt eine Zerlegung in L2-Subsystem-Requirements vor, inklusive TraceLinks.
3. **Test-Generation:** Ein Agent generiert aus den Akzeptanzkriterien eines Requirements automatisch Playwright/Pytest-Tests.
4. **Validation:** Ein Agent prüft die Konsistenz des Requirement-Graphen auf Zyklen oder nicht-allokierte Komponenten.

## 5. Abgrenzung v1 vs. v2

- **Scope v1 (Core & Greenfield):** Vollständiges CRUD für Requirements, Architektur, Tests, Baselines. Traceability-Graph, MCP-Server, REST-API, lokales Deployment (Docker).
- **Scope v2 (Enterprise & Compliance):** Compliance-Zertifizierung (z.B. IEC 61508), ReqIF-Import/Export, fortgeschrittene Vector-Search (RAG), SaaS-Fähigkeit, komplexe Freigabe-Workflows.

---
*Für detaillierte Anforderungen, Architekturspezifikationen und Test-Abdeckung siehe das Verzeichnis `docs/se/`.*
