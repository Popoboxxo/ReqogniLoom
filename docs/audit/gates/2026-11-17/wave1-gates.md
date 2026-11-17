# Problemanalyse-Gates — Welle 1 (2026-11-17)

Basis `main` `5778f97`. Plan §0.1, je Finding zwei Pass (Beleg → Adversary). Audit-Datei als Hypothese behandelt.

## S1.1 — REST-Vertrag
- **API-001: KEIN PROBLEM.** Die behauptete 500 auf `/transitions/` ist unerreichbar: `auth_tenancy/rest.py:247-248` aktiviert den Tenant vor `request.auth_context`; `set_request_tenant` setzt Thread-Local UND GUC. Der cmp-Comment in `workflow_transitions.py:133-139` ist faktisch falsch. Der geplante `.unscoped`-Fix wäre eine ADR-03-Regression → **nicht umsetzen**, nur Kommentar korrigieren + Positivtest.
- **API-006: ANPASSEN.** Nur 405/415 universal ergänzen; 409/412/429/503 sind bereits operationsscharf deklariert. 412 global würde den #1397-Gate mit 615 Operationen brechen (simuliert). Docstring korrigieren.
- **R2A-001/002/006/007/008: BESTÄTIGT** (Envelope `request_id`, OpenAPI-Version aus `get_app_version()`, typisierte Fehler, Deprecation-Signale nach SPA-Migration, Pagination-Normalisierung zentral).
- **R2A-005: ANPASSEN.** `getAllPages` gibt `T[]` an ~10 Callern zurück; Return-Type-Änderung wäre breaking. Stattdessen separate `getAllPagesWithCount()` + `architecture.listAll` auf `getAllPages` umstellen.

## S1.2 — MCP-Protokoll
- **API-003/004/005/007, R2A-003/004: BESTÄTIGT.** API-004 braucht explizite Alias-Map (`UNAUTHORIZED→-32000`, `SERVICE_UNAVAILABLE→-32020`), sonst -32603-Fehlzuordnung. API-005: `build_manifest` muss bei Duplikaten **werfen**; Count 301 bleibt (latente Kollision zuerst durch Test prüfen).
- **API-002: BESTÄTIGT, Fix ANPASSEN.** `Mcp-Session-Id` primär, aber Query-Fallback eine Release-Version behalten (sonst brechen SSE-Clients und der eigene `endpoint`-Event). DELETE nur mit Bound-Key-Proof.
- **API-008: ANPASSEN.** Zentrale `inputSchema`-Validierung ist nicht sicher umsetzbar (bewusst deaktiviert in `tools/base.py:133-138`, `jsonschema` nur transitiv, generische Fallback-Schemas). Stattdessen Ratchet: explizite Schemas pro Produktionsgruppe + `reject_unknown_params`-Aufruf.

## IMPL-001 — Architektur-Editor change_reason
- **BESTÄTIGT**, aber impacto-Korrektur: `ArchitectureArtifactForm.tsx` reicht `requiresChangeReason` nicht weiter → Feld nie sichtbar. **Das Backend verlangt jedoch kein `change_reason` für Architektur-Update/Delete** (nur Requirement/StakeholderNeed + Workflow-Transitions). Die E2E-Begründung „edits blocked client-side" ist falsch und muss korrigiert werden. Minimalfix: 3 additive Zeilen, testid `artifact-form-change-reason`.
