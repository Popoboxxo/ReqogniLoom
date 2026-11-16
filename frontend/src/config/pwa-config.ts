/**
 * PWA caching policy — single source of truth for Vite and its drift test.
 *
 * The service worker may cache the app shell and static assets, never an
 * authenticated response. Keeping the patterns here (instead of inline in
 * vite.config.ts) lets `pwa-sw-policy.test.ts` assert the security boundary
 * without parsing a config file as text.
 */

/** Paths the navigation fallback must never rewrite to index.html. */
export const PWA_NAVIGATION_DENYLIST: RegExp[] = [
  /^\/api\//,
  /^\/mcp\//,
  /^\/admin\//,
  /^\/static\//,
];

/** Prefixes that must always hit the network (no runtime cache rule). */
export const PWA_NETWORK_ONLY_PREFIXES = ["/api/", "/mcp/"] as const;

/** Build assets that are safe to cache by their content hash. */
export const PWA_PRECACHE_GLOBS = [
  "**/*.{js,css,html,woff,woff2,png,svg,webmanifest}",
] as const;

export function isNetworkOnlyPath(pathname: string): boolean {
  return PWA_NETWORK_ONLY_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}
