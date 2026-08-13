# Hermes IDE Plugin — Requirements MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working Hermes IDE plugin that lets a user browse, search, view, create, and edit ReqogniLoom requirements from a sidebar panel, built and locally verified inside this repo.

**Architecture:** A single sidebar panel (`reqogniloom-panel`) with an internal view state machine (`connect → list → detail → form`), backed by a module-level state store with pub/sub (mirroring the `hermes-hq/plugins` `github` reference plugin's proven pattern) and a typed API client (`api.ts`) that talks to ReqogniLoom's existing REST API using API-key auth (`X-API-Key` header, verified against `AuthTenancyAuthentication`, which already covers the whole `/api/v1/` surface, not just MCP).

**Tech Stack:** TypeScript 5.4 (strict), React 18 (classic JSX runtime, `React.createElement`), Vite 8 (IIFE library build, React externalized), Vitest 4 — all pinned to match `hermes-hq/plugins`' own `templates/basic` and `plugins/json-formatter` conventions exactly (checked 2026-08-13).

**Spec:** `docs/superpowers/specs/2026-08-13-hermes-ide-plugin-design.md`

## Global Constraints

- Plugin source lives at `integrations/hermes-plugin/reqogniloom/` in **this** repo (ReqogniLoom) — not a fork of `hermes-hq/plugins`. Publishing there is a later, separate round.
- No `contributes.settings` entry for the API key or connection info — persisted via `api.storage` only, entered through an in-panel Connect screen (mirrors the `github` reference plugin's own token-handling, not the manifest settings UI).
- `permissions` in `hermes-plugin.json`: exactly `["network", "storage"]` — nothing more.
- `api.network.fetch()`'s actual return shape is ambiguous between the official docs (`Promise<string>`) and the `github` reference plugin's own bundled type (`Promise<Response>`). `api.ts`'s `parseNetworkResult()` must handle both — do not assume one and skip the other.
- `GET /api/v1/requirements/` requires a `workspace_id` query parameter (confirmed in `backend/rest_api/query_params.py::parse_uuid_param` docstring: "Validate a **required** UUID request parameter"). The Connect flow must resolve a `workspace_id` before any requirement call — via `GET /api/v1/workspaces/`, which doubles as the API-key validation step.
- `status` on `Requirement` is read-only (server-owned WorkflowEngine mirror, REQ-143) — never send it in create/edit payloads, never render an editable status field.
- Error envelope shape (from `backend/rest_api/serializers.py::build_error_response` / `backend/rest_api/openapi.py::ErrorResponseSerializer`, fixed project-wide contract): `{"error": {"code": string, "message": string, "details": [{"field": string, "errors": string[]}]}}`.
- Pagination envelope shape (from `backend/rest_api/serializers.py::StandardPagination`, fixed project-wide contract): `{"count": number, "next": string|null, "previous": string|null, "results": T[]}`. Default page size 25, max 100.
- All CSS in React components uses the host app's CSS custom properties (`--bg-1`, `--bg-2`, `--text-1`, `--text-2`, `--accent`, `--red`, `--border`, `--radius-sm`, `--font-mono`, `--text-xs`, `--text-sm`) per `hermes-hq/plugins`' `CONTRIBUTING.md` review criteria — never a hardcoded color.
- No unit tests for React view components — matches this ecosystem's own established convention (`plugins/json-formatter`'s only test file mocks React away entirely and tests state/logic only; `plugins/github` has no test file at all). Unit tests target `api.ts` and `state.ts` only. View components are verified manually in Task 9.

---

### Task 1: Scaffold the plugin package and get it building

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/hermes-plugin.json`
- Create: `integrations/hermes-plugin/reqogniloom/package.json`
- Create: `integrations/hermes-plugin/reqogniloom/tsconfig.json`
- Create: `integrations/hermes-plugin/reqogniloom/vite.config.ts`
- Create: `integrations/hermes-plugin/reqogniloom/vitest.config.ts`
- Create: `integrations/hermes-plugin/reqogniloom/.gitignore`
- Create: `integrations/hermes-plugin/reqogniloom/src/activate.ts` (stub — real implementation in Task 7)
- Create: `integrations/hermes-plugin/reqogniloom/src/ReqogniLoomPanel.tsx` (stub — real implementation in Task 5/6)

**Interfaces:**
- Produces: a buildable Vite IIFE bundle at `dist/index.js`, and an `npm test` script wired to Vitest, that every later task's `npm run build` / `npm test` depends on.

- [ ] **Step 1: Create the manifest**

```json
// integrations/hermes-plugin/reqogniloom/hermes-plugin.json
{
  "id": "reqogniloom.reqogniloom",
  "name": "ReqogniLoom",
  "version": "0.1.0",
  "description": "Browse, search, and manage ReqogniLoom requirements from Hermes IDE",
  "author": "ReqogniLoom",
  "main": "dist/index.js",
  "activationEvents": [
    { "type": "onStartup" }
  ],
  "contributes": {
    "commands": [
      {
        "command": "reqogniloom.open",
        "title": "Open ReqogniLoom",
        "category": "ReqogniLoom"
      }
    ],
    "panels": [
      {
        "id": "reqogniloom-panel",
        "name": "ReqogniLoom",
        "side": "left",
        "icon": "<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><rect x=\"2.5\" y=\"2.5\" width=\"13\" height=\"13\" rx=\"1.5\"/><path d=\"M5.5 6.5h7M5.5 9h7M5.5 11.5h4.5\"/></svg>"
      }
    ],
    "statusBarItems": [
      {
        "id": "reqogniloom.status",
        "text": "ReqogniLoom",
        "tooltip": "Open ReqogniLoom panel",
        "alignment": "right",
        "priority": 20,
        "command": "reqogniloom.open"
      }
    ]
  },
  "engines": {
    "hermes": ">=0.5.20"
  },
  "permissions": ["network", "storage"]
}
```

Version is hand-set to `0.1.0` here; a later distribution round (out of this plan's scope per the spec) will wire it to this repo's `VERSION` file the way `dist/plugins/claude-code`'s builder does. Not automated here since there is no code-generation step for this plugin — it's hand-written source, not a template render.

- [ ] **Step 2: Create `package.json`**

```json
// integrations/hermes-plugin/reqogniloom/package.json
{
  "name": "@reqogniloom/hermes-plugin",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "vite build",
    "dev": "vite build --watch",
    "test": "vitest run"
  },
  "devDependencies": {
    "@types/react": "^19.2.14",
    "typescript": "^5.4.0",
    "vite": "^8.0.0",
    "vitest": "^4.1.0"
  },
  "peerDependencies": {
    "react": "^18.0.0"
  }
}
```

- [ ] **Step 3: Create `tsconfig.json`**

```json
// integrations/hermes-plugin/reqogniloom/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react",
    "jsxFactory": "React.createElement",
    "jsxFragmentFactory": "React.Fragment",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "declaration": false,
    "rootDir": "src"
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `vite.config.ts`**

```typescript
// integrations/hermes-plugin/reqogniloom/vite.config.ts
import { defineConfig } from "vite";
import { resolve } from "path";
import manifest from "./hermes-plugin.json";

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, "src/activate.ts"),
      formats: ["iife"],
      name: "__hermes_plugin__",
      fileName: () => "index.js",
    },
    rollupOptions: {
      external: ["react"],
      output: {
        globals: { react: "React" },
        footer: `if (typeof window !== "undefined") { window.__hermesPlugins = window.__hermesPlugins || {}; window.__hermesPlugins["${manifest.id}"] = { activate: __hermes_plugin__.activate, deactivate: __hermes_plugin__.deactivate }; }`,
      },
    },
    outDir: "dist",
    emptyOutDir: true,
    minify: false,
  },
});
```

- [ ] **Step 5: Create `vitest.config.ts`**

```typescript
// integrations/hermes-plugin/reqogniloom/vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
  },
});
```

- [ ] **Step 6: Create `.gitignore`**

```
# integrations/hermes-plugin/reqogniloom/.gitignore
node_modules/
dist/
```

- [ ] **Step 7: Create a stub entry point and panel so the build has something to compile**

