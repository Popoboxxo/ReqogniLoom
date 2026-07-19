"""
SE-Auditor rule package — importing it self-registers every rule.

The RuleEngine imports this package once at construction time; each submodule
below registers its rule(s) via ``@register_rule`` as an import side effect.
A new rule-implementer agent adds its module here (one ``from . import ...``
line per new rule file) — see the guide in ``traceability/audit/registry.py``.

Currently implemented: TRACE-P7 (baseline-scope consistency). The remaining
rules from the §2.2 Pflichtmatrix (TRACE-P1/P1b/P2-P6, ARCH-003, VERIF-P8,
CONS-P9/P10) are implemented by follow-up agents against the same interface.
"""
from __future__ import annotations

from . import trace_p7  # noqa: F401  (registration side effect)

__all__ = ["trace_p7"]
