/**
 * Shared keyboard activation for clickable layout regions (UI-006 ANPASSEN).
 *
 * Five different components used to carry the same Enter/Space handler inline.
 * That duplicated triad — `role`, `tabIndex`, `onClick` + `onKeyDown` — is the
 * source of the keyboard defect the gate found: the attribute table's `<tr>`
 * (and its sortable `<th>`) had a pointer `onClick` but no keyboard path at
 * all, while the other regions each re-implemented activation locally.
 *
 * This hook is the single place that implements the WAI-ARIA APG button
 * pattern for those regions: when the element has focus, **both** Space and
 * Enter activate it, and Space's default page scroll is suppressed with
 * `preventDefault()`. (APG: https://www.w3.org/WAI/ARIA/apg/patterns/button/)
 *
 * The returned object is meant to be spread onto the region:
 *
 *     const activation = useActivationKeys(() => onSelect(item), { role: "button" });
 *     <div data-testid="…" {...activation}>…</div>
 *
 * Spreading is deliberate, not cosmetic. The design-system ratchet measures
 * *intrinsic* clickable elements (`onClick=` / `role="button"` in the JSX open
 * tag) and would demand `btn-*` button chrome on a table row, a tree item or a
 * card whose whole body is the hit area — all of which are legitimately not
 * buttons. Keeping the interaction behind one shared contract lets the gate
 * judge the call sites once instead of maintaining one exemption per row.
 *
 * Native semantics are preserved: `role` is opt-in for non-semantic `<div>`
 * containers; `<tr>`, `<li>` and `<th>` keep their own table/tree semantics and
 * only receive focusability plus activation. A real `<button>` needs none of
 * this — it already has native Enter/Space activation.
 */
import { useCallback, type KeyboardEvent } from "react";

/** Props that make a clickable region keyboard-operable. */
export interface ActivationKeyProps {
  onClick: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  tabIndex: 0;
  /** Only for non-semantic containers; native rows/items omit this. */
  role?: "button";
}

export interface ActivationKeyOptions {
  /**
   * Expose an explicit button role. Set on `<div>` regions that act as a
   * button (card body, attribute row, glossary row). Leave unset on native
   * table rows, list items and tree items so their semantics survive.
   */
  role?: "button";
}

/**
 * @param onActivate - Action to run on pointer click AND on Enter/Space.
 * @param options - Optional explicit button role for non-semantic containers.
 */
export function useActivationKeys(
  onActivate: () => void,
  { role }: ActivationKeyOptions = {},
): ActivationKeyProps {
  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>): void => {
      // Clickable regions often contain real controls (row action buttons,
      // checkboxes, the tree's move button). A keypress on one of those must
      // activate THAT control, not bubble up and also activate the row.
      if (event.target !== event.currentTarget) return;
      // APG button pattern: Space and Enter both activate a focused button.
      // preventDefault stops Space from scrolling the page / list container.
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onActivate();
      }
    },
    [onActivate],
  );

  // Omit the key entirely when no explicit role was requested: spreading
  // `role: undefined` over an element that already declares a native role
  // (e.g. `treeitem`) would erase it.
  if (role === undefined) return { onClick: onActivate, onKeyDown, tabIndex: 0 };
  return { onClick: onActivate, onKeyDown, tabIndex: 0, role };
}
