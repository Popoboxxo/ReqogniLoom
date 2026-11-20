# Memory-Provider-Abstraktion: Honcho entkoppeln

> Bewertung und Zielbild für austauschbare Gedächtnis-Provider (pgvector, Honcho,
> Qdrant und künftige). Interne Doku — Stand `main` nach PR #1947.

## Kurzurteil

**Ja, Honcho ist sauber entkoppelbar — der harte Kern ist es bereits.** Die
Domänen- und Service-Ebene spricht ausschließlich gegen den Port
`MemoryBackend`; drei Adapter (pgvector, Honcho, Qdrant) beweisen, dass das
Muster trägt. Die verbleibende Kopplung sitzt an den **Rändern** (REST-Flat-
Felder, Webhook-Route, Management-Commands) und ist additiv, ohne
Domänen-Umbau, auflösbar.

## Ist-Zustand (belegt)

| Baustein | Ort | Bewertung |
|---|---|---|
| Port/Adapter | `backend/memory/backends.py::MemoryBackend` (14 abstrakte Methoden) | sauber |
| Provider-Registry | `MEMORY_BACKEND_REGISTRY` + `@register_memory_backend` | sauber |
| Fähigkeiten | `MemoryCapabilities` (`dialectic`, `search`, `search_derived`, `consolidation`, `scopes`, `summaries`, `webhooks`, Grenzen) | sauber |
| Settings-Schema | `BackendSettingField`, `settings_schema`, `effective_settings()` (DB > Env > Default) | sauber |
| Admin-Surface | `application/memory_settings_service.py` liest `schema`, `values`, `capabilities` je Backend | schema-getrieben |
| Conformance | `memory/testing/conformance.py` + `tests/test_backend_contract.py` | vorhanden |
| Adapter | `PgvectorMemoryBackend`, `HonchoMemoryBackend`, `QdrantMemoryBackend` | drei echte Implementierungen |

Services (`application/memory_entry_service.py`, `memory_admin_service.py`,
MCP-Tools) rufen `get_memory_backend()` / `active_memory_capabilities()` und
enthalten **keine** Backend-Verzweigungen — das ist der entscheidende Punkt.

## Verbleibende Lecks

1. **REST-Flat-Felder sind hartkodiert.**
   `application/memory_settings_service.py:42-60` pflegt
   `_DERIVED_OPTION_FIELDS`/`_DERIVED_SECRET_FIELDS` mit `honcho_*`/`qdrant_*`;
   `memory/memory_rest.py:405-483` wiederholt dieselben Felder plus eine
   literale Backend-Auswahlliste (`["pgvector", "honcho", "qdrant"]`).
   Ein neuer Provider braucht heute REST-Codeänderungen.
2. **Webhook-Route ist Honcho-spezifisch.**
   `rest_api/urls.py:857` + `memory/memory_rest.py:2628` und
   `memory/webhooks.py` (HMAC-Format, Registrierungs-Command). Die Capability
   `webhooks` existiert, steuert die Route aber nicht.
3. **Provider-spezifische Management-Commands.**
   `memory/management/commands/honcho_migrate_scopes.py`,
   `honcho_register_webhooks.py`; `memory_reconcile.py:161-232` verzweigt hart
   auf `backend_name`.
4. **Backend-Auswahl als Literal.** Die Choice-Liste in `memory_rest.py:405`
   (und ggf. UI-Contracts) muss aus der Registry kommen.

Nicht betroffen: `MemoryEntryRef`/`backend_ref` ist bereits provider-neutral;
Tenant-Scoping, RLS und Degradation laufen über die Service-Fassade.

## Zielbild

- `MemoryBackend` bleibt der Port. Ein Provider ist ein Adapter, kein Sonderweg.
- **Optionale Hooks mit Default-No-op** auf dem Port:
  - `webhook_route() -> str | None` und `verify_webhook(request) -> events`
  - `provision_tenant(tenant_id)` / `teardown_tenant(tenant_id)` (Honcho-Workspace,
    künftige Provider)
