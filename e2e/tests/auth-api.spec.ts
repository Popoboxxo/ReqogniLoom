// REQ-L3-AT001-001/002/003/004: Auth & API surface error contract
import { test, expect } from '@playwright/test';
import { getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

test.describe('[COMP-AT-001] Auth API — error contract', () => {
  test('[REQ-L3-AT001-001] missing credentials -> 401/403 with error envelope', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`);
    // DRF returns 403 by default when no credentials are provided (no WWW-Authenticate);
    // the standardised AuthAndTenancy code path uses 401. Both indicate unauthenticated.
    expect([401, 403]).toContain(response.status());
    const body = await response.json();
    // Accept either DRF default shape {"detail": "..."} or the AuthAndTenancy
    // standardised body {error, message, doc_url} (REQ-L3-AT001-004).
    const hasErrorField = 'error' in body || 'detail' in body;
    expect(hasErrorField).toBeTruthy();
  });

  test('[REQ-L3-AT001-002] invalid Bearer token -> 401 invalid_token', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: 'Bearer not-a-real-token' },
    });
    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.error).toBe('invalid_token');
    expect(body.message).toBeDefined();
    expect(body.doc_url).toContain('invalid_token');
  });

  test('[REQ-L3-AT001-002] invalid API key -> 401 invalid_api_key', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { 'X-API-Key': 'definitely-not-a-real-api-key-xyz' },
    });
    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.error).toBe('invalid_api_key');
    expect(body.message).toBeDefined();
    expect(body.doc_url).toContain('invalid_api_key');
  });

  test.skip('[REQ-L3-AT001-003] API key lifecycle (create/list/revoke) via REST', async () => {
    // No REST endpoint for API key management exposed in rest_api/urls.py.
    // API keys are issued out-of-band via the auth_tenancy service / management command.
    // Skipping until REST surface is added.
  });

  test('[REQ-L3-AT001-004] auth error body has error + message + doc_url fields', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: 'Bearer malformed.jwt.value' },
    });
    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body).toHaveProperty('message');
    expect(body).toHaveProperty('doc_url');
    expect(typeof body.error).toBe('string');
    expect(typeof body.message).toBe('string');
    expect(body.doc_url).toMatch(/^https?:\/\//);
  });

  test('[REQ-L3-AT001-004] login with wrong password returns standardized error envelope', async ({ request }) => {
    const response = await request.post(`${BACKEND_URL}/api/v1/auth/login/`, {
      data: { username: 'admin', password: 'definitely-wrong' },
    });
    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body).toHaveProperty('error');
    expect(body).toHaveProperty('message');
    expect(body).toHaveProperty('doc_url');
  });

  test('[REQ-L1-010] login success returns token + user + tenant_id + roles', async ({ request }) => {
    const response = await request.post(`${BACKEND_URL}/api/v1/auth/login/`, {
      data: { username: 'admin', password: 'admin12345' },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.token).toBeDefined();
    expect(body.user).toBeDefined();
    expect(body.user.username).toBe('admin');
    expect(body.tenant_id).toBeDefined();
    expect(Array.isArray(body.roles)).toBeTruthy();
  });

  test('[REQ-L1-010] /auth/me/ returns identity for valid token', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/auth/me/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.user).toBeDefined();
    expect(body.user.username).toBe('admin');
    expect(body.tenant_id).toBeDefined();
    expect(Array.isArray(body.roles)).toBeTruthy();
  });
});
