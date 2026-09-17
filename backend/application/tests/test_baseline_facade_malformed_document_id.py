"""
Regression test for issue #724.

A malformed (non-UUID) document_id passed to BaselineFacade.create_baseline
with scope="document" must raise a ValidationError (surfaced as HTTP 400),
not leak a ValueError through to the generic handler and produce a 500.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import ValidationError
from application.baseline_facade import BaselineFacade

pytestmark = pytest.mark.django_db


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


class TestMalformedDocumentId:
    def test_malformed_document_id_raises_validation_error_not_value_error(self):
        """Non-UUID string for document_id must be caught as ValidationError.

        Before #724 fix, ``UUID(str("not-a-uuid"))`` raised an unhandled
        ValueError that propagated to the generic ``except Exception`` and
        returned HTTP 500.
        """
        facade = BaselineFacade()
        ctx = _make_ctx()

        with (
            patch("application.baseline_facade.TenantContext"),
            patch(
                "application.baseline_facade.BaselineFacade._check_scope_allowed"
            ),
            patch("application.baseline_facade.BaselineFacade._enforce_audit_gate"),
        ):
            with pytest.raises(ValidationError, match="document_id"):
                facade.create_baseline(
                    scope="document",
                    workspace_id=uuid.uuid4(),
                    name="test-baseline",
                    ctx=ctx,
                    document_id="not-a-uuid",
                )
