"""
Test settings for pytest — uses PostgreSQL test database via Docker Compose.
"""
from .settings import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'reqflow',
        'USER': 'reqflow',
        'PASSWORD': 'reqflow',
        'HOST': 'postgres',
        'PORT': '5432',
    }
}
