---
type: REVIEW
scope: wp-1d-error-format-matrix
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: Fehlerformat-Matrix

**Quelle:** `wp1d-auth-pagination-filter-errors-live.json` → Schlüssel `errors`
(16 Fälle) und `ingress`; `wp1d-authorization-asymmetry.json` →
`error_envelope_shapes` (6 Fälle); `wp1d-roundtrip-v1.json`/`v2.json`.

## Referenz: was das Projekt als Soll definiert

`rest_api/error_envelope.py:1-16` definiert das Zielformat:

```
{"error": {"code": <string>, "message": <string>, "details": <objekt>}}
```

und `error_envelope.py:8-9` behauptet:

> „Wired via `REST_FRAMEWORK['EXCEPTION_HANDLER']` so REST responses stay
> consistent with the MCP-server error format."

Die Bewertung unten misst deshalb die **interne** Konsistenz der fünf
tatsächlich auftretenden Formate — nicht die Übereinstimmung mit einem
externe Standard.

---

## Matrix A — konsistentes Verhalten (Klassen-basierte Views)

| Fall | Methode | Status | Top-Level-Keys | `error` | `error.code` | `message` (Auszug) |
|---|---|---|---|---|---|---|
| unbekannter Pfad | GET `/api/v1/definitely-not-a-route/` | 404 | `["error"]` | Objekt | `NOT_FOUND` | The requested API endpoint does not exist. |
| Requirement nicht vorhanden | GET `/api/v1/requirements/0000…0000/` | 404 | `["error"]` | Objekt | `NOT_FOUND` | Requirement 00000000-0000-0000-0000-000000000000 not found |
| leerer Create-Body | POST `/api/v1/requirements/` `{}` | 400 | `["error"]` | Objekt | `VALIDATION_ERROR` | Validation failed. |
| unbekanntes Feld | POST `{"not_a_field": 1}` | 400 | `["error"]` | Objekt | `VALIDATION_ERROR` | Validation failed. |
| falscher Typ | POST `{"level": 12345}` | 400 | `["error"]` | Objekt | `VALIDATION_ERROR` | Validation failed. |
| `null` statt Pflichtwert | POST `{"title": null}` | 400 | `["error"]` | Objekt | `VALIDATION_ERROR` | Validation failed. |
| falscher Content-Type | POST `text/plain` | 415 | `["error"]` | Objekt | `UNSUPPORTED_MEDIA_TYPE` | Unsupported media type "text/plain" in request. |
| kaputtes JSON | POST `{not json,,,` | 400 | `["error"]` | Objekt | `VALIDATION_ERROR` | JSON parse error … |
| falsche Methode | PUT `/api/v1/auth/login/` | 405 | `["error"]` | Objekt | `METHOD_NOT_ALLOWED` | Method "PUT" not allowed. |
| kein Workspace-Mitglied | GET `/api/v1/workspaces/B/members/` | 403 | `["error"]` | Objekt | `PERMISSION_DENIED` | You are not a member of this workspace. |
| kein Token | GET ohne `Authorization` | 401 | `["error"]` | Objekt | `AUTHENTICATION_REQUIRED` | Authentication credentials were not provided. |
| UUID-Pfad-Validierung | GET `/api/v1/requirements/not-a-uuid/` | 400 | `["error"]` | Objekt | `VALIDATION_ERROR` | `'pk' must be a well-formed UUID.` |

Alle `Content-Type: application/json`. `details` ist konsistent ein Array von
`{field, errors}` (Serialisierer-Form) — teils leer `[]`, teils gefüllt.

**Bemerkenswert:** `rest_api/tests/test_uuid_error_asymmetry_is_intentional.py`
dokumentiert die UUID-Asymmetrie bewusst (`test_uuid_error_asymmetry_is_intentional.py`),
`test_error_envelope_single_form_1081.py` die Hüllen-Form. Beides ist belegt und
trägt.

---

## Matrix B — Abweichungen (`AUD-2026-09-082`)

**Fünf Fehlerformate über drei Transportformen.**

| # | Form | Auslöser | Ort | Beispielantwort |
|---|---|---|---|---|
| 1 | `{"error": {code, message, details}}` | DRF-Exception-Handler, Klassen-Views | `error_envelope.py:48-68` | `{"error":{"code":"NOT_FOUND","message":"…","details":[]}}` |
| 2 | **`{"detail": "<string>"}`** | `_handle()`-Helfer | **`rest_api/link_type_views.py:31-43`** | `{"detail":"Link type 'zzz' not found in this workspace."}` |
| 3 | **`{"detail": "<string>"}`** | funktionsbasiertes View | **`backend/baseline/views.py:101`** (u. a.) | `{"detail":"Query parameter 'scope' is required."}` |
| 4 | **`{success, imported_count, skipped_count, status, errors, warnings}`** | CSV-Import-Controller | **`application/import_service.py:307-313`** | `{"success":false,"imported_count":0,"skipped_count":3,"status":"rollback","errors":[],"warnings":[]}` |
| 5 | **`{"error": "<string>"}`** | MCP-Transport | `mcp_server` (SSE/401) | `{"error":"Authentication required"}` |

Dazu die ReqIF-Import-Form als **sechste** Variante:
`{"success": true, "dry_run": false, "needs": {"created": 0, "updated": 0, "skipped": 20, "errors": [{"identifier": "...", "message": "An internal error occurred while importing this object."}]}}`
(`wp1d-roundtrip-v2.json` → `reqif.import_ctype_multipart/form-data`).