```typescript
// integrations/hermes-plugin/reqogniloom/src/activate.ts
import type { HermesPluginAPI } from "./hermes-api-types";
import { ReqogniLoomPanel } from "./ReqogniLoomPanel";

let hermesAPI: HermesPluginAPI | null = null;

export function getAPI(): HermesPluginAPI {
  if (!hermesAPI) throw new Error("ReqogniLoom plugin not activated");
  return hermesAPI;
}

export function activate(api: HermesPluginAPI) {
  hermesAPI = api;
  api.ui.registerPanel("reqogniloom-panel", ReqogniLoomPanel);
  api.subscriptions.push(
    api.commands.register("reqogniloom.open", () => {
      api.ui.showPanel("reqogniloom-panel");
    })
  );
}

export function deactivate() {
  hermesAPI = null;
}
```

```typescript
// integrations/hermes-plugin/reqogniloom/src/hermes-api-types.ts
// Local declaration of the subset of HermesPluginAPI this plugin uses.
// The host app injects the real implementation at runtime; there is no
// npm package to import these from (see hermes-hq/plugins' own reference
// plugins, which all declare this interface locally rather than depending
// on a shared types package).
export interface Disposable {
  dispose(): void;
}

export interface PluginPanelProps {
  pluginId: string;
  panelId: string;
}

export interface HermesPluginAPI {
  ui: {
    registerPanel(panelId: string, component: React.ComponentType<PluginPanelProps>): Disposable;
    showPanel(panelId: string): void;
    hidePanel(panelId: string): void;
    togglePanel(panelId: string): void;
    showToast(message: string, options?: { type?: "info" | "success" | "warning" | "error"; duration?: number }): void;
    updateStatusBarItem(itemId: string, update: { text?: string; tooltip?: string; visible?: boolean }): void;
  };
  commands: {
    register(commandId: string, handler: () => void | Promise<void>): Disposable;
    execute(commandId: string): Promise<void>;
  };
  storage: {
    get(key: string): Promise<string | null>;
    set(key: string, value: string): Promise<void>;
    delete(key: string): Promise<void>;
  };
  network: {
    fetch(url: string, options?: RequestInit): Promise<unknown>;
  };
  subscriptions: Disposable[];
}
```

```typescript
// integrations/hermes-plugin/reqogniloom/src/ReqogniLoomPanel.tsx
import * as React from "react";
import type { PluginPanelProps } from "./hermes-api-types";

export function ReqogniLoomPanel(_props: PluginPanelProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        padding: "16px",
        minWidth: "260px",
        maxWidth: "400px",
        background: "var(--bg-1)",
        color: "var(--text-1)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-sm)",
      }}
    >
      ReqogniLoom
    </div>
  );
}
```

- [ ] **Step 8: Install dependencies and verify the build**

Run: `cd integrations/hermes-plugin/reqogniloom && npm install && npm run build`
Expected: `dist/index.js` is produced, no TypeScript errors.

