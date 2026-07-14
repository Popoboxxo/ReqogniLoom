"""Pytest configuration and shared fixtures for the ReqFlow backend suite.

This root conftest intentionally defines no fixtures. The scaffolding fixtures
that once lived here (``db_access``, ``single_tenant``, ``api_client``) were
never referenced by any test and have been removed (REQ-068). Cross-cutting
fixtures now live in the per-app ``<app>/tests/conftest.py`` files closest to
the tests that use them.

Add a fixture here only when it is genuinely shared across multiple app test
suites, and document what it provides directly above its definition.
"""
from __future__ import annotations
