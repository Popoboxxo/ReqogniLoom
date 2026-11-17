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

/**
 * App-shell files precached at service-worker install time (PERF-007).
 *
 * The initial ESM graph must boot offline: the hashed Vite entry bundle
 * (``assets/index-*.js``, ~700 KB), its statically-imported ``modulepreload``
 * chunks (react-dom, rolldown-runtime, AuthContext, WorkspaceContext,
 * useQuery, ...) and the shell document/styles/fonts/icons/manifest are all
 * precached. To keep lazy chunks on demand the glob widens to every
 * ``assets/*.js`` and the generated Workbox manifest is then filtered by size
 * through ``shouldKeepPrecacheEntry`` (wired via ``manifestTransforms`` in
 * vite.config.ts): the entry chunk is always kept, every other JS chunk up to
 * ``PWA_PRECACHE_JS_MAX_BYTES`` is kept, larger ones are dropped.
 *
 * Offline trade-off: heavy lazy chunks (Mermaid/fabric/elk/cytoscape/katex/
 * CodeMirror, large ``chunk-*``) are NOT in the install-time precache — they
 * enter the ``reqlo-assets`` runtime cache on first real use and are then
 * served offline from there. Small lazy chunks (< 200 KB) are over-precached
 * on install; that cost is bounded by the threshold and buys a bootable
 * offline first reload.
 */
export const PWA_PRECACHE_GLOBS = [
  "index.html",
  "assets/index-*.css",
  "assets/*.js",
  "assets/*.{woff,woff2,ttf,eot,otf}",
  "icons/*.{png,svg}",
  "*.webmanifest",
] as const;

/**
 * Max byte size of a non-entry ``assets/*.js`` chunk to precache. Chunks at or
 * below this size are initial-load ``modulepreload`` deps (or tiny lazy ones);
 * larger chunks are heavy lazy code that stays on demand. The ~700 KB entry
 * chunk is exempt via ``shouldKeepPrecacheEntry``.
 */
export const PWA_PRECACHE_JS_MAX_BYTES = 200_000;

/** A generated precache manifest entry (subset used by the size filter). */
export interface PwaPrecacheEntry {
  url: string;
  size: number;
}

/**
 * Decide whether a generated precache entry survives the size filter.
 *
 * Non-JS shell assets are governed by ``PWA_PRECACHE_GLOBS`` only and always
 * kept. The hashed entry bundle is always kept regardless of size (it is the
 * root of the initial ESM graph). Every other JS chunk is kept only when it is
 * no larger than ``PWA_PRECACHE_JS_MAX_BYTES``.
 */
export function shouldKeepPrecacheEntry(entry: PwaPrecacheEntry): boolean {
  const { url, size } = entry;
  if (!url.startsWith("assets/") || !url.endsWith(".js")) {
    return true;
  }
  if (/^assets\/index-[^/]*\.js$/.test(url)) {
    return true;
  }
  return size <= PWA_PRECACHE_JS_MAX_BYTES;
}

export function isNetworkOnlyPath(pathname: string): boolean {
  return PWA_NETWORK_ONLY_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}