- [ ] **Step 9: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/
git commit -m "feat: scaffold Hermes IDE plugin package for ReqogniLoom"
```

---

### Task 2: API client module (`api.ts`)

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/src/api.ts`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/api.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks except the `network.fetch` shape from `HermesPluginAPI` (Task 1's `hermes-api-types.ts`).
- Produces (consumed by Task 3/4's `state.ts`):
  - `interface Connection { baseUrl: string; apiKey: string; workspaceId: string }`
  - `interface Workspace { id: string; name: string }`
  - `interface Requirement { id, workspace_id, parent_id, title, description, acceptance_criteria, category, status, type, complexity_fibonacci, verification_method, level, uid, version, change_reason?, created_at, updated_at }`
  - `interface RequirementListResponse { count: number; next: string | null; previous: string | null; results: Requirement[] }`
  - `class ReqogniLoomApiError extends Error { status: number; envelope: ErrorEnvelope | null }`
  - `async function listWorkspaces(network, connection: Omit<Connection, "workspaceId">): Promise<Workspace[]>`
  - `async function listRequirements(network, connection: Connection, params?: { search?: string; page?: number; pageSize?: number }): Promise<RequirementListResponse>`
  - `async function getRequirement(network, connection: Connection, id: string): Promise<Requirement>`
  - `async function createRequirement(network, connection: Connection, input: CreateRequirementInput): Promise<Requirement>`
  - `async function updateRequirement(network, connection: Connection, id: string, input: UpdateRequirementInput): Promise<Requirement>`

- [ ] **Step 1: Write the failing tests**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/api.test.ts
import { describe, it, expect, vi } from "vitest";
import {
  listWorkspaces,
  listRequirements,
  getRequirement,
  createRequirement,
  updateRequirement,
  ReqogniLoomApiError,
  type HermesNetworkAPI,
  type Connection,
} from "../api";

const connection: Connection = {
  baseUrl: "https://reqo.example.com",
  apiKey: "reqlo_test123",
  workspaceId: "11111111-1111-1111-1111-111111111111",
};

function mockNetwork(impl: (url: string, options?: RequestInit) => unknown): HermesNetworkAPI {
  return { fetch: vi.fn(impl) };
}

describe("listWorkspaces", () => {
  it("sends X-API-Key header and returns parsed workspaces (string-return shape)", async () => {
    const network = mockNetwork((url, options) => {
      expect(url).toBe("https://reqo.example.com/api/v1/workspaces/");
      expect((options?.headers as Record<string, string>)["X-API-Key"]).toBe("reqlo_test123");
      return JSON.stringify({
        count: 1,
        next: null,
        previous: null,
        results: [{ id: "w1", name: "Demo" }],
      });
    });
    const workspaces = await listWorkspaces(network, {
      baseUrl: connection.baseUrl,
      apiKey: connection.apiKey,
    });
    expect(workspaces).toEqual([{ id: "w1", name: "Demo" }]);
  });

  it("supports the Response-return shape too", async () => {
    const network = mockNetwork(() =>
      new Response(
        JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
        { status: 200 }
      )
    );
    const workspaces = await listWorkspaces(network, {
      baseUrl: connection.baseUrl,
      apiKey: connection.apiKey,
    });
    expect(workspaces).toEqual([]);
  });

  it("throws ReqogniLoomApiError with the error envelope on 401 (Response shape)", async () => {
    const network = mockNetwork(
      () =>
        new Response(
          JSON.stringify({ error: { code: "AUTHENTICATION_FAILED", message: "Invalid API key", details: [] } }),
          { status: 401 }
        )
    );
    await expect(
      listWorkspaces(network, { baseUrl: connection.baseUrl, apiKey: connection.apiKey })
    ).rejects.toMatchObject({
      status: 401,
      envelope: { error: { code: "AUTHENTICATION_FAILED" } },
    });
  });

  it("throws ReqogniLoomApiError on 401 in the string-return shape too (no HTTP status observable)", async () => {
    const network = mockNetwork(() =>
      JSON.stringify({ error: { code: "AUTHENTICATION_FAILED", message: "Invalid API key", details: [] } })
    );
    await expect(
      listWorkspaces(network, { baseUrl: connection.baseUrl, apiKey: connection.apiKey })
    ).rejects.toBeInstanceOf(ReqogniLoomApiError);
  });
});

describe("listRequirements", () => {
  it("builds the query string with workspace_id, page, page_size, and search", async () => {
    const network = mockNetwork((url) => {
      expect(url).toContain("/api/v1/requirements/?");
      expect(url).toContain(`workspace_id=${connection.workspaceId}`);
      expect(url).toContain("page=2");
      expect(url).toContain("page_size=25");
      expect(url).toContain("search=login");
      return JSON.stringify({ count: 0, next: null, previous: null, results: [] });
    });
    await listRequirements(network, connection, { page: 2, search: "login" });
  });

  it("omits search when not provided", async () => {
    const network = mockNetwork((url) => {
      expect(url).not.toContain("search=");
      return JSON.stringify({ count: 0, next: null, previous: null, results: [] });
    });
    await listRequirements(network, connection);
  });
});

describe("getRequirement", () => {
  it("fetches the single-requirement endpoint", async () => {
    const network = mockNetwork((url) => {
      expect(url).toBe("https://reqo.example.com/api/v1/requirements/req-1/");
      return JSON.stringify({ id: "req-1", title: "Login must work" });
    });
    const req = await getRequirement(network, connection, "req-1");
    expect(req.id).toBe("req-1");
  });
});

describe("createRequirement", () => {
  it("POSTs with workspace_id injected and returns the created requirement", async () => {
    const network = mockNetwork((url, options) => {
      expect(options?.method).toBe("POST");
      const body = JSON.parse(options!.body as string);
      expect(body.workspace_id).toBe(connection.workspaceId);
      expect(body.title).toBe("New requirement");
      return JSON.stringify({ id: "req-2", title: "New requirement" });
    });
    const req = await createRequirement(network, connection, { title: "New requirement" });
    expect(req.id).toBe("req-2");
  });

  it("surfaces field-level 400 errors via the standard envelope", async () => {
    const network = mockNetwork(
      () =>
        new Response(
          JSON.stringify({
            error: {
              code: "VALIDATION_ERROR",
              message: "Validation failed",
              details: [{ field: "title", errors: ["This field is required."] }],
            },
          }),
          { status: 400 }
        )
    );
    await expect(createRequirement(network, connection, { title: "" })).rejects.toMatchObject({
      status: 400,
      envelope: {
        error: { details: [{ field: "title", errors: ["This field is required."] }] },
      },
    });
  });
});

describe("updateRequirement", () => {
  it("PATCHes without workspace_id (not part of update payload)", async () => {
    const network = mockNetwork((url, options) => {
      expect(url).toBe("https://reqo.example.com/api/v1/requirements/req-1/");
      expect(options?.method).toBe("PATCH");
      const body = JSON.parse(options!.body as string);
      expect(body).not.toHaveProperty("workspace_id");
      expect(body.title).toBe("Updated title");
      return JSON.stringify({ id: "req-1", title: "Updated title" });
    });
    const req = await updateRequirement(network, connection, "req-1", { title: "Updated title" });
    expect(req.title).toBe("Updated title");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd integrations/hermes-plugin/reqogniloom && npm test`
Expected: FAIL — `Cannot find module '../api'` (file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

```typescript
// integrations/hermes-plugin/reqogniloom/src/api.ts

export interface HermesNetworkAPI {
  fetch(url: string, options?: RequestInit): Promise<unknown>;
}

export interface Connection {
  baseUrl: string;
  apiKey: string;
  workspaceId: string;
}

export interface Workspace {
  id: string;
  name: string;
}

export type RequirementType = "SyReq" | "UseCase" | "FeatureReq";
export type VerificationMethod = "Test" | "Review" | "Analysis" | "Inspection" | "Demonstration";

export interface Requirement {
  id: string;
  workspace_id: string;
  parent_id: string | null;
  title: string;
  description: string;
  acceptance_criteria: string;
  category: string;
  status: string;
  type: RequirementType;
  complexity_fibonacci: number | null;
  verification_method: VerificationMethod | null;
  level: number | null;
  uid: string | null;
  version: number;
  change_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface RequirementListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Requirement[];
}

interface WorkspaceListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Workspace[];
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: { field: string; errors: string[] }[];
  };
}

export interface CreateRequirementInput {
  title: string;
  description?: string;
  acceptance_criteria?: string;
  category?: string;
  type?: RequirementType;
  complexity_fibonacci?: number;
  verification_method?: VerificationMethod;
  level?: number;
  parent_id?: string;
}

export type UpdateRequirementInput = Partial<CreateRequirementInput> & { change_reason?: string };

export class ReqogniLoomApiError extends Error {
  status: number;
  envelope: ErrorEnvelope | null;

  constructor(status: number, envelope: ErrorEnvelope | null, message: string) {
    super(message);
    this.name = "ReqogniLoomApiError";
    this.status = status;
    this.envelope = envelope;
  }
}

// api.network.fetch()'s actual return shape is ambiguous: the official docs
// (hermes-hq/plugins/docs/PLUGIN-API.md, checked 2026-08-13) say it returns
// Promise<string> (response body as text, no status code observable), but
// the `github` reference plugin's own bundled HermesPluginAPI type declares
// Promise<Response> instead. Handle both rather than gambling on one — see
// plan Task 9 for where this gets confirmed empirically against a real
// Hermes IDE build.
async function parseNetworkResult(raw: unknown): Promise<{ status: number; body: unknown }> {
  if (typeof raw === "string") {
    let body: unknown = null;
    try {
      body = raw ? JSON.parse(raw) : null;
    } catch {
      body = null;
    }
    const isErrorShaped = !!(body && typeof body === "object" && "error" in (body as Record<string, unknown>));
    return { status: isErrorShaped ? 400 : 200, body };
  }
  const res = raw as Response;
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  return { status: res.status, body };
}

async function reqloFetch(
  network: HermesNetworkAPI,
  baseUrl: string,
  apiKey: string,
  path: string,
  options: RequestInit = {}
): Promise<unknown> {
  const url = `${baseUrl.replace(/\/$/, "")}${path}`;
  const raw = await network.fetch(url, {
    ...options,
    headers: {
      "X-API-Key": apiKey,
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  const { status, body } = await parseNetworkResult(raw);
  if (status < 200 || status >= 300) {
    const envelope =
      body && typeof body === "object" && "error" in (body as Record<string, unknown>)
        ? (body as ErrorEnvelope)
        : null;
    throw new ReqogniLoomApiError(status, envelope, envelope?.error.message ?? `HTTP ${status}`);
  }
  return body;
}

export async function listWorkspaces(
  network: HermesNetworkAPI,
  credentials: { baseUrl: string; apiKey: string }
): Promise<Workspace[]> {
  const body = await reqloFetch(network, credentials.baseUrl, credentials.apiKey, "/api/v1/workspaces/");
  return (body as WorkspaceListResponse).results;
}

export async function listRequirements(
  network: HermesNetworkAPI,
  connection: Connection,
  params: { search?: string; page?: number; pageSize?: number } = {}
): Promise<RequirementListResponse> {
  const query = new URLSearchParams();
  query.set("workspace_id", connection.workspaceId);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 25));
  if (params.search) query.set("search", params.search);
  const body = await reqloFetch(
    network,
    connection.baseUrl,
    connection.apiKey,
    `/api/v1/requirements/?${query.toString()}`
  );
  return body as RequirementListResponse;
}

export async function getRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  id: string
): Promise<Requirement> {
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, `/api/v1/requirements/${id}/`);
  return body as Requirement;
}

export async function createRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  input: CreateRequirementInput
): Promise<Requirement> {
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, "/api/v1/requirements/", {
    method: "POST",
    body: JSON.stringify({ ...input, workspace_id: connection.workspaceId }),
  });
  return body as Requirement;
}

export async function updateRequirement(
  network: HermesNetworkAPI,
  connection: Connection,
  id: string,
  input: UpdateRequirementInput
): Promise<Requirement> {
  const body = await reqloFetch(network, connection.baseUrl, connection.apiKey, `/api/v1/requirements/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return body as Requirement;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npm test`
Expected: PASS — all `api.test.ts` cases green.

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/api.ts integrations/hermes-plugin/reqogniloom/src/__tests__/api.test.ts
git commit -m "feat: add ReqogniLoom API client for Hermes plugin"
```

---

### Task 3: State module — connect flow and requirements list

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/src/state.ts`
- Test: `integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts`

**Interfaces:**
- Consumes: everything exported from `api.ts` (Task 2) — `listWorkspaces`, `listRequirements`, `Connection`, `Workspace`, `Requirement`, `ReqogniLoomApiError`.
- Consumes: `HermesPluginAPI` shape from `hermes-api-types.ts` (Task 1), specifically `.storage` and `.network`.
- Produces (consumed by Task 4 and the UI components in Task 5/6):
  - `type View = "connect" | "list" | "detail" | "form"`
  - `interface AppState { view, connection, pendingCredentials, pendingWorkspaces, connectError, connecting, requirements, requirementsCount, requirementsPage, hasMoreRequirements, searchTerm, listLoading, listError, selectedRequirement, detailLoading, detailError }` (full shape below — Task 4 extends this with a `form` field)
  - `function initState(api: HermesPluginAPI): Promise<void>`
  - `function getState(): AppState`
  - `function subscribe(listener: () => void): () => void`
  - `function connectWithCredentials(baseUrl: string, apiKey: string): Promise<void>`
  - `function chooseWorkspace(workspace: Workspace): Promise<void>`
  - `function disconnect(): Promise<void>`
  - `function loadRequirements(page?: number): Promise<void>`
  - `function setSearchTerm(term: string): void`

- [ ] **Step 1: Write the failing tests**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as apiModule from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof apiModule>("../api");
  return {
    ...actual,
    listWorkspaces: vi.fn(),
    listRequirements: vi.fn(),
  };
});

import { initState, getState, subscribe, connectWithCredentials, chooseWorkspace, disconnect, loadRequirements, setSearchTerm } from "../state";
import { ReqogniLoomApiError } from "../api";

function createMockHermesAPI(overrides?: { storedConnection?: string | null }) {
  const store = new Map<string, string>();
  if (overrides?.storedConnection) store.set("reqogniloom-connection", overrides.storedConnection);
  return {
    ui: {
      registerPanel: vi.fn(),
      showPanel: vi.fn(),
      hidePanel: vi.fn(),
      togglePanel: vi.fn(),
      showToast: vi.fn(),
      updateStatusBarItem: vi.fn(),
    },
    commands: { register: vi.fn(() => ({ dispose: vi.fn() })), execute: vi.fn() },
    storage: {
      get: vi.fn((key: string) => Promise.resolve(store.get(key) ?? null)),
      set: vi.fn((key: string, value: string) => {
        store.set(key, value);
        return Promise.resolve();
      }),
      delete: vi.fn((key: string) => {
        store.delete(key);
        return Promise.resolve();
      }),
    },
    network: { fetch: vi.fn() },
    subscriptions: [],
  };
}

const workspace = { id: "w1", name: "Demo" };
const connection = { baseUrl: "https://reqo.example.com", apiKey: "reqlo_x", workspaceId: "w1" };

beforeEach(() => {
  vi.clearAllMocks();
});

describe("initState", () => {
  it("starts in the connect view when nothing is stored", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);
    expect(getState().view).toBe("connect");
    expect(getState().connection).toBeNull();
  });

  it("restores a stored connection and loads the list directly", async () => {
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI({ storedConnection: JSON.stringify(connection) });
    await initState(api as never);
    expect(getState().view).toBe("list");
    expect(getState().connection).toEqual(connection);
    expect(apiModule.listRequirements).toHaveBeenCalled();
  });
});

