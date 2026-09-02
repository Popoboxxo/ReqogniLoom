"""Single source of truth for the project-wide pgvector embedding dimension.

Issue #794. Every ``VectorField`` in this codebase MUST declare its
``dimensions`` from :data:`EMBEDDING_VECTOR_DIMENSIONS` rather than from a
local integer literal. Before this module existed the dimension was
hardcoded independently in five places and they disagreed:

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
Requirement/TraceLink/IcdVersion and ``artifact.search``'s semantic pass was
permanently empty on every default deployment.

This module pins all five columns to the dimension the *default* provider
actually emits, so the shipped configuration works with no operator action.

Layering (ADR-01): this lives in ``persistence`` (Layer 0) deliberately.
``icd``/``memory``/``llm_adapter``/``application`` all sit above persistence
and may import it; persistence may not import them. Putting the constant in
``llm_adapter`` (Layer 1, where the providers live) would have inverted that.

Changing this value is a schema change: it requires an ``AlterField``
migration for every column listed above, and -- because pgvector cannot cast
between differing vector widths -- existing embeddings must be NULLed and
regenerated (``manage.py backfill_embeddings``).
"""
from __future__ import annotations

#: Dimension of every ``VectorField`` in this project.
#:
#: 384 == ``sentence-transformers``/``all-MiniLM-L6-v2``, the shipped default
#: ``EMBEDDING_PROVIDER`` (see ``llm_adapter.embedding_service``). Deployments
#: that switch to a provider with a different native width (``ollama``/
#: ``nomic-embed-text`` -> 768, ``openai``/``text-embedding-3-small`` -> 1536)
#: must change this constant AND generate the corresponding migrations;
#: ``llm_adapter.checks.check_embedding_dimensions`` reports the mismatch as a
#: startup system-check warning instead of letting it degrade silently.
EMBEDDING_VECTOR_DIMENSIONS = 384

__all__ = ["EMBEDDING_VECTOR_DIMENSIONS"]
