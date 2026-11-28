"""Shared builders for the change-impact engine (S4) tests.

Not a test module (leading underscore), so pytest never collects it.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from application.change_impact_engine import ChangeImpactEngine
from application.models import ChangeRequest, ChangeRequestAffectedItem
from persistence.models import Artifact, TraceLink
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_workspace,
)


@dataclass
class EngineEnv:
    """An armed tenant, one provisioned workspace, one editor and one CR."""

    tenant: Any
    workspace: Any
    ctx: Any
    cr: ChangeRequest
    engine: ChangeImpactEngine
    artifacts: dict[str, Artifact] = field(default_factory=dict)


@contextmanager
def engine_env(*, create_cr: bool = True) -> Iterator[EngineEnv]:
    """Yield a ready-to-run engine environment inside an active tenant."""
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        ctx = editor_ctx(tenant, workspace)
        cr = (
            ChangeRequest.objects.create(
                tenant=tenant,
                workspace_id=workspace.id,
                title="Impact CR",
            )
            if create_cr
            else None
        )
        yield EngineEnv(
            tenant=tenant,
            workspace=workspace,
            ctx=ctx,
            cr=cr,
            engine=ChangeImpactEngine(),
        )


def make_artifact(
    env: EngineEnv,
    name: str,
    *,
    artifact_type: str = "Requirement",
    parent: Artifact | None = None,
) -> Artifact:
    """Create a bare Artifact of *artifact_type* (no domain entity row)."""
    artifact = Artifact.objects.create(
        tenant=env.tenant,
        workspace=env.workspace,
        artifact_type=artifact_type,
        parent=parent,
    )
    env.artifacts[name] = artifact
    return artifact


def make_link(
    env: EngineEnv,
    source: Artifact,
    target: Artifact,
    link_type: str,
) -> TraceLink:
    """Create one TraceLink directly (bypasses catalog validation)."""
    return TraceLink.objects.create(
        tenant=env.tenant,
        source=source,
        target=target,
        link_type=link_type,
    )


def add_affected_item(
    env: EngineEnv,
    artifact: Artifact,
    *,
    action: str = "modify",
) -> ChangeRequestAffectedItem:
    """Attach *artifact* to the change request's change set."""
    return ChangeRequestAffectedItem.objects.create(
        tenant=env.tenant,
        change_request=env.cr,
        item_id=str(artifact.id),
        entity_type="item",
        change_action=action,
    )


def chain(env: EngineEnv, prefix: str, length: int) -> list[Artifact]:
    """Create a ``derives-from`` chain of *length* artifacts (root last).

    With ``derives-from`` the propagation runs target -> source, so
    ``chain[-1]`` is the root (the deepest target) and ``chain[0]`` the far end.
    """
    artifacts = [
        make_artifact(env, f"{prefix}{index}") for index in range(length)
    ]
    for index in range(1, length):
        make_link(env, artifacts[index - 1], artifacts[index], "derives-from")
    return artifacts


__all__ = [
    "EngineEnv",
    "add_affected_item",
    "chain",
    "engine_env",
    "make_artifact",
    "make_link",
]