describe("connectWithCredentials", () => {
  it("auto-selects the single workspace and moves to list", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().view).toBe("list");
    expect(getState().connection).toEqual(connection);
    expect(api.storage.set).toHaveBeenCalledWith("reqogniloom-connection", JSON.stringify(connection));
  });

  it("shows a workspace picker when there is more than one", async () => {
    const second = { id: "w2", name: "Second" };
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace, second]);
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().view).toBe("connect");
    expect(getState().pendingWorkspaces).toEqual([workspace, second]);
    expect(getState().connection).toBeNull();
  });

  it("sets connectError with no workspaces accessible", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([]);
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().connectError).toMatch(/no workspaces/i);
  });

  it("sets connectError on 401", async () => {
    vi.mocked(apiModule.listWorkspaces).mockRejectedValue(new ReqogniLoomApiError(401, null, "Invalid API key"));
    const api = createMockHermesAPI();
    await initState(api as never);

    await connectWithCredentials("https://reqo.example.com", "bad-key");

    expect(getState().connectError).toBe("Invalid API key");
    expect(getState().connecting).toBe(false);
  });
});

describe("chooseWorkspace", () => {
  it("finalizes the connection and loads the list", async () => {
    const second = { id: "w2", name: "Second" };
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace, second]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await chooseWorkspace(second);

    expect(getState().view).toBe("list");
    expect(getState().connection?.workspaceId).toBe("w2");
    expect(api.storage.set).toHaveBeenCalledWith(
      "reqogniloom-connection",
      JSON.stringify({ ...connection, workspaceId: "w2" })
    );
  });
});

describe("loadRequirements", () => {
  it("populates the list on success", async () => {
    const req = { id: "r1", title: "Login" };
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [req as never],
    });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    expect(getState().requirements).toEqual([req]);
    expect(getState().requirementsCount).toBe(1);
    expect(getState().listLoading).toBe(false);
  });

  it("disconnects and returns to the connect view on 401", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements)
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockRejectedValueOnce(new ReqogniLoomApiError(401, null, "Invalid API key"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    expect(getState().view).toBe("list");

    await loadRequirements();

    expect(getState().view).toBe("connect");
    expect(getState().connection).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });

  it("sets listError on a non-auth failure and stays on the list view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements)
      .mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] })
      .mockRejectedValueOnce(new ReqogniLoomApiError(500, null, "Server error"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await loadRequirements();

    expect(getState().view).toBe("list");
    expect(getState().listError).toBe("Server error");
  });
});

describe("setSearchTerm / loadRequirements interaction", () => {
  it("reloads page 1 with the search term applied", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    setSearchTerm("login");
    await loadRequirements();

    expect(apiModule.listRequirements).toHaveBeenLastCalledWith(
      expect.anything(),
      connection,
      expect.objectContaining({ search: "login", page: 1 })
    );
  });
});

describe("disconnect", () => {
  it("clears storage and resets to the connect view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await disconnect();

    expect(getState().view).toBe("connect");
    expect(getState().connection).toBeNull();
    expect(api.storage.delete).toHaveBeenCalledWith("reqogniloom-connection");
  });
});