- **REST generisch:** `backend_options.<provider>.<field>` und
  `backend_secrets.<provider>.<field>` sind die Wahrheit; die flachen
  `honcho_*`/`qdrant_*`-Felder bleiben eine Release-Lang als Deprecation-Aliase.
- **Auswahl aus der Registry:** `memory_backend`-Choices = Registry-Keys.
- **Tooling capability-getrieben:** `memory_reconcile` und Commands verzweigen
  über Capabilities/Hooks, nicht über Namen.

## Anbindung eines neuen Providers (Soll-Zustand)

1. Adapter schreiben: 14 Methoden, `capabilities`, `settings_schema`,
   `settings_key`.
2. `@register_memory_backend("<name>")` dekorieren.
3. Fixture in `memory/testing/conformance.py` ergänzen; `test_backend_contract.py`
   und `test_every_registered_backend_has_conformance_fixture` grün.
4. Settings ausschließlich über `backend_options`/`backend_secrets` belegen.
5. Optional: Webhook-Hook und Tenant-Lifecycle implementieren.

**Akzeptanzkriterium:** Schritte 1–4 ändern keine Datei in `application/`,
`rest_api/` oder `mcp_server/`.

## Umgesetzt (PR #1949)

- **P1/P2:** `memory_backend`-Choices kommen aus `MEMORY_BACKEND_REGISTRY`;
  `backend_options`/`backend_secrets` sind schema-getrieben und die UI rendert
  die Felder aus `backends_payload`. Die flachen `honcho_*`/`qdrant_*`-Felder
  bleiben Kompatibilitäts-Alias für die eingebauten Provider.
- **P3:** generische Route `/api/v1/memory/webhooks/<provider>/` — Transport
  (Größen-Guard, Throttle, Cache-Invalidierung) geteilt, Credential im
  Provider (`verify_webhook`). Honcho behält Pfad und Vertrag.
- **P4:** `memory_reconcile` ruft `reconcile_external` am Backend auf;
  `capabilities.external_store` steuert Scan und Severity. Die Honcho-/Qdrant-
  Scans liegen in ihren Adaptern.
- **P5:** `provision_tenant` bei Tenant-Erstellung (best-effort);
  `teardown_tenant` per `post_delete`-Signal auf `transaction.on_commit`.
- **P6:** `memory/tests/test_provider_plugin_contract.py` registriert einen
  Dummy-Provider und beweist: wählbar, schema-validiert, im Admin-Payload
  sichtbar — ohne Core-Änderung.

## Arbeitspakete (Priorität, additiv)

| # | Paket | Aufwand | Risiko |
|---|---|---|---|
| P1 | REST/Serializer schema-getrieben, Flat-Felder als Aliase | M | niedrig |
| P2 | Backend-Choices aus `MEMORY_BACKEND_REGISTRY` | S | niedrig |
| P3 | `webhook_route()`/`verify_webhook()` + generische Route `<provider>` | M | mittel |
| P4 | `memory_reconcile`/Commands capability-getrieben | S | niedrig |
| P5 | `provision_tenant`/`teardown_tenant`-Hook | M | mittel |
| P6 | Provider-Quickstart + „dritter Provider ohne Core-Änderung"-CI-Test | S | niedrig |

Reihenfolge P2 → P1 → P4 → P3 → P5 → P6 hält Honcho/Qdrant durchgehend
lauffähig; P1/P2 sind die einzigen, die ein neuer Provider heute zwingend
braucht.

## Empfehlung

Die Abstraktion ist bereits vorhanden und tragfähig. Statt eines neuen
Umbaus genügen **P1 + P2**, um „neuer Provider ohne Kernänderung" zu
erreichen; P3/P5 machen auch die optionalen Fähigkeiten steckbar. Honcho
verschwindet damit aus dem Kern und bleibt ein Adapter unter mehreren.
