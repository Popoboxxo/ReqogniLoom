import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  bluepencilIdentityFromUser,
  installBluepencilHost,
  resetBluepencilHost,
  setBluepencilIdentitySource,
} from "../bluepencil/host";
import { teardownBluepencilReviewLayer } from "../bluepencil/loader";

function host(): NonNullable<Window["rfBluepencil"]> {
  const value = window.rfBluepencil;
  if (value === undefined) throw new Error("window.rfBluepencil is not installed");
  return value;
}

function clearCsrfCookie(): void {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
}

describe("bluepencil host headers", () => {
  beforeEach(() => {
    resetBluepencilHost();
    clearCsrfCookie();
    installBluepencilHost();
  });
  afterEach(() => {
    resetBluepencilHost();
    clearCsrfCookie();
  });

  it("returns no headers without a CSRF cookie", () => {
    expect(host().headers()).toEqual({});
  });

  it("mirrors the CSRF cookie", () => {
    document.cookie = "csrftoken=csrf-abc; path=/";
    expect(host().headers()).toEqual({ "X-CSRFToken": "csrf-abc" });
  });

  it("does not expose an authorization header", () => {
    document.cookie = "csrftoken=csrf-abc; path=/";
    const headers = host().headers();
    expect(headers).not.toHaveProperty("Authorization");
  });

  it("returns a fresh headers object", () => {
    expect(host().headers()).not.toBe(host().headers());
  });
});

describe("bluepencil host identity", () => {
  beforeEach(resetBluepencilHost);
  afterEach(resetBluepencilHost);

  it("maps first and last name", () => {
    installBluepencilHost({
      getUser: () =>
        bluepencilIdentityFromUser({
          id: "u-1",
          username: "alovelace",
          first_name: "Ada",
          last_name: "Lovelace",
        }),
    });
    expect(host().identity.getUser()).toEqual({ id: "u-1", name: "Ada Lovelace" });
  });

  it("falls back to username", () => {
    installBluepencilHost({
      getUser: () =>
        bluepencilIdentityFromUser({
          id: "u-2",
          username: "tester",
          first_name: "",
          last_name: "   ",
        }),
    });
    expect(host().identity.getUser()).toEqual({ id: "u-2", name: "tester" });
  });

  it("normalizes whitespace and omits an empty id", () => {
    expect(
      bluepencilIdentityFromUser({
        id: "",
        username: "x",
        first_name: "  Ada  ",
        last_name: "  Lovelace ",
      }),
    ).toEqual({ name: "Ada Lovelace" });
  });

  it("returns null without a usable identity", () => {
    installBluepencilHost({ getUser: () => bluepencilIdentityFromUser(null) });
    expect(host().identity.getUser()).toBeNull();
    expect(bluepencilIdentityFromUser(undefined)).toBeNull();
    expect(bluepencilIdentityFromUser({ username: "  " })).toBeNull();
  });
});

describe("bluepencil host gate and route", () => {
  beforeEach(() => {
    resetBluepencilHost();
    installBluepencilHost();
  });
  afterEach(() => {
    resetBluepencilHost();
    window.history.pushState({}, "", "/");
  });

  it("keeps the client gate permissive", () => {
    expect(host().gate()).toBe(true);
  });

  it("uses the pathname fallback", () => {
    window.history.pushState({}, "", "/requirements/abc");
    expect(host().routeFor()).toBe("/requirements/abc");
    expect(host().routeFor(null)).toBe("/requirements/abc");
  });

  it("uses the nearest data-rf-view ancestor", () => {
    const section = document.createElement("section");
    section.setAttribute("data-rf-view", "/artifact/42");
    const button = document.createElement("button");
    section.append(button);
    document.body.append(section);

    expect(host().routeFor(button)).toBe("/artifact/42");
    expect(host().routeFor({})).toBe(window.location.pathname);
    section.remove();
  });
});

describe("bluepencil host lifecycle", () => {
  beforeEach(resetBluepencilHost);
  afterEach(resetBluepencilHost);

  it("keeps stable wrapper references while updating identity", () => {
    const first = installBluepencilHost({ getUser: () => ({ id: "u-1", name: "First" }) });
    const identity = window.rfBluepencil?.identity;
    const getUser = identity?.getUser;
    const second = installBluepencilHost();

    expect(second).toBe(first);
    expect(window.rfBluepencil?.identity).toBe(identity);
    expect(window.rfBluepencil?.identity.getUser).toBe(getUser);

    setBluepencilIdentitySource(() => ({ id: "u-2", name: "Second" }));
    expect(host().identity.getUser()).toEqual({ id: "u-2", name: "Second" });
    setBluepencilIdentitySource(null);
    expect(host().identity.getUser()).toBeNull();
  });

  it("clears the global and identity source on teardown", () => {
    installBluepencilHost({ getUser: () => ({ name: "Ada" }) });
    teardownBluepencilReviewLayer();

    expect(window.rfBluepencil).toBeUndefined();
    installBluepencilHost();
    expect(host().identity.getUser()).toBeNull();
  });
});