describe("subscribe", () => {
  it("notifies listeners on state change", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([]);
    const api = createMockHermesAPI();
    await initState(api as never);
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);

    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    expect(listener).toHaveBeenCalled();

    listener.mockClear();
    unsubscribe();
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    expect(listener).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd integrations/hermes-plugin/reqogniloom && npm test`
Expected: FAIL — `Cannot find module '../state'`.

- [ ] **Step 3: Write the implementation**

```typescript
// integrations/hermes-plugin/reqogniloom/src/state.ts
import type { HermesPluginAPI } from "./hermes-api-types";
import {
  listWorkspaces,
  listRequirements,
  type Connection,
  type Workspace,
  type Requirement,
  ReqogniLoomApiError,
} from "./api";

const STORAGE_KEY = "reqogniloom-connection";

export type View = "connect" | "list" | "detail" | "form";

export interface AppState {
  view: View;
  connection: Connection | null;
  pendingCredentials: { baseUrl: string; apiKey: string } | null;
  pendingWorkspaces: Workspace[];
  connectError: string | null;
  connecting: boolean;
  requirements: Requirement[];
  requirementsCount: number;
  requirementsPage: number;
  hasMoreRequirements: boolean;
  searchTerm: string;
  listLoading: boolean;
  listError: string | null;
  selectedRequirement: Requirement | null;
  detailLoading: boolean;
  detailError: string | null;
}

let state: AppState = {
  view: "connect",
  connection: null,
  pendingCredentials: null,
  pendingWorkspaces: [],
  connectError: null,
  connecting: false,
  requirements: [],
  requirementsCount: 0,
  requirementsPage: 1,
  hasMoreRequirements: false,
  searchTerm: "",
  listLoading: false,
  listError: null,
  selectedRequirement: null,
  detailLoading: false,
  detailError: null,
};

let hermesAPI: HermesPluginAPI | null = null;
const listeners = new Set<() => void>();

export function getState(): AppState {
  return state;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setState(patch: Partial<AppState>) {
  state = { ...state, ...patch };
  for (const l of listeners) {
    try {
      l();
    } catch {
      /* a listener throwing must not break the others */
    }
  }
}

function api(): HermesPluginAPI {
  if (!hermesAPI) throw new Error("state not initialized — call initState() first");
  return hermesAPI;
}

export async function initState(pluginApi: HermesPluginAPI): Promise<void> {
  hermesAPI = pluginApi;
  const stored = await pluginApi.storage.get(STORAGE_KEY);
  if (!stored) return;
  try {
    const connection = JSON.parse(stored) as Connection;
    setState({ connection, view: "list" });
    await loadRequirements();
  } catch {
    await pluginApi.storage.delete(STORAGE_KEY);
  }
}

export async function connectWithCredentials(baseUrl: string, apiKey: string): Promise<void> {
  setState({ connecting: true, connectError: null });
  try {
    const workspaces = await listWorkspaces(api().network, { baseUrl, apiKey });
    if (workspaces.length === 0) {
      setState({ connecting: false, connectError: "No workspaces accessible with this API key." });
      return;
    }
    if (workspaces.length === 1) {
      await finalizeConnection({ baseUrl, apiKey, workspaceId: workspaces[0].id });
      return;
    }
    setState({
      connecting: false,
      pendingCredentials: { baseUrl, apiKey },
      pendingWorkspaces: workspaces,
    });
  } catch (err) {
    setState({
      connecting: false,
      connectError: err instanceof ReqogniLoomApiError ? err.message : "Connection failed.",
    });
  }
}

export async function chooseWorkspace(workspace: Workspace): Promise<void> {
  if (!state.pendingCredentials) return;
  await finalizeConnection({ ...state.pendingCredentials, workspaceId: workspace.id });
}

async function finalizeConnection(connection: Connection): Promise<void> {
  await api().storage.set(STORAGE_KEY, JSON.stringify(connection));
  setState({
    connection,
    connecting: false,
    pendingCredentials: null,
    pendingWorkspaces: [],
    connectError: null,
    view: "list",
  });
  await loadRequirements();
}

export async function disconnect(): Promise<void> {
  await api().storage.delete(STORAGE_KEY);
  setState({
    view: "connect",
    connection: null,
    pendingCredentials: null,
    pendingWorkspaces: [],
    requirements: [],
    requirementsCount: 0,
    requirementsPage: 1,
    hasMoreRequirements: false,
    selectedRequirement: null,
  });
}

export function setSearchTerm(term: string): void {
  setState({ searchTerm: term });
}

export async function loadRequirements(page = 1): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ listLoading: true, listError: null });
  try {
    const response = await listRequirements(api().network, connection, {
      page,
      search: state.searchTerm || undefined,
    });
    setState({
      requirements: response.results,
      requirementsCount: response.count,
      requirementsPage: page,
      hasMoreRequirements: response.next !== null,
      listLoading: false,
    });
  } catch (err) {
    if (err instanceof ReqogniLoomApiError && (err.status === 401 || err.status === 403)) {
      await disconnect();
      return;
    }
    setState({
      listLoading: false,
      listError: err instanceof ReqogniLoomApiError ? err.message : "Failed to load requirements.",
    });
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npm test`
Expected: PASS — all `state.test.ts` cases green (Task 4 will extend this same file with detail/form tests, so re-run the whole suite, not a subset).

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/state.ts integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts
git commit -m "feat: add connect and list state flow for Hermes plugin"
```

---

### Task 4: State module — detail and create/edit form flow

**Files:**
- Modify: `integrations/hermes-plugin/reqogniloom/src/state.ts`
- Modify: `integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts`

**Interfaces:**
- Consumes: `getRequirement`, `createRequirement`, `updateRequirement` from `api.ts` (Task 2, previously unused by `state.ts`); everything Task 3 already produced in `state.ts` (`setState`, `api()`, `AppState`, view/connection handling).
- Produces (consumed by Task 6's `RequirementDetail.tsx` / `RequirementForm.tsx`):
  - `interface FormState { mode: "create" | "edit"; values: CreateRequirementInput; requirementId?: string; fieldErrors: Record<string, string[]>; submitting: boolean; submitError: string | null }` — added to `AppState.form: FormState | null`
  - `function selectRequirement(id: string): Promise<void>` — loads detail, sets `view: "detail"`
  - `function backToList(): void` — clears `selectedRequirement`/`form`, sets `view: "list"`
  - `function openCreateForm(): void`
  - `function openEditForm(requirement: Requirement): void`
  - `function updateFormField<K extends keyof CreateRequirementInput>(field: K, value: CreateRequirementInput[K]): void`
  - `function submitForm(): Promise<void>`

- [ ] **Step 1: Write the failing tests (append to the existing test file)**

```typescript
// integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts
// --- append below the existing describe blocks, same imports file ---

import { selectRequirement, backToList, openCreateForm, openEditForm, updateFormField, submitForm } from "../state";

describe("selectRequirement / backToList", () => {
  it("loads the requirement detail and switches view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.getRequirement).mockResolvedValue({ id: "r1", title: "Login" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await selectRequirement("r1");

    expect(getState().view).toBe("detail");
    expect(getState().selectedRequirement).toEqual({ id: "r1", title: "Login" });
    expect(getState().detailLoading).toBe(false);
  });

  it("sets detailError on failure", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.getRequirement).mockRejectedValue(new ReqogniLoomApiError(404, null, "Not found"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");

    await selectRequirement("missing");

    expect(getState().detailError).toBe("Not found");
  });

  it("backToList clears selection and returns to the list view", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.getRequirement).mockResolvedValue({ id: "r1", title: "Login" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    await selectRequirement("r1");

    backToList();

    expect(getState().view).toBe("list");
    expect(getState().selectedRequirement).toBeNull();
  });
});

describe("create/edit form", () => {
  it("openCreateForm starts with empty values in create mode", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);

    openCreateForm();

    expect(getState().view).toBe("form");
    expect(getState().form).toEqual({
      mode: "create",
      values: { title: "" },
      requirementId: undefined,
      fieldErrors: {},
      submitting: false,
      submitError: null,
    });
  });

  it("openEditForm pre-fills values from the requirement in edit mode", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);
    const req = {
      id: "r1",
      title: "Login",
      description: "desc",
      acceptance_criteria: "ac",
      category: "auth",
      type: "SyReq",
      level: 1,
    } as never;

    openEditForm(req);

    expect(getState().view).toBe("form");
    expect(getState().form?.mode).toBe("edit");
    expect(getState().form?.requirementId).toBe("r1");
    expect(getState().form?.values.title).toBe("Login");
  });

  it("updateFormField updates a single field without touching others", async () => {
    const api = createMockHermesAPI();
    await initState(api as never);
    openCreateForm();

    updateFormField("title", "New title");
    updateFormField("category", "auth");

    expect(getState().form?.values).toEqual({ title: "New title", category: "auth" });
  });

  it("submitForm creates a requirement and returns to the list on success", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 1, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockResolvedValue({ id: "r2", title: "New" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();
    updateFormField("title", "New");

    await submitForm();

    expect(apiModule.createRequirement).toHaveBeenCalledWith(expect.anything(), connection, { title: "New" });
    expect(getState().view).toBe("list");
    expect(getState().form).toBeNull();
  });

  it("submitForm updates an existing requirement in edit mode", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.updateRequirement).mockResolvedValue({ id: "r1", title: "Renamed" } as never);
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openEditForm({ id: "r1", title: "Old" } as never);
    updateFormField("title", "Renamed");

    await submitForm();

    expect(apiModule.updateRequirement).toHaveBeenCalledWith(expect.anything(), connection, "r1", { title: "Renamed" });
    expect(getState().view).toBe("list");
  });

  it("submitForm surfaces field-level 400 errors and stays on the form", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockRejectedValue(
      new ReqogniLoomApiError(400, {
        error: { code: "VALIDATION_ERROR", message: "Validation failed", details: [{ field: "title", errors: ["Required."] }] },
      }, "Validation failed")
    );
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();

    await submitForm();

    expect(getState().view).toBe("form");
    expect(getState().form?.fieldErrors).toEqual({ title: ["Required."] });
    expect(getState().form?.submitting).toBe(false);
  });

  it("submitForm sets a generic submitError for non-validation failures", async () => {
    vi.mocked(apiModule.listWorkspaces).mockResolvedValue([workspace]);
    vi.mocked(apiModule.listRequirements).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    vi.mocked(apiModule.createRequirement).mockRejectedValue(new ReqogniLoomApiError(500, null, "Server error"));
    const api = createMockHermesAPI();
    await initState(api as never);
    await connectWithCredentials("https://reqo.example.com", "reqlo_x");
    openCreateForm();

    await submitForm();

    expect(getState().form?.submitError).toBe("Server error");
    expect(getState().form?.fieldErrors).toEqual({});
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd integrations/hermes-plugin/reqogniloom && npm test`
Expected: FAIL — `selectRequirement`/`openCreateForm`/etc. not exported from `../state`.

- [ ] **Step 3: Extend the implementation**

Replace the `import { ... } from "./api"` line at the top of `state.ts` (added in Task 3) with:

```typescript
import {
  listWorkspaces,
  listRequirements,
  getRequirement,
  createRequirement,
  updateRequirement,
  type Connection,
  type Workspace,
  type Requirement,
  type CreateRequirementInput,
  ReqogniLoomApiError,
} from "./api";
```

Replace the `export interface AppState { ... }` block (Task 3) with the following — identical to Task 3's version plus one new `form` field:

```typescript
export interface FormState {
  mode: "create" | "edit";
  values: CreateRequirementInput;
  requirementId?: string;
  fieldErrors: Record<string, string[]>;
  submitting: boolean;
  submitError: string | null;
}

export interface AppState {
  view: View;
  connection: Connection | null;
  pendingCredentials: { baseUrl: string; apiKey: string } | null;
  pendingWorkspaces: Workspace[];
  connectError: string | null;
  connecting: boolean;
  requirements: Requirement[];
  requirementsCount: number;
  requirementsPage: number;
  hasMoreRequirements: boolean;
  searchTerm: string;
  listLoading: boolean;
  listError: string | null;
  selectedRequirement: Requirement | null;
  detailLoading: boolean;
  detailError: string | null;
  form: FormState | null;
}
```

Replace the initial `let state: AppState = { ... }` literal (Task 3) with the same fields plus `form: null,`:

```typescript
let state: AppState = {
  view: "connect",
  connection: null,
  pendingCredentials: null,
  pendingWorkspaces: [],
  connectError: null,
  connecting: false,
  requirements: [],
  requirementsCount: 0,
  requirementsPage: 1,
  hasMoreRequirements: false,
  searchTerm: "",
  listLoading: false,
  listError: null,
  selectedRequirement: null,
  detailLoading: false,
  detailError: null,
  form: null,
};
```

Replace the `export async function disconnect(): Promise<void> { ... }` block (Task 3) with the same body plus resetting `form` and `detailError`:

```typescript
export async function disconnect(): Promise<void> {
  await api().storage.delete(STORAGE_KEY);
  setState({
    view: "connect",
    connection: null,
    pendingCredentials: null,
    pendingWorkspaces: [],
    requirements: [],
    requirementsCount: 0,
    requirementsPage: 1,
    hasMoreRequirements: false,
    selectedRequirement: null,
    detailError: null,
    form: null,
  });
}
```

Then append the following new functions to the end of the file:

```typescript
export async function selectRequirement(id: string): Promise<void> {
  const connection = state.connection;
  if (!connection) return;
  setState({ view: "detail", detailLoading: true, detailError: null });
  try {
    const requirement = await getRequirement(api().network, connection, id);
    setState({ selectedRequirement: requirement, detailLoading: false });
  } catch (err) {
    if (err instanceof ReqogniLoomApiError && (err.status === 401 || err.status === 403)) {
      await disconnect();
      return;
    }
    setState({
      detailLoading: false,
      detailError: err instanceof ReqogniLoomApiError ? err.message : "Failed to load requirement.",
    });
  }
}

export function backToList(): void {
  setState({ view: "list", selectedRequirement: null, detailError: null, form: null });
}

export function openCreateForm(): void {
  setState({
    view: "form",
    form: { mode: "create", values: { title: "" }, fieldErrors: {}, submitting: false, submitError: null },
  });
}

export function openEditForm(requirement: Requirement): void {
  setState({
    view: "form",
    form: {
      mode: "edit",
      requirementId: requirement.id,
      values: {
        title: requirement.title,
        description: requirement.description,
        acceptance_criteria: requirement.acceptance_criteria,
        category: requirement.category,
        type: requirement.type,
        complexity_fibonacci: requirement.complexity_fibonacci ?? undefined,
        verification_method: requirement.verification_method ?? undefined,
        level: requirement.level ?? undefined,
        parent_id: requirement.parent_id ?? undefined,
      },
      fieldErrors: {},
      submitting: false,
      submitError: null,
    },
  });
}

export function updateFormField<K extends keyof CreateRequirementInput>(
  field: K,
  value: CreateRequirementInput[K]
): void {
  if (!state.form) return;
  setState({ form: { ...state.form, values: { ...state.form.values, [field]: value } } });
}

export async function submitForm(): Promise<void> {
  const form = state.form;
  const connection = state.connection;
  if (!form || !connection) return;
  setState({ form: { ...form, submitting: true, fieldErrors: {}, submitError: null } });
  try {
    if (form.mode === "create") {
      await createRequirement(api().network, connection, form.values);
    } else {
      await updateRequirement(api().network, connection, form.requirementId!, form.values);
    }
    setState({ view: "list", form: null });
    await loadRequirements(state.requirementsPage);
  } catch (err) {
    if (err instanceof ReqogniLoomApiError && (err.status === 401 || err.status === 403)) {
      await disconnect();
      return;
    }
    if (err instanceof ReqogniLoomApiError && err.envelope) {
      const fieldErrors: Record<string, string[]> = {};
      for (const d of err.envelope.error.details) fieldErrors[d.field] = d.errors;
      setState({ form: { ...form, submitting: false, fieldErrors } });
      return;
    }
    setState({
      form: {
        ...form,
        submitting: false,
        submitError: err instanceof ReqogniLoomApiError ? err.message : "Failed to save.",
      },
    });
  }
}
```

Also update `disconnect()` (from Task 3) to reset `form: null` and `detailError: null` alongside its existing resets, and update the initial `state` literal to include `form: null`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd integrations/hermes-plugin/reqogniloom && npm test`
Expected: PASS — full `state.test.ts` suite green.

- [ ] **Step 5: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/state.ts integrations/hermes-plugin/reqogniloom/src/__tests__/state.test.ts
git commit -m "feat: add detail and create/edit form flow to Hermes plugin state"
```

---

### Task 5: UI — Connect screen and requirements list

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/src/ConnectScreen.tsx`
- Create: `integrations/hermes-plugin/reqogniloom/src/RequirementsList.tsx`

**Interfaces:**
- Consumes: `AppState`, `subscribe`, `connectWithCredentials`, `chooseWorkspace`, `setSearchTerm`, `loadRequirements`, `selectRequirement`, `openCreateForm` from `state.ts` (Tasks 3/4).
- Produces: `ConnectScreen` and `RequirementsList` React components, wired together in Task 7's `ReqogniLoomPanel.tsx`.

Per the Global Constraints, this task has no unit tests (matches this ecosystem's own convention of not unit-testing view components) — it is verified visually in Task 9.

- [ ] **Step 1: Write `ConnectScreen.tsx`**

```typescript
// integrations/hermes-plugin/reqogniloom/src/ConnectScreen.tsx
import * as React from "react";
import { useState } from "react";
import type { AppState } from "./state";
import { connectWithCredentials, chooseWorkspace } from "./state";

const inputStyle: React.CSSProperties = {
  background: "var(--bg-2)",
  color: "var(--text-1)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "6px 8px",
  fontSize: "var(--text-sm)",
  fontFamily: "var(--font-mono)",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

export function ConnectScreen({ state }: { state: AppState }) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  if (state.pendingWorkspaces.length > 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <p style={{ color: "var(--text-2)", fontSize: "var(--text-xs)" }}>Choose a workspace:</p>
        {state.pendingWorkspaces.map((w) => (
          <button key={w.id} style={{ ...buttonStyle, textAlign: "left" }} onClick={() => chooseWorkspace(w)}>
            {w.name}
          </button>
        ))}
      </div>
    );
  }

  return (
    <form
      style={{ display: "flex", flexDirection: "column", gap: "8px" }}
      onSubmit={(e) => {
        e.preventDefault();
        void connectWithCredentials(baseUrl, apiKey);
      }}
    >
      <label style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>
        Workspace URL
        <input
          style={{ ...inputStyle, width: "100%", marginTop: "4px" }}
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://reqogniloom.example.com"
        />
      </label>
      <label style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>
        API Key
        <input
          style={{ ...inputStyle, width: "100%", marginTop: "4px" }}
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="reqlo_..."
        />
      </label>
      {state.connectError && <p style={{ color: "var(--red)", fontSize: "var(--text-xs)" }}>{state.connectError}</p>}
      <button type="submit" style={buttonStyle} disabled={state.connecting || !baseUrl || !apiKey}>
        {state.connecting ? "Connecting…" : "Connect"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Write `RequirementsList.tsx`**

```typescript
// integrations/hermes-plugin/reqogniloom/src/RequirementsList.tsx
import * as React from "react";
import type { AppState } from "./state";
import { setSearchTerm, loadRequirements, selectRequirement, openCreateForm, disconnect } from "./state";

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

export function RequirementsList({ state }: { state: AppState }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px", height: "100%" }}>
      <div style={{ display: "flex", gap: "6px" }}>
        <input
          style={{
            flex: 1,
            background: "var(--bg-2)",
            color: "var(--text-1)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: "6px 8px",
            fontSize: "var(--text-sm)",
          }}
          value={state.searchTerm}
          placeholder="Search requirements…"
          onChange={(e) => setSearchTerm(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void loadRequirements(1);
          }}
        />
        <button style={buttonStyle} onClick={() => void loadRequirements(1)}>
          Search
        </button>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>{state.requirementsCount} total</span>
        <div style={{ display: "flex", gap: "6px" }}>
          <button style={buttonStyle} onClick={() => openCreateForm()}>
            + New
          </button>
          <button style={buttonStyle} onClick={() => void disconnect()}>
            Disconnect
          </button>
        </div>
      </div>

      {state.listError && <p style={{ color: "var(--red)", fontSize: "var(--text-xs)" }}>{state.listError}</p>}

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "4px" }}>
        {state.listLoading && <p style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Loading…</p>}
        {!state.listLoading &&
          state.requirements.map((r) => (
            <button
              key={r.id}
              style={{
                textAlign: "left",
                background: "var(--bg-2)",
                color: "var(--text-1)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px",
                cursor: "pointer",
                fontSize: "var(--text-sm)",
              }}
              onClick={() => void selectRequirement(r.id)}
            >
              <div>{r.title}</div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>
                {r.uid ?? r.id} · {r.status}
              </div>
            </button>
          ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <button
          style={buttonStyle}
          disabled={state.requirementsPage <= 1}
          onClick={() => void loadRequirements(state.requirementsPage - 1)}
        >
          Prev
        </button>
        <button
          style={buttonStyle}
          disabled={!state.hasMoreRequirements}
          onClick={() => void loadRequirements(state.requirementsPage + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify the project still builds**

Run: `cd integrations/hermes-plugin/reqogniloom && npm run build`
Expected: builds cleanly, no TypeScript errors (these components aren't wired into `activate.ts` yet — that's Task 7 — so a build-only check is sufficient here).

- [ ] **Step 4: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/ConnectScreen.tsx integrations/hermes-plugin/reqogniloom/src/RequirementsList.tsx
git commit -m "feat: add connect screen and requirements list UI"
```

---

### Task 6: UI — Requirement detail and create/edit form

**Files:**
- Create: `integrations/hermes-plugin/reqogniloom/src/RequirementDetail.tsx`
- Create: `integrations/hermes-plugin/reqogniloom/src/RequirementForm.tsx`

**Interfaces:**
- Consumes: `AppState`, `backToList`, `openEditForm`, `updateFormField`, `submitForm` from `state.ts` (Task 4).
- Produces: `RequirementDetail` and `RequirementForm` components, wired in Task 7.

No unit tests, same reasoning as Task 5.

- [ ] **Step 1: Write `RequirementDetail.tsx`**

```typescript
// integrations/hermes-plugin/reqogniloom/src/RequirementDetail.tsx
import * as React from "react";
import type { AppState } from "./state";
import { backToList, openEditForm } from "./state";

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

const rowStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "2px" };
const labelStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };

export function RequirementDetail({ state }: { state: AppState }) {
  if (state.detailLoading) return <p style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Loading…</p>;
  if (state.detailError) return <p style={{ color: "var(--red)", fontSize: "var(--text-xs)" }}>{state.detailError}</p>;
  const r = state.selectedRequirement;
  if (!r) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <button style={buttonStyle} onClick={() => backToList()}>
        ← Back
      </button>
      <h3 style={{ margin: 0, fontSize: "var(--text-sm)" }}>{r.title}</h3>

      <div style={rowStyle}>
        <span style={labelStyle}>ID</span>
        <span>{r.uid ?? r.id}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Status</span>
        <span>{r.status}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Type</span>
        <span>{r.type}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Level</span>
        <span>{r.level ?? "—"}</span>
      </div>
      {r.verification_method && (
        <div style={rowStyle}>
          <span style={labelStyle}>Verification Method</span>
          <span>{r.verification_method}</span>
        </div>
      )}
      <div style={rowStyle}>
        <span style={labelStyle}>Description</span>
        <span>{r.description || "—"}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Acceptance Criteria</span>
        <span>{r.acceptance_criteria || "—"}</span>
      </div>

      <button style={buttonStyle} onClick={() => openEditForm(r)}>
        Edit
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Write `RequirementForm.tsx`**

```typescript
// integrations/hermes-plugin/reqogniloom/src/RequirementForm.tsx
import * as React from "react";
import type { AppState } from "./state";
import { backToList, updateFormField, submitForm } from "./state";

const inputStyle: React.CSSProperties = {
  background: "var(--bg-2)",
  color: "var(--text-1)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "6px 8px",
  fontSize: "var(--text-sm)",
  fontFamily: "var(--font-mono)",
  width: "100%",
  marginTop: "4px",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

const labelStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };
const errorStyle: React.CSSProperties = { color: "var(--red)", fontSize: "var(--text-xs)", marginTop: "2px" };

export function RequirementForm({ state }: { state: AppState }) {
  const form = state.form;
  if (!form) return null;

  return (
    <form
      style={{ display: "flex", flexDirection: "column", gap: "10px" }}
      onSubmit={(e) => {
        e.preventDefault();
        void submitForm();
      }}
    >
      <h3 style={{ margin: 0, fontSize: "var(--text-sm)" }}>
        {form.mode === "create" ? "New Requirement" : "Edit Requirement"}
      </h3>

      <label style={labelStyle}>
        Title
        <input
          style={inputStyle}
          value={form.values.title ?? ""}
          onChange={(e) => updateFormField("title", e.target.value)}
        />
        {form.fieldErrors.title && <div style={errorStyle}>{form.fieldErrors.title.join(" ")}</div>}
      </label>

      <label style={labelStyle}>
        Description
        <textarea
          style={{ ...inputStyle, minHeight: "60px" }}
          value={form.values.description ?? ""}
          onChange={(e) => updateFormField("description", e.target.value)}
        />
        {form.fieldErrors.description && <div style={errorStyle}>{form.fieldErrors.description.join(" ")}</div>}
      </label>

      <label style={labelStyle}>
        Acceptance Criteria
        <textarea
          style={{ ...inputStyle, minHeight: "60px" }}
          value={form.values.acceptance_criteria ?? ""}
          onChange={(e) => updateFormField("acceptance_criteria", e.target.value)}
        />
        {form.fieldErrors.acceptance_criteria && (
          <div style={errorStyle}>{form.fieldErrors.acceptance_criteria.join(" ")}</div>
        )}
      </label>

      <label style={labelStyle}>
        Category
        <input
          style={inputStyle}
          value={form.values.category ?? ""}
          onChange={(e) => updateFormField("category", e.target.value)}
        />
      </label>

      <label style={labelStyle}>
        Level (0-4)
        <input
          style={inputStyle}
          type="number"
          min={0}
          max={4}
          value={form.values.level ?? ""}
          onChange={(e) => updateFormField("level", e.target.value === "" ? undefined : Number(e.target.value))}
        />
        {form.fieldErrors.level && <div style={errorStyle}>{form.fieldErrors.level.join(" ")}</div>}
      </label>

      {form.submitError && <p style={errorStyle}>{form.submitError}</p>}

      <div style={{ display: "flex", gap: "8px" }}>
        <button type="submit" style={buttonStyle} disabled={form.submitting || !form.values.title}>
          {form.submitting ? "Saving…" : "Save"}
        </button>
        <button type="button" style={buttonStyle} onClick={() => backToList()}>
          Cancel
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 3: Verify the project still builds**

Run: `cd integrations/hermes-plugin/reqogniloom && npm run build`
Expected: builds cleanly, no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/RequirementDetail.tsx integrations/hermes-plugin/reqogniloom/src/RequirementForm.tsx
git commit -m "feat: add requirement detail and create/edit form UI"
```

---

### Task 7: Wire everything together in `activate.ts` and `ReqogniLoomPanel.tsx`

**Files:**
- Modify: `integrations/hermes-plugin/reqogniloom/src/activate.ts`
- Modify: `integrations/hermes-plugin/reqogniloom/src/ReqogniLoomPanel.tsx`

**Interfaces:**
- Consumes: `initState`, `getState`, `subscribe` from `state.ts` (Tasks 3/4); `ConnectScreen`, `RequirementsList`, `RequirementDetail`, `RequirementForm` (Tasks 5/6).
- Produces: the final activated plugin — nothing downstream depends on this task, it is the integration point.

- [ ] **Step 1: Replace the stub `activate.ts` with the real lifecycle**

```typescript
// integrations/hermes-plugin/reqogniloom/src/activate.ts
import type { HermesPluginAPI } from "./hermes-api-types";
import { ReqogniLoomPanel } from "./ReqogniLoomPanel";
import { initState } from "./state";

let hermesAPI: HermesPluginAPI | null = null;

export function getAPI(): HermesPluginAPI {
  if (!hermesAPI) throw new Error("ReqogniLoom plugin not activated");
  return hermesAPI;
}

export async function activate(api: HermesPluginAPI) {
  hermesAPI = api;

  api.ui.registerPanel("reqogniloom-panel", ReqogniLoomPanel);
  api.subscriptions.push(
    api.commands.register("reqogniloom.open", () => {
      api.ui.showPanel("reqogniloom-panel");
    })
  );

  await initState(api);
}

export function deactivate() {
  hermesAPI = null;
}
```

- [ ] **Step 2: Replace the stub `ReqogniLoomPanel.tsx` with the real view switch**

```typescript
// integrations/hermes-plugin/reqogniloom/src/ReqogniLoomPanel.tsx
import * as React from "react";
import { useEffect, useState } from "react";
import type { PluginPanelProps } from "./hermes-api-types";
import { getState, subscribe } from "./state";
import { ConnectScreen } from "./ConnectScreen";
import { RequirementsList } from "./RequirementsList";
import { RequirementDetail } from "./RequirementDetail";
import { RequirementForm } from "./RequirementForm";

export function ReqogniLoomPanel(_props: PluginPanelProps) {
  const [, forceRender] = useState(0);

  useEffect(() => {
    return subscribe(() => forceRender((n) => n + 1));
  }, []);

  const state = getState();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        padding: "16px",
        gap: "12px",
        minWidth: "260px",
        maxWidth: "400px",
        overflowY: "auto",
        background: "var(--bg-1)",
        color: "var(--text-1)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-sm)",
      }}
    >
      <h3
        style={{
          margin: 0,
          fontSize: "var(--text-xs)",
          fontWeight: 600,
          textTransform: "uppercase",
          color: "var(--text-2)",
          letterSpacing: "0.05em",
        }}
      >
        REQOGNILOOM
      </h3>

      {state.view === "connect" && <ConnectScreen state={state} />}
      {state.view === "list" && <RequirementsList state={state} />}
      {state.view === "detail" && <RequirementDetail state={state} />}
      {state.view === "form" && <RequirementForm state={state} />}
    </div>
  );
}
```

- [ ] **Step 3: Run the full test suite and the build**

Run: `cd integrations/hermes-plugin/reqogniloom && npm test && npm run build`
Expected: all `api.test.ts` and `state.test.ts` cases pass, `dist/index.js` builds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add integrations/hermes-plugin/reqogniloom/src/activate.ts integrations/hermes-plugin/reqogniloom/src/ReqogniLoomPanel.tsx
git commit -m "feat: wire up ReqogniLoom Hermes plugin panel lifecycle"
```

---

### Task 8: CI workflow

**Files:**
- Create: `.github/workflows/hermes-plugin.yml`

**Interfaces:**
- Consumes: `integrations/hermes-plugin/reqogniloom/package.json`'s `build`/`test` scripts (Task 1).
- Produces: nothing downstream — this is the terminal automation task.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/hermes-plugin.yml
name: Hermes Plugin

on:
  push:
    branches: [main]
    paths:
      - "integrations/hermes-plugin/**"
      - ".github/workflows/hermes-plugin.yml"
  pull_request:
    paths:
      - "integrations/hermes-plugin/**"
      - ".github/workflows/hermes-plugin.yml"

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: integrations/hermes-plugin/reqogniloom
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
        with:
          node-version: "20"
      - run: npm install
      - run: npm test
      - run: npm run build
```

- [ ] **Step 2: Verify the workflow YAML is valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/hermes-plugin.yml'))"`
Expected: no exception (valid YAML syntax) — this repo doesn't run GitHub Actions locally, so this is the practical local check; the real test is the first push triggering the workflow.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/hermes-plugin.yml
git commit -m "ci: add Hermes plugin lint/test/build workflow"
```

---

### Task 9: Manual verification against a running ReqogniLoom dev stack

**Files:** none (verification only, no code changes expected unless this task surfaces a bug — if it does, fix it here and amend the relevant earlier task's commit or add a small follow-up commit, then re-verify).

**Interfaces:** none — this task consumes the fully wired plugin from Task 7 and the running dev stack; it produces confidence, not code.

- [ ] **Step 1: Bring up the ReqogniLoom dev stack**

Run: `docker compose up -d postgres redis backend celery frontend` (from the repo root)
Expected: all 5 services healthy/running (`docker compose ps`).

- [ ] **Step 2: Create a test API key**

Log into the running ReqogniLoom instance (seeded demo admin — check `docker compose exec backend python manage.py seed_demo` output or existing seed docs for credentials), navigate to API key management, and create a new key. Note the `reqlo_...` value — it's shown once.

- [ ] **Step 3: Build the plugin and install it into a local Hermes IDE**

Run:
```bash
cd integrations/hermes-plugin/reqogniloom
npm install
npm run build
mkdir -p ~/.config/com.hermes-ide.terminal/plugins/reqogniloom.reqogniloom
cp -r hermes-plugin.json dist ~/.config/com.hermes-ide.terminal/plugins/reqogniloom.reqogniloom/
```
(Use the macOS/Windows path from `docs/DEVELOPMENT.md` in `hermes-hq/plugins` instead if not on Linux.)

Restart Hermes IDE.

- [ ] **Step 4: Verify the Connect flow**

- Open the ReqogniLoom panel (via the sidebar icon or the "Open ReqogniLoom" command).
- Enter the dev stack's frontend/backend base URL and the API key from Step 2.
- Confirm: if the seeded demo tenant has exactly one workspace, the panel goes straight to the requirements list; if it has more than one, the workspace picker appears and clicking one proceeds to the list.
- **This is where `api.network.fetch()`'s actual return shape (string vs. `Response`) gets confirmed for real** — if the Connect step fails with a parsing error despite a correct URL/key, that's the signal `parseNetworkResult()` in `api.ts` needs adjusting; fix it there (both shapes are already handled, so this should just work, but confirm it does).

- [ ] **Step 5: Verify list, search, and pagination**

- Confirm the requirements list loads and shows real titles/status/IDs from the seeded data.
- Type a search term matching a known seeded requirement's title, confirm the list filters.
- If there are more than 25 requirements, confirm Next/Prev paging works.

- [ ] **Step 6: Verify detail, create, and edit**

- Click a requirement, confirm the detail view shows its fields correctly (including that `status` renders but has no edit control).
- Click "+ New", fill in a title, submit, confirm it appears in the list afterward.
- Open that new requirement, click "Edit", change the title, submit, confirm the change is reflected.
- Trigger a validation error deliberately (e.g., clear the title before submitting an edit) and confirm the field-level error renders under the Title input, not just a generic toast.

- [ ] **Step 7: Verify disconnect and reconnect**

- Click "Disconnect", confirm the panel returns to the Connect screen and the stored key is gone (re-opening the panel doesn't auto-connect).
- Reconnect with the same credentials, confirm it works again.

- [ ] **Step 8: Record findings**

If any step in this task surfaced a real bug (not covered by the unit tests because it's an integration-only failure mode, e.g. the `api.network.fetch` shape mismatch), fix it in the relevant file, re-run `npm test`, and commit the fix with a message referencing which manual-verification step caught it. If everything passed as designed, no commit is needed for this task — it closes the plan.
