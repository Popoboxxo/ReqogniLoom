# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: waterkettle-scenario.spec.ts >> [WK-SCENARIO] Wasserkocher SE-Durchstich >> SN-1: Dashboard rendert die aktive Demo-Workspace-Karte
- Location: tests\waterkettle-scenario.spec.ts:295:7

# Error details

```
Error: apiRequestContext.post: connect ECONNREFUSED ::1:8000
Call log:
  - → POST http://localhost:8000/api/v1/auth/login/
    - user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.7827.55 Safari/537.36
    - accept: */*
    - accept-encoding: gzip,deflate,br
    - content-type: application/json
    - content-length: 44

```