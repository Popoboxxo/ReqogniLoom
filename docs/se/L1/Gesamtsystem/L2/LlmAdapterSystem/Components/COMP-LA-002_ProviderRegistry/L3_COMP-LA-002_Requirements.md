# L3 ProviderRegistry Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-LA-002 — ProviderRegistry
> **Parent-System:** LlmAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Sammlung der austauschbaren Provider-Implementierungen; Provider-Auswahl und -Instanziierung basierend auf Deployment-Konfiguration (`LLM_PROVIDER`-Umgebungsvariable); Fehlerbehandlung und Timeout-Konfiguration. Implementiert den Plugin-Mechanismus, der Vendor-Lock-in verhindert.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-LA-001 | LLM-Capability-Interface mit Provider-Abstraktion |
| REQ-L2-LA-005 | Provider-Fehlerbehandlung und Timeout |
| REQ-L2-LA-007 | Azure-OpenAI Provider-Unterstützung |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-INT-002 | eingehend | COMP-LA-003 (CapabilityRouter) | `get_provider() -> LlmCapabilityInterface` |
| IF-LA-INT-003 | ausgehend | COMP-LA-001 (CapabilityInterface) | Klassenimplementierung (Vererbung): Provider-Klassen erben von `LlmCapabilityInterface` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-EXT-OUT-001 | ausgehend | LLM-Provider (extern) | HTTPS-Outbound: Provider-spezifische API (Anthropic/OpenAI/Ollama/Azure) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-LA002-001: Konfigurationsbasierte Provider-Auswahl und -Instanziierung


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die ProviderRegistry SHALL anhand der Umgebungsvariable `LLM_PROVIDER` den korrekten Provider instanziieren. Unterstützte Werte: `anthropic`, `openai`, `ollama`, `azure`. Bei unbekanntem Wert SHALL ein strukturierter Fehler `LLM_PROVIDER_UNKNOWN` zurückgegeben werden. Bei fehlender Variable SHALL `LLM_NOT_CONFIGURED` zurückgegeben werden. Alle Provider-Instanzen MÜSSEN `LlmCapabilityInterface` implementieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `LLM_PROVIDER=anthropic` → `AnthropicProvider` instance returned
- [ ] `LLM_PROVIDER=openai` → `OpenAiProvider` instance returned
- [ ] `LLM_PROVIDER=ollama` → `OllamaProvider` instance returned
- [ ] `LLM_PROVIDER=azure` → `AzureOpenAiProvider` instance returned
- [ ] `LLM_PROVIDER=unknown_value` → raises/returns `LLM_PROVIDER_UNKNOWN`
- [ ] `LLM_PROVIDER` not set → raises/returns `LLM_NOT_CONFIGURED`
- [ ] All returned instances pass `isinstance(instance, LlmCapabilityInterface)` check

---

### REQ-L3-LA002-002: Konfigurierbarer Request-Timeout fuer synchrone Provider-Aufrufe


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Die ProviderRegistry SHALL jeden synchronen HTTP-Request an den externen LLM-Provider mit einem konfigurierbaren Timeout absichern. Der Default-Wert SHALL 30 Sekunden betragen. Der Timeout SHALL über die Umgebungsvariable `LLM_TIMEOUT` (Ganzzahl in Sekunden) überschreibbar sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Default timeout of 30s applied when `LLM_TIMEOUT` is not set
- [ ] `LLM_TIMEOUT=60` → provider uses 60s timeout
- [ ] Timeout exceeded on synchronous call → propagates `TimeoutError` (caught upstream by CapabilityRouter)
- [ ] Timeout setting applies to all synchronous provider implementations uniformly

---

### REQ-L3-LA002-003: Plugin-faehige Provider-Registrierung


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Die ProviderRegistry SHALL einen Registrierungsmechanismus bereitstellen, der das Hinzufügen neuer Provider ohne Änderung am CapabilityRouter oder anderen Komponenten ermöglicht. Die Registrierung SOLL über ein Dictionary oder eine Dekorator-basierte Registry erfolgen.

**Priority:** desired
**Acceptance Criteria:**
- [ ] A new provider class can be registered by adding it to the registry without editing router code
- [ ] Registered provider is discoverable via `get_provider()` when `LLM_PROVIDER` matches
- [ ] Unit test for a stub provider passes without modifying existing provider files

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
