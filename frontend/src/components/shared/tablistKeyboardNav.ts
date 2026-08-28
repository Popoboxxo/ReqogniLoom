/**
 * UI-41 (systemaudit 2026-08-27): shared ARIA APG "tabs" keyboard pattern.
 *
 * SystemSettings, WorkspaceSettings and PresetSegmentedControl each render a
 * `role="tablist"` of `role="tab"` buttons that were only mouse/click
 * operable — every tab button was a plain, individually-tabbable `<button>`
 * (technically reachable, but not the roving-tabindex + arrow-key model the
 * ARIA Authoring Practices Guide specifies for the tabs pattern, which is
 * what screen reader users expect once they hear "tab, 1 of N"). This helper
 * is attached once to the `role="tablist"` container (event delegation, no
 * per-button wiring) and:
 *   - Left/Right (Home/End) move + immediately activate the neighboring tab
 *     (the "automatic activation" model — matches how these tabs already
 *     activate on click, so this does not change their activation contract)
 *   - moves real DOM focus to the newly active tab so Tab/Shift+Tab
 *     continues from there, not from wherever the list started
 *
 * Pair with `tabRovingTabIndex(id, activeId)` on each tab button so only the
 * active tab is a Tab-stop and the others are reachable via arrow keys only,
 * per the APG roving-tabindex recommendation.
 */

/** `tabIndex` for one tab button in a roving-tabindex tablist. */
export function tabRovingTabIndex<T extends string>(id: T, activeId: T): 0 | -1 {
  return id === activeId ? 0 : -1;
}

const NAV_KEYS = new Set(["ArrowLeft", "ArrowRight", "Home", "End"]);

/**
 * `onKeyDown` handler for a `role="tablist"` container. `ids` must be in the
 * same left-to-right order as the rendered `role="tab"` buttons.
 */
export function handleTablistKeyDown<T extends string>(
  e: React.KeyboardEvent<HTMLElement>,
  ids: readonly T[],
  activeId: T,
  onChange: (id: T) => void
): void {
  if (!NAV_KEYS.has(e.key) || ids.length === 0) return;
  e.preventDefault();

  const currentIndex = Math.max(0, ids.indexOf(activeId));
  let nextIndex = currentIndex;
  if (e.key === "ArrowLeft") nextIndex = (currentIndex - 1 + ids.length) % ids.length;
  else if (e.key === "ArrowRight") nextIndex = (currentIndex + 1) % ids.length;
  else if (e.key === "Home") nextIndex = 0;
  else if (e.key === "End") nextIndex = ids.length - 1;

  const nextId = ids[nextIndex];
  if (nextId === activeId) return;
  onChange(nextId);

  const container = e.currentTarget;
  requestAnimationFrame(() => {
    const tabs = container.querySelectorAll<HTMLElement>('[role="tab"]');
    tabs[nextIndex]?.focus();
  });
}
