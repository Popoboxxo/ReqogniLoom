import { StrictMode } from "react";
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { advanceAuthSessionGeneration } from "../api/client";
import { teardownBluepencilReviewLayer } from "../bluepencil/loader";
import { AuthProvider, useAuth, type AuthState } from "../context/AuthContext";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let captured: AuthState | null = null;

function Capture(): JSX.Element {
  captured = useAuth();
  return <div data-testid="auth-capture" />;
}

describe("AuthContext login timeout", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    advanceAuthSessionGeneration();
    captured = null;
  });

  afterEach(() => {
    teardownBluepencilReviewLayer();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  it("compensates with logout when response-body processing times out", async () => {
    let loginSignal: AbortSignal | null = null;
    let logoutCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/auth/me/")) return Promise.resolve(response({}, 401));
        if (url.endsWith("/auth/refresh/")) return Promise.resolve(response({}, 401));
        if (url.endsWith("/auth/login/")) {
          loginSignal = init?.signal ?? null;
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () =>
              new Promise<never>((_resolve, reject) => {
                const rejectOnAbort = () => reject(new DOMException("Aborted", "AbortError"));
                if (loginSignal?.aborted) rejectOnAbort();
                else loginSignal?.addEventListener("abort", rejectOnAbort, { once: true });
              }),
          } as Response);
        }
        if (url.endsWith("/auth/logout/")) {
          logoutCalls += 1;
          return Promise.resolve(response({}));
        }
        return Promise.resolve(response({}));
      }),
    );

    render(
      <StrictMode>
        <AuthProvider>
          <Capture />
        </AuthProvider>
      </StrictMode>,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const pendingLogin = captured!.login({ username: "first.user", password: "pw" });
    await act(async () => {
      await Promise.resolve();
    });
    expect(loginSignal).not.toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    await expect(pendingLogin).rejects.toThrow("Login request timed out");
    expect(logoutCalls).toBe(1);
    expect(captured?.status).toBe("anonymous");
  });
});