### Warum Form 2/3 den Handler umgehen

`rest_api/link_type_views.py:31-43`:

```python
def _handle(func, *args, success: int = status.HTTP_200_OK, **kwargs) -> Response:
    try:
        payload = func(*args, **kwargs)
    except PermissionDeniedError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    except NotFoundError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
```

`_handle` baut die Fehlerhülle selbst und gibt eine `Response` zurück — der
zentrale `reqogniloom_exception_handler` sieht sie nie. Betroffen sind alle
sechs Views in `link_type_views.py` (`LinkTypeDefaultsListView`,
`LinkTypeDefaultsDetailView`, `WorkspaceLinkTypeListView`,
`WorkspaceLinkTypeDetailView`, `WorkspaceLinkTypeResetView`).

`baseline/views.py:74-101` ist ein **funktionsbasiertes** View (`scope_preview`),
das Django direkt aufruft — DRFs Exception-Pipeline läuft daran vorbei.

Live belegt, beide 400:

```
GET  /api/v1/baselines/scope-preview/
     → {"detail":"Query parameter 'scope' is required."}

POST /api/v1/workspaces/77c6286e-…/link-type-definitions/zzz/reset/
     → {"detail":"Link type 'zzz' not found in this workspace."}
```

### Warum die Behauptung in `error_envelope.py:8-9` nicht stimmt

Der Docstring sagt, REST bleibe „consistent with the MCP-server error format".
Gemessen:

| Transport | Fehlerform |
|---|---|
| REST (Klassen-View) | `{"error": {code, message, details}}` |
| REST (`_handle`, FBV) | `{"detail": "<string>"}` |
| REST (CSV-Import) | `{success, imported_count, skipped_count, status, errors, warnings}` |
| REST (ReqIF-Import) | `{success, dry_run, needs}` |
| MCP | `{"error": "<string>"}` |

Fünf Formen. Die MCP-Form ist nicht einmal REST-ähnlich (flacher String statt
Objekt). **Ein Client braucht fünf Parser.**

---

## Befund `AUD-2026-09-077` — kein `trace_id` in der Fehlerhülle

`{"error": {code, message, details}}` enthält **kein** Feld, das eine
Response mit einem Server-Log korreliert. Die Anwendung führt aber
durchgängig eine `request_id` — jedes Log-Record hat sie:

```json
{"asctime": "2026-09-29 23:15:56,643", "name": "application.import_service",
 "levelname": "ERROR", "request_id": "a92f7382-eab5-4044-90a0-4096b52ae2ee",
 "message": "ImportService: DB error during atomic insert, rolling back. …"}
```

Die Information ist vorhanden, sie erreicht den Client nur nicht. Für einen
500er ohne Serverzugriff (oder für einen Nutzer, der nur den Screenshot an den
Support schickt) ist der Fehler damit nicht reproduzierbar.

Erschwerend: genau die 500er, für die das am nötig wäre, sind die
Paginierungs-500er aus `AUD-2026-09-073` — clientseitig ausgelöst, also
besonders gut für Support-Fälle geeignet.

---

## Matrix C — Fehlercode-Registry und ihre Lücken

`error_envelope.py:34-45` bildet elf HTTP-Statuscodes auf Codes ab. Gemessene
Codes über alle Tests dieses Abschnitts:

`AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`, `NOT_FOUND`,
`VALIDATION_ERROR`, `METHOD_NOT_ALLOWED`, `UNSUPPORTED_MEDIA_TYPE`,
`INTERNAL_SERVER_ERROR`, `RATE_LIMITED` (nicht ausgelöst),
`CONFLICT` (nicht ausgelöst), `SERVICE_UNAVAILABLE` (nicht ausgelöst).

Dazu **drei Codes außerhalb der Registry**, die aus
`authentication.py` stammen und in `_STATUS_TO_CODE` fehlen:
`invalid_token`, `invalid_signature`, `invalid_api_key`. Sie erscheinen als
`error.code` auf 401, sind aber nicht über die Registry auflösbar — ein Client,
der den Code-Space aus `_STATUS_TO_CODE` enumerieren will, übersieht sie.
Nicht falsch, aber die Behauptung in `error_envelope.py:29-30`
(„Every key is a code in `rest_api.serializers._ERROR_MESSAGES` … a client can
enumerate the whole code space from it") gilt für die Auth-Codes nicht.

**Fehlend ganz:** ein Code für „abgelaufenes Token" und einer für „falscher
`aud`/`iss`" — siehe `wp1d-auth-matrix.md` / `AUD-2026-09-088`.

---

## Nicht geprüft (BLOCKED)

| Punkt | Grund |
|---|---|
| 409-/`CONFLICT`-Pfade live auslösen | hätten einen echten Konflikt-Zustand gebraucht (z. B. gleichzeitige ETag-Schreibvorgänge); nur der Statuscode-Kontrast 400/404/403/401/405/415 ist live belegt |
| 429-/`RATE_LIMITED` | bewusst nicht ausgelöst, um parallele Audit-Agenten auf dem geteilten Stack nicht zu blockieren (gleiche Entscheidung wie WP-1a) |
| 503-/`SERVICE_UNAVAILABLE` | bräuchte das Abschalten von Redis/Postgres — hätte den geteilten Stack beschädigt |
| 500 mit englischer vs. deutscher Lokalisierung | `detect_lang(request)` vorhanden; nur der Default-Pfad (englisch) gemessen |
