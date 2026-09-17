# Test Layout Convention

This document defines the test file organization for the ReqogniLoom frontend.

## Primary Pattern: Central Test Directory

Test files for React components are placed in the **central `src/test/` directory**, organized by feature or module name.

```
src/
├── test/
│   ├── LoginPage.test.tsx
│   ├── WorkspaceContext.test.tsx
│   ├── GlossaryView.test.tsx
│   └── ...
├── components/
│   ├── LoginPage.tsx
│   ├── WorkspaceContext.tsx
│   └── ...
```

**Rationale:**
- Centralized test discovery and maintenance
- Clear separation between implementation and tests
- Easier to manage shared test utilities and fixtures

## Secondary Pattern: Co-Located Tests for Utilities

For utilities, services, and API layers, tests may be co-located in the same directory as the source file:

```
src/api/
├── client.ts
├── client.test.ts
├── diagrams.ts
├── diagrams.test.ts
```

**Rationale:**
- Tight coupling between utility and its test
- Simpler to maintain for small, focused modules

## Vitest Configuration

The `vite.config.ts` is configured to discover tests using the pattern:

```
include: ["src/**/*.{test,spec}.{ts,tsx}"]
```

This automatically picks up both central and co-located tests.

## Guidelines

- **Default:** Place component tests in `src/test/`
- **Exception:** Co-locate tests for utilities, APIs, and services in their source directory
- **File naming:** Use `.test.ts` or `.test.tsx` suffix (preferred over `.spec.*`)
- **Setup files:** Common test utilities and setup are in `src/test/setup.ts`
