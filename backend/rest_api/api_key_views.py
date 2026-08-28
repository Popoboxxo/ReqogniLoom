"""
COMP-RA-001 — ApiKeyViewSet (REQ-L3-AT001-003).

REST endpoints for API key lifecycle (create / list / revoke).

Architecture:
  Uses AuthenticationService from auth_tenancy for all operations.
  Standardised auth error handling via AuthTenancyAuthentication.

Error shape:
  Every failure uses the single project-wide envelope built by
  ``rest_api.serializers.build_error_response`` (REQ-L2-RA-009)::

      {"error": {"code": "...", "message": "...", "details": []}}

  This module previously emitted a flat ``{"error": "<code>", "message": ...}``
  body, which was one of three competing error shapes in the REST surface
  (systemaudit 2026-08-27, P1 item 13). The ``code`` string literals and the
  human-readable messages are unchanged — only the nesting is.

Endpoints:
  GET    /api/v1/api-keys/         — list keys (metadata only)
  GET    /api/v1/api-keys/<pk>/    — retrieve one key (metadata only)
  POST   /api/v1/api-keys/         — create key (plaintext returned ONCE)
  DELETE /api/v1/api-keys/<pk>/    — revoke key
"""
from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from auth_tenancy.services import Operation
from auth_tenancy.services.authentication import AuthenticationService
from rest_api.serializers import build_error_response


