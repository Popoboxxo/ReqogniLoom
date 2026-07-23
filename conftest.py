"""
Pytest configuration for REQ-016 C6-Custom-Fields tests.
"""
import os
import sys

# Set Django settings module before importing Django
os.environ['DJANGO_SETTINGS_MODULE'] = 'reqogniloom.settings'

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import pytest

@pytest.fixture(scope='session', autouse=True)
def django_db_setup():
    """Override database configuration for tests."""
    from django.conf import settings

    # Override to use SQLite instead of PostgreSQL
    settings.DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
