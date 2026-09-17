"""SA-32 — server-side refresh-token rotation state (SYSTEMAUDIT §4.6 F7).

Adds ``at_refresh_token``: one row per issued refresh JWT, carrying the ``jti``
(this token) and ``session_id`` (its rotation family) plus the ``used_at`` /
``revoked_at`` bits that make reuse detection possible.

ROLLOUT IMPACT — one forced re-login per active session
-------------------------------------------------------
Refresh tokens minted before this migration carry no ``jti``/``sid`` claims, so
``AuthenticationService.rotate_refresh_token`` cannot reason about them and
rejects them with ``invalid_token``. Every user holding a pre-deploy refresh
cookie therefore has to log in once more; the SPA already treats a failed
refresh as "fall through to the login screen", so this surfaces as a normal
login prompt, not an error.

The alternative — grandfathering claim-less tokens through — was rejected: it
would leave the exact vulnerability this migration closes exploitable for the
full 30-day refresh TTL after deploy, which is the entire window an attacker
with a stolen token cares about.

No RLS policy is attached. ``/auth/login/`` and ``/auth/refresh/`` write and
read this table before any tenant context exists (``authentication_classes =
[]``), exactly like ``at_api_key``; the standard policy would reject the INSERT
and match zero rows on read. Registered as a reviewed exception in
``persistence/tests/test_rls_coverage.py::RLS_EXEMPT_TABLES``. The rows hold no
credential material — only opaque identifiers, never the JWT or its signature.

Table growth is bounded by ``manage.py cleanup_expired_refresh_tokens``.

req_id : REQ-L2-AT-002, REQ-L3-AT001-001
"""

import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth_tenancy', '0011_rls_policies'),
        ('persistence', '0068_requirement_level_cascade_vocabulary'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RefreshToken',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('jti', models.UUIDField(db_index=True, unique=True)),
                ('session_id', models.UUIDField(db_index=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_reason', models.CharField(blank=True, default='', max_length=64)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refresh_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'at_refresh_token',
                'indexes': [models.Index(fields=['session_id', 'revoked_at'], name='idx_refresh_session_active'), models.Index(fields=['expires_at'], name='idx_refresh_expires')],
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
    ]