class ApiKeyViewSet(ViewSet):
    """REST ViewSet for API key lifecycle management.

    list:    GET  /api/v1/api-keys/         — metadata-only listing
    retrieve:GET  /api/v1/api-keys/<pk>/    — metadata for one key
    create:  POST /api/v1/api-keys/         — create, plaintext returned once
    destroy: DEL  /api/v1/api-keys/<pk>/    — revoke key

    Authentication: Bearer token (AuthTenancyAuthentication via DRF default classes).
    Permissions:  Any authenticated, role-holding user may manage OWN keys.
    Tenant scope: Keys are scoped to the user — list/create return only the
                  authenticated user's keys.  Tenant isolation is implicit via
                  AuthenticationService which filters by user_id.

    RBAC gate (fix #716): every action here is inherently self-scoped — a
    caller only ever creates/lists/reads/revokes THEIR OWN keys (see the
    ``user_id``-filtered service calls below), never another user's or a
    workspace's data. Requiring workspace ``write`` for POST/DELETE — the
    global ``RbacPermission`` HTTP-method default (GET->read, POST/DELETE
    ->write) — incorrectly locked a Viewer out of ever creating (or
    revoking) their own key, leaving them with literally no programmatic
    access path (MCP X-API-Key / REST Bearer) at all, UI-only. ``READ`` is
    declared uniformly for every action here as the least-privilege
    operation that still requires the caller to hold an active role
    somewhere in the tenant (an authenticated user with NO role anywhere
    remains correctly denied — ``AuthorizationService.decide_access`` denies
    READ too in that case). This mirrors the "authenticated self-service
    action, not a workspace-write action" precedent already used by
    ``UserPreferenceView``/``WorkspaceMembersView``/``UserViewSet`` for
    other self- or tenant-scoped endpoints.
    """

    required_operation = Operation.READ

    # Uses global DEFAULT_AUTHENTICATION_CLASSES (AuthTenancyAuthentication)
    # and DEFAULT_PERMISSION_CLASSES (RbacPermission) from settings; the
    # ``required_operation`` above overrides RbacPermission's per-HTTP-method
    # default for every action on this ViewSet (see rest_api.auth_enforcer.
    # RbacPermission.has_permission).
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._authn = AuthenticationService()

    # -- helpers -----------------------------------------------------------

    def _get_user_id(self, request: Request) -> str | None:
        """Extract the authenticated user's UUID from the auth context."""
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            return None
        return str(ctx.user_id)

    def _get_tenant_id(self, request: Request) -> str | None:
        """Extract the authenticated user's tenant UUID from the auth context."""
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            return None
        return str(ctx.tenant_id)

    # -- list (GET /api/v1/api-keys/) --------------------------------------

    def list(self, request: Request, **kwargs: Any) -> Response:
        """Return metadata-only listing of the authenticated user's API keys."""
        user_id = self._get_user_id(request)
        if user_id is None:
            return Response(
                build_error_response(code="authentication_required", message="Not authenticated"),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        from uuid import UUID
        keys = self._authn.list_api_keys(user_id=UUID(user_id))
        return Response(keys, status=status.HTTP_200_OK)

    # -- retrieve (GET /api/v1/api-keys/<pk>/) -----------------------------

    def retrieve(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """Return metadata for a single API key owned by the caller.

        Mirrors :meth:`list` — the plaintext is never returned; it is only
        available once at creation time. Keys belonging to other users (and
        therefore other tenants) are never exposed: the lookup is scoped to the
        authenticated user's keys, so a foreign key id yields 404.

        Returns 200 with the key metadata, 404 if the key does not exist or is
        not owned by the caller, 401 if unauthenticated.
        """
        user_id = self._get_user_id(request)
        if user_id is None:
            return Response(
                build_error_response(code="authentication_required", message="Not authenticated"),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not pk:
            return Response(
                build_error_response(code="NOT_FOUND", message="Key ID is required."),
                status=status.HTTP_404_NOT_FOUND,
            )

        from uuid import UUID
        try:
            key_uuid = UUID(pk)
        except (ValueError, AttributeError):
            return Response(
                build_error_response(code="NOT_FOUND", message="Invalid key ID."),
                status=status.HTTP_404_NOT_FOUND,
            )

        keys = self._authn.list_api_keys(user_id=UUID(user_id))
        match = next((k for k in keys if k.get("id") == str(key_uuid)), None)
        if match is None:
            return Response(
                build_error_response(code="NOT_FOUND", message="Key not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(match, status=status.HTTP_200_OK)

    # -- create (POST /api/v1/api-keys/) -----------------------------------

    def create(self, request: Request, **kwargs: Any) -> Response:
        """Create a new API key and return its plaintext exactly once.

        Request body:
          { "name": "my-api-key-label" }

        Response (201):
          {
            "id": "<uuid>",
            "name": "my-api-key-label",
            "plaintext": "reqlo_<40 chars>",   // ONLY shown here, never again
            "warning": "Save this key now — it will not be shown again."
          }

        Errors:
          400 — name missing or empty
          400 — max active keys reached
          401 — not authenticated
        """
        user_id = self._get_user_id(request)
        tenant_id = self._get_tenant_id(request)
        if user_id is None or tenant_id is None:
            return Response(
                build_error_response(code="authentication_required", message="Not authenticated"),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        name = request.data.get("name")
        if not isinstance(name, str) or not name.strip():
            return Response(
                build_error_response(code="VALIDATION_ERROR", message="Field 'name' is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        from uuid import UUID
        try:
            result = self._authn.create_api_key(
                user_id=UUID(user_id),
                tenant_id=UUID(tenant_id),
                name=name.strip(),
            )
        except ValueError as exc:
            return Response(
                build_error_response(code="VALIDATION_ERROR", message=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "id": str(result.api_key_id),
                "name": result.name,
                "plaintext": result.plaintext,
                "warning": "Save this key now — it will not be shown again.",
            },
            status=status.HTTP_201_CREATED,
        )

    # -- destroy (DELETE /api/v1/api-keys/<pk>/) ---------------------------

    def destroy(self, request: Request, pk: str | None = None, **kwargs: Any) -> Response:
        """Revoke an API key by its UUID.

        The key is immediately invalidated — subsequent requests using this key
        will receive 401 ``api_key_revoked``.

        Returns 204 with no body on success.
        Returns 404 if the key does not exist or does not belong to the user.
        """
        user_id = self._get_user_id(request)
        if user_id is None:
            return Response(
                build_error_response(code="authentication_required", message="Not authenticated"),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not pk:
            return Response(
                build_error_response(code="NOT_FOUND", message="Key ID is required."),
                status=status.HTTP_404_NOT_FOUND,
            )

        from uuid import UUID
        try:
            key_uuid = UUID(pk)
        except (ValueError, AttributeError):
            return Response(
                build_error_response(code="NOT_FOUND", message="Invalid key ID."),
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            self._authn.revoke_api_key(api_key_id=key_uuid, user_id=UUID(user_id))
        except Exception:
            return Response(
                build_error_response(code="NOT_FOUND", message="Key not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
