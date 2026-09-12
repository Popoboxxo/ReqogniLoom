"""Single source of truth for the project-wide pgvector embedding dimension.

Issue #794 made every ``VectorField`` in this codebase read its ``dimensions``
from :data:`EMBEDDING_VECTOR_DIMENSIONS` rather than from a local integer
literal. Before that module existed the dimension was hardcoded independently
in five places and they disagreed:

===========================================  =====================
Column                                       Declared dimension
===========================================  =====================
``pl_requirement.embedding``                 ``vector(1536)``
``pl_tracelink.embedding``                   ``vector(1536)``
``icd_version.embedding``                    ``vector(1536)``
``mem_workspace_memory.embedding``           ``vector(384)``
``mem_user_tenant_memory.embedding``         ``vector(384)``
===========================================  =====================

The 1536 columns were shaped for OpenAI ``text-embedding-3-small``, which was
the ``EMBEDDING_PROVIDER`` default at the time they were added. That default
later changed to ``sentence-transformers`` (``all-MiniLM-L6-v2``, 384-dim)
without the columns following, so under the *shipped default configuration*
every generated vector was dimension-mismatched against those three columns.
The write-side guards (``RequirementService._generate_and_store_embedding``,
``TraceLinkService._generate_and_store_embedding``,
``icd.icd_manager._apply_embedding``) therefore skipped 100% of writes and the
read-side guard (``application.search_service._run_semantic_query``)
short-circuited 100% of semantic passes -- silently, by design, because
embedding generation is best-effort and must never fail the surrounding write.
Net effect: zero embeddings were ever persisted for
Requirement/TraceLink/Icd and ``artifact.search``'s semantic pass was
permanently empty on every default deployment. #794 pinned the columns to the
default provider's width so the shipped configuration works with no operator
action.

Issue #826 makes the value operator-configurable without weakening that
default. The width is resolved once, at import time, from the
``EMBEDDING_VECTOR_DIMENSIONS`` environment variable:

* **unset or blank** -> :data:`DEFAULT_EMBEDDING_VECTOR_DIMENSIONS` (384), so
  an untouched deployment keeps working exactly as before;
* **a positive integer** -> that value is used for every embedding column;
* **anything else** (non-integer, zero, negative) -> :class:`ImproperlyConfigured`
  at import, loudly, before any model or migration code can act on a bogus
  width.

Because model fields bind the value at import time, *changing* the variable is
a schema change and must be followed by a migration, not just a restart. Switch
workflow for a non-default provider (e.g. ``ollama``/``nomic-embed-text`` ->
768, ``openai``/``text-embedding-3-small`` -> 1536)::

    # 1. match the columns to the provider's output width
    EMBEDDING_VECTOR_DIMENSIONS=768

    # 2. generate + apply the AlterField migrations for all five columns
    python manage.py makemigrations
    python manage.py migrate

    # 3. repopulate (pgvector cannot cast between widths, so existing vectors
    #    are discarded by the resize and must be regenerated)
    python manage.py backfill_embeddings

Before step 2 the mismatch is not silent: ``llm_adapter.checks`` reports it as
``llm_adapter.W001`` from ``manage.py check``, and
``manage.py verify_embedding_dimensions`` compares the *actual* DB column
types against the configured provider and exits non-zero on a mismatch.

Layering (ADR-01): this lives in ``persistence`` (Layer 0) deliberately.
``icd``/``memory``/``llm_adapter``/``application`` all sit above persistence
and may import it; persistence may not import them. Putting the constant in
``llm_adapter`` (Layer 1, where the providers live) would have inverted that.
"""
from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

#: Name of the environment variable that selects every embedding column width.
EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR = "EMBEDDING_VECTOR_DIMENSIONS"

#: Width used when :data:`EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR` is unset/blank.
#:
#: 384 == ``sentence-transformers``/``all-MiniLM-L6-v2``, the shipped default
#: ``EMBEDDING_PROVIDER`` (see ``llm_adapter.embedding_service``).
DEFAULT_EMBEDDING_VECTOR_DIMENSIONS = 384


def _resolve_embedding_vector_dimensions() -> int:
    """Resolve the embedding column width from the environment.

    Returns:
        The configured positive integer width, or
        :data:`DEFAULT_EMBEDDING_VECTOR_DIMENSIONS` when the environment
        variable is unset or blank.

    Raises:
        ImproperlyConfigured: If the variable is set to a value that is not a
            positive integer. ``ImproperlyConfigured`` (rather than a bare
            ``ValueError``) is used because this is a deployment-configuration
            error and it is the exception Django itself raises from settings
            loading, so the traceback points an operator at their environment
            rather than at a parsing bug in this module.
    """
    raw = os.environ.get(EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR)
    if raw is None or not raw.strip():
        return DEFAULT_EMBEDDING_VECTOR_DIMENSIONS

    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            f"{EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR}={raw!r} is not a valid "
            f"integer. Set it to your embedding provider's output width "
            f"(sentence-transformers=384, ollama/nomic-embed-text=768, "
            f"openai/text-embedding-3-small=1536) or leave it unset for the "
            f"default {DEFAULT_EMBEDDING_VECTOR_DIMENSIONS}."
        ) from exc

    if value <= 0:
        raise ImproperlyConfigured(
            f"{EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR}={value} must be a positive "
            f"vector width (e.g. 384 for sentence-transformers, 768 for "
            f"ollama, 1536 for openai)."
        )

    return value


#: Dimension of every ``VectorField`` in this project, resolved from the
#: :data:`EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR` environment variable at import
#: time (default :data:`DEFAULT_EMBEDDING_VECTOR_DIMENSIONS`). See the module
#: docstring for the switch workflow.
EMBEDDING_VECTOR_DIMENSIONS = _resolve_embedding_vector_dimensions()

__all__ = [
    "DEFAULT_EMBEDDING_VECTOR_DIMENSIONS",
    "EMBEDDING_VECTOR_DIMENSIONS",
    "EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR",
]
