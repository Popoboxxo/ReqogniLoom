import { StrictMode } from "react";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { AuthProvider, useAuth, type AuthState } from "../context/AuthContext";
import { installBluepencilHost } from "../bluepencil/host";
import { teardownBluepencilReviewLayer } from "../bluepencil/loader";

const firstUser = {
  id: "u-1",
  username: "first.user",
  email: "first@example.test",
  first_name: "First",
  last_name: "User",
  is_active: true,
  tenant_id: "t-1",
  roles: ["editor"],
};

const secondUser = {
  ...firstUser,
  id: "u-2",
  username: "second.user",
  first_name: "Second",
  last_name: "User",
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
} {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function loaderScripts(): HTMLScriptElement[] {
  return Array.from(document.querySelectorAll<HTMLScriptElement>("script[data-bluepencil-loader]"));
}

function completeAttach(): void {
  document.dispatchEvent(new Event("bp-attach-ready"));
}

let captured: AuthState | null = null;

function Capture(): JSX.Element {
  captured = useAuth();
  return <div data-testid="auth-capture" />;
}

describe("AuthContext bluepencil lifecycle", () => {
  beforeEach(async () => {
    vi.stubEnv("VITE_BLUEPENCIL_ENABLED", "1");
    completeAttach();
    teardownBluepencilReviewLayer();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    captured = null;
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    completeAttach();
    teardownBluepencilReviewLayer();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  });

  it("does not let a pending session response restore identity after logout", async () => {
    const restore = deferred<Response>();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) return restore.promise;
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    installBluepencilHost({ getUser: () => ({ name: "First User" }) });

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/me/"))).toBe(true),
    );
    captured!.logout();
    installBluepencilHost();

    restore.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
    await waitFor(() => expect(captured?.status).toBe("anonymous"));

    expect(captured?.user).toBeNull();
    expect(window.rfBluepencil?.identity.getUser()).toBeNull();
  });

  it("keeps the latest StrictMode session restore authoritative", async () => {
    const firstRestore = deferred<Response>();
    const secondRestore = deferred<Response>();
    let restoreCalls = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) {
        restoreCalls += 1;
        return restoreCalls === 1 ? firstRestore.promise : secondRestore.promise;
      }
      if (url.endsWith("/auth/refresh/")) return Promise.resolve(response({}, 401));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StrictMode>
        <AuthProvider>
          <Capture />
        </AuthProvider>
      </StrictMode>,
    );
    await waitFor(() => expect(restoreCalls).toBe(2));

    firstRestore.resolve(response({}, 401));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/refresh/"))).toBe(true));
    secondRestore.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));

    await waitFor(() => expect(captured?.status).toBe("authenticated"));
    expect(captured?.user).toEqual(firstUser);
  });

  it("does not notify globally for a stale restore after a newer success", async () => {
    const firstRestore = deferred<Response>();
    const secondRestore = deferred<Response>();
    const onUnauthorized = vi.fn();
    let restoreCalls = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) {
        restoreCalls += 1;
        return restoreCalls === 1 ? firstRestore.promise : secondRestore.promise;
      }
      if (url.endsWith("/auth/refresh/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/protected/")) return Promise.resolve(response({}, 401));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StrictMode>
        <AuthProvider onUnauthorized={onUnauthorized}>
          <Capture />
        </AuthProvider>
      </StrictMode>,
    );
    await waitFor(() => expect(restoreCalls).toBe(2));

    secondRestore.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
    await waitFor(() => expect(captured?.status).toBe("authenticated"));
    firstRestore.resolve(response({}, 401));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/refresh/")),
    ).toBe(false);
    expect(onUnauthorized).not.toHaveBeenCalled();
    expect(captured?.status).toBe("authenticated");
    expect(captured?.user).toEqual(firstUser);

    await expect(apiClient.get("/protected/")).rejects.toMatchObject({
      error: { code: "AUTHENTICATION_REQUIRED" },
    });
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
    expect(captured?.status).toBe("anonymous");
    expect(window.rfBluepencil).toBeUndefined();
  });

  it("handles a real 401 while session restore is still pending", async () => {
    const restore = deferred<Response>();
    const onUnauthorized = vi.fn();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) return restore.promise;
      if (url.endsWith("/protected/") || url.endsWith("/auth/refresh/")) {
        return Promise.resolve(response({}, 401));
      }
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);
    installBluepencilHost();

    render(
      <AuthProvider onUnauthorized={onUnauthorized}>
        <Capture />
      </AuthProvider>,
    );

    await expect(apiClient.get("/protected/")).rejects.toMatchObject({
      error: { code: "AUTHENTICATION_REQUIRED" },
    });
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
    expect(captured?.status).toBe("anonymous");
    expect(window.rfBluepencil).toBeUndefined();

    restore.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(captured?.status).toBe("anonymous");
  });

  it("does not apply a login response that resolves after logout", async () => {
    const login = deferred<Response>();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/login/")) return login.promise;
      if (url.endsWith("/auth/logout/")) return Promise.resolve(response({}));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("anonymous"));

    const pendingLogin = captured!.login({ username: "first.user", password: "pw" });
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/login/"))).toBe(true),
    );
    captured!.logout();
    await waitFor(() => expect(captured?.status).toBe("anonymous"));
    installBluepencilHost();
    login.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));

    await pendingLogin;
    expect(captured?.status).toBe("anonymous");
    expect(captured?.user).toBeNull();
    expect(window.rfBluepencil?.identity.getUser()).toBeNull();
  });

  it("aborts a pending login before sending logout", async () => {
    let loginSignal: AbortSignal | null = null;
    const order: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/refresh/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/login/")) {
        order.push("login");
        loginSignal = init?.signal ?? null;
        return new Promise<Response>((_resolve, reject) => {
          loginSignal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        });
      }
      if (url.endsWith("/auth/logout/")) {
        order.push("logout");
        return Promise.resolve(response({}));
      }
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("anonymous"));

    const pendingLogin = captured!.login({ username: "first.user", password: "pw" });
    await waitFor(() => expect(loginSignal).not.toBeNull());
    captured!.logout();

    await expect(pendingLogin).rejects.toMatchObject({ name: "AbortError" });
    await waitFor(() => expect(order).toEqual(["login", "logout"]));
    expect(captured?.status).toBe("anonymous");
  });

  it("serializes login and logout cookie transitions in invocation order", async () => {
    const login = deferred<Response>();
    const order: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/refresh/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/login/")) {
        order.push("login");
        return login.promise;
      }
      if (url.endsWith("/auth/logout/")) {
        order.push("logout");
        return Promise.resolve(response({}));
      }
      if (url.endsWith("/bluepencil/api/health")) return Promise.resolve(response({ ok: true }));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("anonymous"));

    const pendingLogin = captured!.login({ username: "first.user", password: "pw" });
    await waitFor(() => expect(order).toEqual(["login"]));
    captured!.logout();
    expect(order).toEqual(["login"]);

    login.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
    await pendingLogin;
    await waitFor(() => expect(order).toEqual(["login", "logout"]));
    expect(captured?.status).toBe("anonymous");
  });

  it("serializes a login queued after logout", async () => {
    const logout = deferred<Response>();
    const order: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/refresh/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/logout/")) {
        order.push("logout");
        return logout.promise;
      }
      if (url.endsWith("/auth/login/")) {
        order.push("login");
        return Promise.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
      }
      if (url.endsWith("/bluepencil/api/health")) return Promise.resolve(response({ ok: true }));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("anonymous"));

    captured!.logout();
    const pendingLogin = captured!.login({ username: "first.user", password: "pw" });
    await waitFor(() => expect(order).toEqual(["logout"]));
    expect(order).not.toContain("login");

    logout.resolve(response({}));
    await pendingLogin;
    await waitFor(() => expect(order).toEqual(["logout", "login"]));
    expect(captured?.status).toBe("authenticated");
  });

  it("does not let a delayed logout 401 invalidate a queued login", async () => {
    const logout = deferred<Response>();
    const order: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/refresh/")) return Promise.resolve(response({}, 401));
      if (url.endsWith("/auth/logout/")) {
        order.push("logout");
        return logout.promise;
      }
      if (url.endsWith("/auth/login/")) {
        order.push("login");
        return Promise.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
      }
      if (url.endsWith("/bluepencil/api/health")) return Promise.resolve(response({ ok: true }));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("anonymous"));

    captured!.logout();
    const pendingLogin = captured!.login({ username: "first.user", password: "pw" });
    await waitFor(() => expect(order).toEqual(["logout"]));

    logout.resolve(response({}, 401));
    await pendingLogin;
    await waitFor(() => expect(order).toEqual(["logout", "login"]));
    expect(captured?.status).toBe("authenticated");
    expect(captured?.user).toEqual(firstUser);
  });

  it("ignores a profile response that resolves after logout", async () => {
    const profile = deferred<Response>();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.endsWith("/auth/me/") && method === "GET") {
        return Promise.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
      }
      if (url.endsWith("/auth/me/") && method === "PATCH") return profile.promise;
      if (url.endsWith("/bluepencil/api/health")) return Promise.resolve(response({ ok: true }));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("authenticated"));
    await waitFor(() => expect(loaderScripts()).toHaveLength(1));

    const update = captured!.updateProfile({ first_name: "Changed", last_name: "Name" });
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).endsWith("/auth/me/") &&
            (init as RequestInit | undefined)?.method === "PATCH",
        ),
      ).toBe(true),
    );
    captured!.logout();
    await waitFor(() => expect(captured?.status).toBe("anonymous"));
    installBluepencilHost();
    profile.resolve(response({ user: { ...firstUser, first_name: "Stale", last_name: "Result" } }));

    await update;
    expect(captured?.status).toBe("anonymous");
    expect(captured?.user).toBeNull();
    expect(window.rfBluepencil?.identity.getUser()).toBeNull();
    expect(loaderScripts()).toHaveLength(0);
  });

  it("reinstalls and rebinds exactly once after logout and login", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) {
        return Promise.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
      }
      if (url.endsWith("/auth/login/")) {
        return Promise.resolve(
          response({ user: secondUser, tenant_id: "t-1", roles: ["editor"] }),
        );
      }
      if (url.endsWith("/bluepencil/api/health")) return Promise.resolve(response({ ok: true }));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("authenticated"));
    await waitFor(() => expect(loaderScripts()).toHaveLength(1));
    const firstHost = window.rfBluepencil;

    captured!.logout();
    await waitFor(() => expect(loaderScripts()).toHaveLength(0));
    completeAttach();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    expect(window.rfBluepencil).toBeUndefined();

    await captured!.login({ username: "second.user", password: "pw" });
    await waitFor(() => expect(captured?.status).toBe("authenticated"));
    await waitFor(() => expect(loaderScripts()).toHaveLength(1));

    expect(loaderScripts()).toHaveLength(1);
    expect(window.rfBluepencil).toBeDefined();
    expect(window.rfBluepencil).not.toBe(firstHost);
    expect(window.rfBluepencil?.identity.getUser()).toEqual({ id: "u-2", name: "Second User" });
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/bluepencil/api/health")),
    ).toHaveLength(2);
  });

  it("preserves the new identity when an older attach finishes after login", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me/")) {
        return Promise.resolve(response({ user: firstUser, tenant_id: "t-1", roles: ["editor"] }));
      }
      if (url.endsWith("/auth/login/")) {
        return Promise.resolve(
          response({ user: secondUser, tenant_id: "t-1", roles: ["editor"] }),
        );
      }
      if (url.endsWith("/bluepencil/api/health")) return Promise.resolve(response({ ok: true }));
      return Promise.resolve(response({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    );
    await waitFor(() => expect(captured?.status).toBe("authenticated"));
    await waitFor(() => expect(loaderScripts()).toHaveLength(1));

    captured!.logout();
    await waitFor(() => expect(captured?.status).toBe("anonymous"));
    await captured!.login({ username: "second.user", password: "pw" });
    await waitFor(() => expect(captured?.status).toBe("authenticated"));
    expect(window.rfBluepencil?.identity.getUser()).toEqual({ id: "u-2", name: "Second User" });

    completeAttach();
    await waitFor(() => expect(loaderScripts()).toHaveLength(1));
    expect(window.rfBluepencil?.identity.getUser()).toEqual({ id: "u-2", name: "Second User" });
  });
});
