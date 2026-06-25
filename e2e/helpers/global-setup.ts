import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  // Verify backend is reachable
  const response = await fetch('http://localhost:8000/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@example.com', password: 'admin12345' }),
  }).catch(() => null);

  if (!response || !response.ok) {
    console.warn('Backend not reachable — tests will run but may fail');
  }
}

export default globalSetup;
