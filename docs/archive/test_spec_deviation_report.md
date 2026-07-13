# Test- vs. Spezifikations-Abweichungsbericht (Deviation Report)

Dieser Bericht analysiert die systematischen Abweichungen zwischen der **Spezifikation (L2/L3)**, den **Testfällen** und der tatsächlichen **Umsetzung im Frontend und Backend**.
Ganz im Sinne des Contract-First-Ansatzes dient die *Spezifikation* als "Single Source of Truth".

## 1. Frontend Abweichungen (ReactFrontendSystem)

Die Analyse der Frontend-Tests (`vitest run`) und des Codes zeigt, dass die Test-Suite extrem "verrottet" (Test Rot) ist und viele Spezifikationen in der UI gar nicht oder falsch umgesetzt sind, während die Tests entweder fehlen, veraltet sind oder gar nicht erst kompilieren.

| Spezifikation (L2/L3) | Test-Status | Umsetzung (Ist-Zustand vs. Spec) | Deviation / Handlungsbedarf |
|-----------------------|-------------|----------------------------------|-----------------------------|
| **REQ-L2-RF-003**: Inline-Editing & Markdown in RequirementEditors | 🔴 **Fehlerhaft** (`ArchitectureEditors.test.tsx` wirft URL-Fehler `Invalid URL: /api/v1/requirements/...`) | **Abweichung:** Der Editor nutzt teilweise noch veraltete API-Pfade ohne Basis-URL, was zu Laufzeit-Abstürzen in Tests führt. | API-Client `BASE_URL` Setup in Tests und Hooks ist defekt. Muss gemäß Backend-Spezifikation korrigiert werden. |
| **REQ-L3-RF003-005**: Dynamische UI-Masken für StReq und SyReq (Fibonacci-Slider, MoSCoW) | ⚪ **Fehlt komplett** | **Abweichung:** Die UI rendert immer noch ein generisches Eingabefeld. Der geforderte Fibonacci-Slider für `SyReq` und das Dropdown für `StReq` fehlen in der UI. | Komponenten `RequirementEditors` muss strikt auf den `type` prüfen und dynamische Formularelemente rendern. |
| **REQ-L2-RF-006**: Traceability-Anzeige (Bidirektional) | 🔴 **Fehlerhaft** (`TraceabilityPanel.test.tsx` kompiliert nicht: `Cannot find name 'expect'`) | **Abweichung:** Das Panel wird in der UI angezeigt, aber die Unit-Tests wurden bei der Migration auf Vitest zerschossen. | Die Test-Suite für das Panel muss repariert werden. |
| **REQ-L2-RF-017**: Sandbox-Diff-UI & Baseline-Vergleich | ⚪ **Fehlt komplett** | **Abweichung:** Es gibt im Frontend noch keinen zweispaltigen Diff-Viewer für Baselines (Added/Modified/Deleted mit Versions-Delta). | Die Komponente muss von Grund auf neu gebaut werden. |
| **REQ-L2-RF-016**: Flat View & Level View Toggle | 🟢 **Bestanden** (Aber teilweise unvollständig) | **Abweichung:** Der "Flat View" ist vorhanden, aber die hierarchische Kaskadendarstellung ("Level View") mit L0 -> L1 -> L2 ist in der UI inkonsistent und zeigt den `suspect`-Status nicht richtig an. | Der `HierarchyTreeView` muss die `suspect` Flags vom Backend (SN-30) korrekt auswerten und rendern. |
| **REQ-L2-RF-012**: Workspace-Konfigurations-UI (SE-Modus / Preset Toggle) | 🔴 **Fehlerhaft** (`WorkspaceContext.test.tsx` Type-Errors: `is_active`, `closed_at` fehlen) | **Abweichung:** Das Frontend-Datenmodell (Typescript-Interface) für `Workspace` ist veraltet. Das Backend schickt bereits `is_active`, `closed_by` (SN-33 Archivierung), aber das Frontend verarbeitet sie nicht. | `types.ts` und `WorkspaceContext` müssen an die aktuelle API-Spezifikation angeglichen werden. |
| **REQ-L2-RF-008**: Terminologie-Profil-Rendering | 🔴 **Fehlerhaft** (`ModalDialogBase.test.tsx` Mock-Errors) | **Abweichung:** Die dynamischen Labels funktionieren zwar teilweise, aber die Dialoge (z.B. Requirement anlegen) nutzen teilweise noch Hardcoded-Texte statt der i18n-Terminologie-Engine. | Dialog-Komponenten müssen refactored werden, um `useTranslation` korrekt für Entitäten zu nutzen. |

> [!WARNING] Fazit Frontend
> Das Frontend hinkt der Spezifikation stark hinterher. Besonders die Architektur-Erweiterungen für AI-Native SE (Fibonacci-Schätzung, Baseline-Diffs) fehlen in der Umsetzung. Gleichzeitig kompilieren weite Teile der Frontend-Tests nicht mehr, da die Typescript-Interfaces nicht nachgezogen wurden, als das Backend aktualisiert wurde.

