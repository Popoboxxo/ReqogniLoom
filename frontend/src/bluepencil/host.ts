import { readCookie } from "../api/client";

/** Identity metadata consumed by the Bluepencil element. */
export interface BluepencilIdentity {
  id?: string;
  name: string;
}

/** User fields used to derive Bluepencil identity. */
export interface BluepencilIdentityUser {
  id?: string | null;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
}

/** Global hook object resolved by the Bluepencil element. */
export interface BluepencilHost {
  headers: () => Record<string, string>;
  gate: () => boolean;
  routeFor: (element?: unknown) => string;
  identity: { getUser: () => BluepencilIdentity | null };
  buildRef: () => string;
}

/** Optional hook overrides used when installing the host bridge. */
export interface BluepencilHostOptions {
  getUser?: () => BluepencilIdentity | null;
  headers?: () => Record<string, string>;
  gate?: () => boolean;
  routeFor?: (element?: unknown) => string;
  buildRef?: () => string;
}

declare global {
  interface Window {
    rfBluepencil?: BluepencilHost;
  }
}

let identitySource: (() => BluepencilIdentity | null) | null = null;
let headersSource: (() => Record<string, string>) | null = null;
let gateSource: (() => boolean) | null = null;
let routeForSource: ((element?: unknown) => string) | null = null;
let buildRefSource: (() => string) | null = null;
let hostSingleton: BluepencilHost | null = null;

function defaultHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const csrf = readCookie("csrftoken");
  if (csrf) headers["X-CSRFToken"] = csrf;
  return headers;
}

function defaultGate(): boolean {
  return true;
}

function defaultRouteFor(element?: unknown): string {
  const candidate = element as Element | null | undefined;
  const scoped = candidate?.closest?.("[data-rf-view]") as HTMLElement | null | undefined;
  const view = scoped?.dataset?.rfView;
  if (typeof view === "string" && view !== "") return view;
  return typeof window !== "undefined" ? window.location.pathname : "/";
}

function defaultBuildRef(): string {
  return "";
}

/** Updates the identity resolver without replacing the host object. */
export function setBluepencilIdentitySource(
  getUser: (() => BluepencilIdentity | null) | null,
): void {
  identitySource = getUser;
}

/** Maps an authenticated user to the element's identity shape. */
export function bluepencilIdentityFromUser(
  user: BluepencilIdentityUser | null | undefined,
): BluepencilIdentity | null {
  if (user === null || user === undefined) return null;
  const fullName = `${user.first_name ?? ""} ${user.last_name ?? ""}`
    .trim()
    .replace(/\s+/g, " ");
  const name = fullName !== "" ? fullName : (user.username ?? "").trim();
  if (name === "") return null;
  const identity: BluepencilIdentity = { name };
  if (typeof user.id === "string" && user.id !== "") identity.id = user.id;
  return identity;
}

function createHost(): BluepencilHost {
  return {
    headers: () => (headersSource ?? defaultHeaders)(),
    gate: () => (gateSource ?? defaultGate)(),
    routeFor: (element?: unknown) => (routeForSource ?? defaultRouteFor)(element),
    identity: { getUser: () => identitySource?.() ?? null },
    buildRef: () => (buildRefSource ?? defaultBuildRef)(),
  };
}

/** Installs or updates the singleton host bridge. */
export function installBluepencilHost(opts: BluepencilHostOptions = {}): BluepencilHost {
  if (opts.getUser !== undefined) identitySource = opts.getUser;
  if (opts.headers !== undefined) headersSource = opts.headers;
  if (opts.gate !== undefined) gateSource = opts.gate;
  if (opts.routeFor !== undefined) routeForSource = opts.routeFor;
  if (opts.buildRef !== undefined) buildRefSource = opts.buildRef;
  if (hostSingleton === null) hostSingleton = createHost();
  const host = hostSingleton;
  if (typeof window !== "undefined") window.rfBluepencil = host;
  return host;
}

/** Clears the host bridge and all hook sources. */
export function resetBluepencilHost(): void {
  identitySource = null;
  headersSource = null;
  gateSource = null;
  routeForSource = null;
  buildRefSource = null;
  hostSingleton = null;
  if (typeof window !== "undefined") delete window.rfBluepencil;
}
