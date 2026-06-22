---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 ProviderRegistry Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-LA-002_ProviderRegistry
> **Parent:** L2_LlmAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die ProviderRegistry verwaltet die Sammlung aller LLM-Provider-Implementierungen und stellt einen Plugin-Mechanismus bereit. Sie liest die Umgebungsvariable `LLM_PROVIDER` und instanziiert den entsprechenden Provider (anthropic, openai, ollama, azure). Sie konfiguriert Request-Timeouts via `LLM_TIMEOUT` und erlaubt die Registrierung neuer Provider ohne Änderung anderer Komponenten. Sie gibt eine Instanz von `LlmCapabilityInterface` zurück, die vom CapabilityRouter verwendet wird.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`ProviderRegistry` (Singleton oder Factory-Klasse):** Zentrale Registrierungs- und Instanziierungslogik.
- **`ProviderConfig` (Dataclass):** Kapselt Konfiguration (provider_name, timeout, api_keys, etc.).
- **`AnthropicProvider` (Klasse, Subclass von LlmCapabilityInterface):** Konkrete Implementierung für Anthropic.
- **`OpenAiProvider` (Klasse, Subclass von LlmCapabilityInterface):** Konkrete Implementierung für OpenAI.
- **`OllamaProvider` (Klasse, Subclass von LlmCapabilityInterface):** Konkrete Implementierung für Ollama (lokal).
- **`AzureOpenAiProvider` (Klasse, Subclass von LlmCapabilityInterface):** Konkrete Implementierung für Azure OpenAI.

### 2.2 Datenstrukturen

- **Provider-Registry (In-Memory Dict):**
  - Key: provider_name (str) — "anthropic", "openai", "ollama", "azure"
  - Value: Provider-Klasse (type)
  - Beispiel: `{"anthropic": AnthropicProvider, "openai": OpenAiProvider, ...}`

- **ProviderConfig:**
  - `provider_name`: str
  - `timeout`: int (seconds, default 30)
  - `api_key`: str (sensitive, read from env)
  - `api_base_url`: str | None (optional, für Ollama oder Azure)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-LA002-001 (Config-basierte Auswahl) | Funktion `get_provider() -> LlmCapabilityInterface`: liest `LLM_PROVIDER` aus Env, schlägt in Registry nach, instanziiert und gibt Provider-Instanz zurück. Unbekannte Werte/fehlende Var: strukturierter Fehler (LLM_PROVIDER_UNKNOWN oder LLM_NOT_CONFIGURED). |
| REQ-L3-LA002-002 (Konfigurierbarer Timeout) | Jeder Provider erhält timeout-Konfiguration. Default 30s, überschreibbar via `LLM_TIMEOUT` env var. Timeout wird an konkrete HTTP-Clients weitergegeben. |
| REQ-L3-LA002-003 (Plugin-Registry) | Registrierungsmechanismus: Dict oder Dekorator-basiert. Neue Provider können hinzugefügt werden, ohne Router/andere Komponenten zu ändern. Beispiel: @register_provider("custom_provider") führt Custom-Provider in Registry ein. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-LA-INT-002:** Aufruf vom CapabilityRouter: `get_provider() -> LlmCapabilityInterface`.

- **Ausgänge (Outbound):**
  - **IF-LA-EXT-OUT-001:** Abhängig vom gewählten Provider: HTTPS-Outbound zu Anthropic API / OpenAI API / Ollama / Azure OpenAI.
  - **IF-LA-INT-003:** Konkrete Provider-Klassen erben von LlmCapabilityInterface.

---

## 5. Architectural Rationale

**ADR-L3-LA002-01 — Umgebungsvariable statt Konfigurationsdatei**
*Entscheidung:* Provider-Auswahl via `LLM_PROVIDER` Env-Var, nicht via YAML/JSON-Datei.
*Rationale:* Einfache Deployment-Variabilität, besonders für Container/Kubernetes. Secrets (API-Keys) können sicher als Env-Vars injiziert werden. Erfüllt REQ-L3-LA002-001.
*Alternative abgelehnt:* Konfigurationsdatei — würde bei Containerisierung zu Komplexität führen.

**ADR-L3-LA002-02 — Dezentralisierter Timeout (pro Provider)**
*Entscheidung:* Jeder Provider-Instanz wird individuell ein timeout zugewiesen, der an den zugrunde liegenden HTTP-Client weitergegeben wird.
*Rationale:* Erlaubt unterschiedliche Timeouts pro Provider (z.B. Ollama-local = 5s, Anthropic-remote = 30s). Erfüllt REQ-L3-LA002-002 flexibel.
*Alternative abgelehnt:* Global-only timeout — würde nicht-lokale und lokale Provider unfair handhaben.

**ADR-L3-LA002-03 — Dict-basierte Provider-Registry**
*Entscheidung:* Provider-Registrierung via Plain-Dict oder Class-Attribute-Dict.
*Rationale:* Einfach, pythonic. Neue Provider können durch Eintrag in Dict oder Dekorator hinzugefügt werden. Erfüllt REQ-L3-LA002-003.
*Alternative abgelehnt:* Plugin-Framework (entry_points) — würde Komplexität und Abhängigkeiten hinzufügen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