## 2. Backend Abweichungen (ApplicationServiceSystem & RestApiAdapterSystem)

Der Lauf von `pytest` liefert folgendes Ergebnis: **1.783 bestanden, 28 fehlgeschlagen, 11 fehlerhaft (Errors).**

Das Backend ist deutlich näher an der Spezifikation als das Frontend. Allerdings gibt es auch hier eklatante Lücken, wenn man die L2-Dokumente (`L2_ApplicationServiceSystem_Requirements.md` & `L2_RestApiAdapterSystem_Requirements.md`) mit den fehlschlagenden Tests abgleicht:

| Spezifikation (L2) | Test-Status | Umsetzung (Ist-Zustand vs. Spec) | Deviation / Handlungsbedarf |
|--------------------|-------------|----------------------------------|-----------------------------|
| **REQ-L2-AS-015**: Traceability-Link Validierung | 🔴 **Fehlgeschlagen** (`test_all_ten_types_present`) | **Abweichung:** In der Spezifikation (bzw. dem L2-Katalog) wurden neue Link-Typen definiert (wie z.B. unser neues `derives` oder `uses-term` für das Glossar). Der Test `EXPECTED_TYPES` ist veraltet und hat diese neuen Typen nicht hinterlegt. | Der Test schlägt zurecht fehl, hier muss die Testsuite an die (geänderte) Spezifikation angepasst werden. |
| **REQ-L2-AS-012**: Requirement Decomposition (Architektur-Breakdown) | 🔴 **Fehlgeschlagen** (`test_decompose_with_target_architecture_elements`) | **Abweichung:** Die Funktionalität, ein Requirement in mehrere Child-Requirements aufzubrechen und *direkt* an Architektur-Elemente zu knüpfen, schlägt fehl. | Der `RequirementService` wirft Exceptions bei der Zuordnung. Die Spezifikation verlangt eine atomare Transaktion (REQ -> Arch), die aktuell im Backend fehlschlägt. |
| **REQ-L2-AS-025**: MCP Server Audit Logging (Workspace Delete) | 🔴 **Fehlerhaft** (`test_write_tool_creates_audit_entry[workspace.delete]`) | **Abweichung:** Der Audit-Log beim Löschen eines Workspaces via MCP stürzt komplett ab (`NameError: WorkspacePresetConfig is not defined`), weil ein alter Import fehlt. | Das Löschen von Workspaces via API/MCP ist kaputt. |
| **REQ-L2-AS-030**: ICD (Interface Control Documents) Immutability | 🔴 **Fehlgeschlagen** (15x in `icd/tests/test_icd.py`) | **Abweichung:** L2 fordert, dass freigegebene Schnittstellen-Dokumente (ICD) *immutable* sind und eine neue Version erzeugt wird. Die Implementierung ändert jedoch das bestehende ICD, anstatt eine saubere Historie aufzubauen. | Massiver Verstoß gegen die Traceability-Spezifikation! Der `ICDService` muss versionierte Dokumente speichern, statt sie zu überschreiben. |
| **REQ-L2-RA-015**: PDF VCRM Report Export | 🔴 **Fehlgeschlagen** (`test_pdf_requirement_document_contains_workspace_title`) | **Abweichung:** Der PDF-Export schlägt fehl oder nutzt nicht die korrekten Layouts aus der Spezifikation. (Die Abhängigkeit `reportlab` fehlte sogar im Container). | Der ReportGenerator exportiert falsche Daten. |
| **REQ-L2-RA-020**: SSE Transport API für MCP-Tools | 🔴 **Fehlerhaft** (6x in `test_e2e_sse_transport.py`) | **Abweichung:** Die Streaming-API für den Agenten (SSE) wirft Timeouts/Parse-Errors. | Die SSE-Schnittstelle entspricht nicht dem MCP-Transport-Vertrag der Spezifikation. |

> [!CAUTION] Fazit Backend
> Während Standard-CRUD gut funktioniert, brechen alle "Advanced SE"-Konzepte in sich zusammen. Vor allem die **Immutability von Schnittstellen-Dokumenten (ICD)** ist falsch implementiert und löscht alte Versionsstände, was ein direkter Verstoß gegen die SE-Spezifikation (Compliance) ist. Auch der Requirement-Decomposition-Algorithmus ist fehlerhaft.

---

### Gesamtfazit & Nächste Schritte

Wir haben nun einen exakten Spiegel des Systems auf Basis der Spezifikation!
**Wie möchtest du vorgehen?**
1. Sollen wir als erstes die **Frontend-Tests** und Typescript-Mocks fixen, damit wir das Frontend wieder sauber kompilieren können?
2. Oder sollen wir direkt in das **Backend** springen und den **ICD Versioning Bug** (Verstoß gegen Immutability) beheben?
3. Oder etwas anderes? Sag mir einfach Bescheid!
