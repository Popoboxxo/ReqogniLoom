"""
COMP-PL-001 EntitySchemaManager — Actor entity + Artifact system fields.

Attribut v3 WS2 (#936, spec sections 3 and 4): the ``Actor`` carrier for
internal users and external dummies, its per-tenant uniqueness rules, and the
``Artifact.owner``/``reporter``/``priority`` columns every item type inherits.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from persistence.models import Actor, Artifact, User
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)


class TestActorUniqueness:
    """The two partial unique constraints from spec section 4."""

    def test_same_user_is_unique_per_tenant(self, tenant_a) -> None:
        with active_tenant(tenant_a):
            user = User.objects.create(
                username="actor-u1", email="actor-u1@t.test", tenant=tenant_a
            )
            Actor.objects.create(
                tenant=tenant_a, kind="user", user=user, display_name="U1"
            )
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Actor.objects.create(
                        tenant=tenant_a, kind="user", user=user, display_name="U1 again"
                    )

    def test_same_user_may_be_an_actor_in_another_tenant(self, tenant_a, tenant_b) -> None:
        user = User.objects.create(
            username="actor-multi", email="actor-multi@t.test", tenant=tenant_a
        )
        with active_tenant(tenant_a):
            Actor.objects.create(
                tenant=tenant_a, kind="user", user=user, display_name="Multi"
            )
        with active_tenant(tenant_b):
            Actor.objects.create(
                tenant=tenant_b, kind="user", user=user, display_name="Multi"
            )
        assert Actor.unscoped.filter(user=user).count() == 2

    def test_external_display_name_is_unique_per_tenant_case_insensitively(
        self, tenant_a
    ) -> None:
        with active_tenant(tenant_a):
            Actor.objects.create(
                tenant=tenant_a, kind="external", display_name="Frau Müller"
            )
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    Actor.objects.create(
                        tenant=tenant_a, kind="external", display_name="frau müller"
                    )

    def test_internal_and_external_may_share_a_display_name(self, tenant_a) -> None:
        """The external rule is scoped to ``kind="external"`` on purpose."""
        with active_tenant(tenant_a):
            user = User.objects.create(
                username="actor-alex", email="actor-alex@t.test", tenant=tenant_a
            )
            Actor.objects.create(
                tenant=tenant_a, kind="user", user=user, display_name="Alex"
            )
            Actor.objects.create(
                tenant=tenant_a, kind="external", display_name="Alex"
            )
            assert Actor.objects.filter(tenant=tenant_a, display_name="Alex").count() == 2

    def test_same_external_name_in_different_tenants_is_allowed(
        self, tenant_a, tenant_b
    ) -> None:
        with active_tenant(tenant_a):
            Actor.objects.create(tenant=tenant_a, kind="external", display_name="Bob")
        with active_tenant(tenant_b):
            Actor.objects.create(tenant=tenant_b, kind="external", display_name="Bob")
        assert Actor.unscoped.filter(kind="external", display_name="Bob").count() == 2

    def test_declared_constraints(self) -> None:
        names = {constraint.name for constraint in Actor._meta.constraints}
        assert {"uq_actor_tenant_user", "uq_actor_tenant_external_name"} <= names


class TestArtifactSystemFields:
    """Spec section 3: the cross-cutting fields on ``Artifact``."""

    def test_defaults_are_empty(self, tenant_a, workspace_a) -> None:
        with active_tenant(tenant_a):
            artifact = Artifact.objects.create(
                tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement"
            )
        assert artifact.owner is None
        assert artifact.reporter is None
        assert artifact.priority == ""

    def test_owner_and_reporter_reference_actor_and_survive_deletion(
        self, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            owner = Actor.objects.create(
                tenant=tenant_a, kind="external", display_name="Owner X"
            )
            reporter = Actor.objects.create(
                tenant=tenant_a, kind="external", display_name="Reporter Y"
            )
            artifact = Artifact.objects.create(
                tenant=tenant_a,
                workspace=workspace_a,
                artifact_type="Requirement",
                owner=owner,
                reporter=reporter,
            )
            owner.delete()
            artifact.refresh_from_db()
        assert artifact.owner is None
        assert artifact.reporter_id == reporter.id

    def test_priority_accepts_a_free_value(self, tenant_a, workspace_a) -> None:
        """No model ``choices``: the scale is owned by the attribute definition."""
        with active_tenant(tenant_a):
            artifact = Artifact.objects.create(
                tenant=tenant_a,
                workspace=workspace_a,
                artifact_type="Requirement",
                priority="blocker",
            )
        assert artifact.priority == "blocker"
