"""REST + MCP surface of the renamed decompose caps (spec §4)."""
from __future__ import annotations

import pytest

from rest_api.architecture_decompose_views import GenerateDraftRequestSerializer

_ELEMENT_ID = "11111111-1111-1111-1111-111111111111"


def test_serializer_accepts_the_new_cap_names():
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "max_breadth": 4, "max_depth": 2}
    )

    assert ser.is_valid(), ser.errors
    assert ser.validated_data["max_breadth"] == 4
    assert ser.validated_data["max_depth"] == 2


def test_serializer_ignores_the_removed_legacy_names():
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "breadth": 4, "depth": 2}
    )

    assert ser.is_valid(), ser.errors
    assert "max_breadth" not in ser.validated_data
    assert "max_depth" not in ser.validated_data


def test_serializer_rejects_a_cap_below_one():
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "max_breadth": 0}
    )

    assert not ser.is_valid()
    assert "max_breadth" in ser.errors


def test_serializer_has_no_upper_bound_on_the_caps():
    """The cap is admin policy now, not a hard-coded 5/3 (spec §4)."""
    ser = GenerateDraftRequestSerializer(
        data={"element_id": _ELEMENT_ID, "max_breadth": 12, "max_depth": 6}
    )

    assert ser.is_valid(), ser.errors


def test_mcp_schema_declares_the_new_cap_names():
    from mcp_server.tools.architecture import ArchitectureToolGroup

    schema = next(
        s
        for s in ArchitectureToolGroup().get_tool_schemas()
        if s["name"] == "architecture.decompose"
    )
    properties = schema["inputSchema"]["properties"]

    assert set(properties) == {"element_id", "max_breadth", "max_depth"}


@pytest.mark.django_db
def test_mcp_handler_forwards_the_caps(monkeypatch):
    from application import architecture_decompose_service as svc_mod
    from auth_tenancy.context import AuthContext, AuthMethod
    from mcp_server.tools.architecture import ArchitectureToolGroup

    captured: dict = {}

    class _Svc:
        def generate_draft(self, ctx, element_id, *, max_breadth=None, max_depth=None):
            captured["max_breadth"] = max_breadth
            captured["max_depth"] = max_depth
            raise svc_mod.NotFoundError("stop here")

    monkeypatch.setattr(svc_mod, "ArchitectureDecomposeService", _Svc)
    ctx = AuthContext(
        user_id=None,
        tenant_id=None,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )

    ArchitectureToolGroup()._handle_decompose(
        params={"element_id": _ELEMENT_ID, "max_breadth": 4, "max_depth": 2},
        auth_context=ctx,
        api_key="k",
    )

    assert captured == {"max_breadth": 4, "max_depth": 2}


@pytest.mark.django_db
def test_mcp_handler_passes_none_when_the_caps_are_omitted(monkeypatch):
    from application import architecture_decompose_service as svc_mod
    from auth_tenancy.context import AuthContext, AuthMethod
    from mcp_server.tools.architecture import ArchitectureToolGroup

    captured: dict = {}

    class _Svc:
        def generate_draft(self, ctx, element_id, *, max_breadth=None, max_depth=None):
            captured["max_breadth"] = max_breadth
            captured["max_depth"] = max_depth
            raise svc_mod.NotFoundError("stop here")

    monkeypatch.setattr(svc_mod, "ArchitectureDecomposeService", _Svc)
    ctx = AuthContext(
        user_id=None,
        tenant_id=None,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )

    ArchitectureToolGroup()._handle_decompose(
        params={"element_id": _ELEMENT_ID}, auth_context=ctx, api_key="k"
    )

    assert captured == {"max_breadth": None, "max_depth": None}
