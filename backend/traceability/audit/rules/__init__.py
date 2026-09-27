"""
SE-Auditor rule package — importing it self-registers every rule.

The RuleEngine imports this package once at construction time; each submodule
below registers its rule(s) via ``@register_rule`` as an import side effect.
A new rule-implementer agent adds its module here (one ``from . import ...``
line per new rule file) — see the guide in ``traceability/audit/registry.py``.

Fully implemented (§2.2 Pflichtmatrix): TRACE-P1/P1b/P2/P3
(trace_derivation_allocation), TRACE-P4/P5/ARCH-003 (decomposition_consistency),
TRACE-P6/VERIF-P8/CONS-P9/CONS-P10 (coverage_consistency), and TRACE-P7
(trace_p7, baseline-scope consistency), plus VAL-P1 (validation_goals).

ADR-005 removed CONS-P11 (level_progression). It asserted that
``Requirement.level`` agrees with the decomposition graph, and the same ADR made
``level`` **derived from** that graph — so the rule could never fire. This is the
same argument ``hierarchy.py`` already makes about TRACE-P5's ``decomposes``-
only read ("feeding it normalised edges would make the rule tautologically
true"). The attribute itself stays: ``level == L4`` is the only L4 filter
TRACE-P5, ARCH-003 and VERIF-P8 have. Only the rule went.
"""
from __future__ import annotations

from . import coverage_consistency  # noqa: F401  (registration side effect)
from . import decomposition_consistency  # noqa: F401  (registration side effect)
from . import trace_derivation_allocation  # noqa: F401  (registration side effect)
from . import trace_p7  # noqa: F401  (registration side effect)
from . import validation_goals  # noqa: F401  (registration side effect)

__all__ = [
    "coverage_consistency",
    "decomposition_consistency",
    "trace_derivation_allocation",
    "trace_p7",
    "validation_goals",
]
