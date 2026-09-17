/**
 * ARCH-L1-001 ReactFrontend — SVG sanitisation helper.
 *
 * req_id: REQ-L1-056 (Canvas), REQ-L1-057 (Mermaid)
 *
 * Single seam for every SVG string that reaches `dangerouslySetInnerHTML`.
 * Two sources feed those sinks and neither is trustworthy on its own:
 *   - the server-rendered canvas export (IF-L1-060), derived from stored,
 *     user-supplied stroke JSON — i.e. attacker-controllable across users in a
 *     multi-tenant workspace;
 *   - mermaid.render output, which is generated from a stored source string.
 *     Mermaid runs with `securityLevel: "strict"`, but that is *its* guarantee,
 *     not ours, and it is a config flag one refactor away from being lost.
 *
 * Sanitising here is defence-in-depth: the canvas exporter also coerces and
 * escapes its inputs server-side (backend/diagram/canvas_editor.py).
 */
import DOMPurify from "dompurify";

/**
 * Strip script content, event-handler attributes and javascript: URLs from an
 * SVG string, keeping the markup renderable.
 *
 * DOMPurify defaults are kept deliberately strict: `<foreignObject>` and its
 * HTML subtree are dropped (DOMPurify treats it as an mXSS vector and does not
 * list it as an HTML integration point). Mermaid would otherwise emit node
 * labels inside `<foreignObject>` and they would silently vanish here, so both
 * mermaid call sites are configured with `htmlLabels: false` and render labels
 * as plain SVG `<text>`. Keep those two settings together: relaxing the
 * sanitiser instead would mean re-enabling ADD_TAGS + HTML_INTEGRATION_POINTS +
 * FORBID_CONTENTS, i.e. undoing three hardening defaults at once.
 *
 * @param svg Untrusted SVG markup.
 * @returns Sanitised markup, safe to hand to `dangerouslySetInnerHTML`.
 */
export function sanitizeSvg(svg: string): string {
  if (!svg) return "";
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    // The SVG profile drops `role`, which mermaid sets on the diagram root
    // (role="graphics-document") and on nodes. It carries no script surface,
    // so keeping it preserves screen-reader semantics.
    ADD_ATTR: ["role"],
  });
}
