# L0 Stakeholder Needs — Backlog (Zukünftige Anforderungen)

> **Level:** L0 (Stakeholder Needs)
> **System:** ReqFlow
> **Datum:** 2026-06-26
> **Status:** erfasst (noch nicht in L1 heruntergebrochen)

Dieses Dokument enthält relevante Stakeholder-Needs, die für zukünftige Iterationen (oder v2) identifiziert wurden, aber noch nicht in die L1-System-Anforderungen heruntergebrochen sind.

---

### REQ-L0-023 — SN-23: ReqIF-Support für MBSE-Datenaustausch

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Systems Engineers müssen Anforderungsstrukturen verlustfrei über den Industriestandard ReqIF (Requirements Interchange Format) importieren und exportieren können, um nahtlos mit externen Zulieferern und klassischen SE-Tools (wie DOORS oder Polarion) zusammenzuarbeiten.

**Rationale:** CSV-Exporte/Importe (SN-13) reichen für komplexe, hierarchische MBSE-Datenstrukturen mit Trace-Links nicht aus. ReqIF ist in regulierten Industrien zwingend erforderlich.

---

### REQ-L0-024 — SN-24: Test-Ausführungs-Management (Test Runs)

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

QA-Ingenieure und CI/CD-Pipelines müssen Testläufe (Test Runs) protokollieren und den Ausführungsstatus von Testfällen dokumentieren können. Automatisierte Pipelines müssen Testergebnisse direkt über die API oder den MCP-Server als Testlauf-Ergebnis an das System zurückmelden können.

**Rationale:** SN-03 definiert Testfälle, aber ohne die Dokumentation der eigentlichen Testausführung fehlt der Nachweis auf der rechten Seite des V-Modells (Verification & Validation).

---

### REQ-L0-025 — SN-25: Kollaboration und In-App-Diskussion

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Entwickler, Systems Engineers und AI-Agenten müssen direkt an einzelnen Artefakten (Requirements, Architektur-Elementen) kontextbezogen diskutieren können, inkl. @Mentions und Kommentar-Threads.

**Rationale:** Ohne integrierte Kommunikation finden Abstimmungen in externen Tools statt, wodurch der Kontext für AI-Agenten und zukünftige Reviews verloren geht.

---

### REQ-L0-026 — SN-26: Semantische Suche (RAG) und KI-Assistenz

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Nutzer und AI-Agenten müssen das System über semantische (vektorbasierte) Suchen abfragen können, um Duplikate zu identifizieren, Impact-Analysen intelligent zu unterstützen und fehlende Verknüpfungen vorzuschlagen.

**Rationale:** Eine rein textbasierte Suche skaliert bei tausenden Anforderungen nicht. Ein AI-natives Tool profitiert maßgeblich von integrierten Embeddings/Vektordatenbanken (RAG).

---

### REQ-L0-027 — SN-27: Granulare Zugriffssteuerung (Item-Level Access)

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Projekt-Admins müssen die Sichtbarkeit und Bearbeitungsrechte auf Subsystem- oder sogar Artefakt-Ebene einschränken können (z.B. Lesezugriff für Zulieferer A nur auf Komponenten des Subsystems X).

**Rationale:** Mandantenfähigkeit (SN-08) trennt Kunden komplett. In großen Projekten müssen jedoch externe Partner am selben Projekt arbeiten, ohne den gesamten Systemkontext sehen zu dürfen.

---

### REQ-L0-028 — SN-28: Visuelles Diffing von Artefakten und Baselines

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Reviewer müssen Änderungen an Artefakten oder Unterschiede zwischen zwei Projekt-Baselines visuell als "Diff" vergleichen können, um Freigabe-Entscheidungen (Approvals) fundiert treffen zu können.

**Rationale:** Das Audit-Log (SN-11) speichert Änderungen, ist aber für Menschen schwer lesbar. Ein visueller Text-Diff ist für formale Reviews unerlässlich.
