"""Prompt-regression fixtures for the promptfoo export (plan D / D2.1).

The package holds the checked-in source of truth for prompt regression
scenarios (``cases/*.yaml``) and the loader/validator in :mod:`cases`.

It intentionally contains no Django models and no runtime behaviour: the
production code path (``application.prompt_resolver``) never imports this
package, so a broken case file can only fail the export/CI gate, never an
application request.
"""
