/**
 * ArtifactInspector — `inert` bracket of the sheet (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-093 (accessibility baseline)
 *
 * The sheet is **non-modal** (spec §4.2, D3/B1): the list and the navigation
 * stay operable and the sheet has no focus trap. What is *not* allowed is a
 * focusable detail area *behind* the sheet — that is exactly WCAG 2.2
 * SC 2.4.11 ("Focus Not Obscured"). So the covered detail area gets `inert`
 * while the sheet is open, and loses it again in the same commit the sheet
 * unmounts.
 *
 * `useLayoutEffect` is load-bearing here: a passive effect runs after paint,
 * which would leave one frame in which the detail area is still tabbable, and
 * its cleanup runs after the sheet is already gone — the very "no frame that
 * is neither focusable nor visible" rule the spec asks for.
 *
 * `inert` is set as an attribute (not a React prop) because the covered
 * element is owned by the route, not by the shell.
 */

import { useLayoutEffect } from "react";

const INERT_ATTRIBUTE = "inert";

/**
 * Marks `ref`'s element `inert` while `active` is true.
 *
 * The hook is a no-op when the ref is not attached (first render, or a route
 * that has no separate detail container) — an inspector without a covered
 * region behaves like the panel form, which needs no bracket at all.
 */
export function useInertBehindSheet(
  ref: React.RefObject<HTMLElement | null>,
  active: boolean,
): void {
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    if (!active) return undefined;
    element.setAttribute(INERT_ATTRIBUTE, "");
    return () => {
      element.removeAttribute(INERT_ATTRIBUTE);
    };
  }, [ref, active]);
}
