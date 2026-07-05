/**
 * ARCH-L1-001 ReactFrontend — DecompositionTree (COMP-RF-004).
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-001 (Hierarchie-Tree-View für L0-L4 Zerlegungsbaum),
 *          REQ-003 (skalierbare Listen-Toolbar — Suche/Filter/Sortierung)
 *
 * Left-sidebar tree panel for the Architecture editor (Phase 1 MVP per
 * docs/DESIGN_TREE_VIEW_L0_L4_HIERARCHY.md):
 *   - Transforms the flat /api/v1/architecture/ list (parent_id relation)
 *     into a client-side tree
 *   - Expand/Collapse per node, level badges L0-L4 (design-doc colors)
 *   - Search box (300ms debounce; matches stay visible with their parents)
 *   - Click-to-select → parent switches the main editor (node highlight)
 *   - Right-click context menu: Show Details / Edit / Add Child /
 *     Link to Requirement / Delete (handlers provided by the parent)
 *   - Accessibility: role="tree"/"treeitem", aria-expanded, keyboard
 *     navigation (Arrow keys, Enter, Escape)
 *
 * Phase 2 (REQ-001): drag&drop reparenting — drag a node onto another
 * node to make it that node's child, or onto the root dropzone (shown
 * while dragging) to detach it to L0. Dropping onto the element itself
 * is blocked client-side; cycles are rejected by the backend hierarchy
 * invariants and surfaced by the parent via an inline error banner.
 *
 * Out of scope: requirement link nodes.
 */

import { useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import type { ArchitectureElement, ElementType } from "../../types";
import { ListToolbar } from "../shared/ListToolbar";

// ---------------------------------------------------------------------------
// Level badge colors (design doc section 6 — level_badge)
// ---------------------------------------------------------------------------

const LEVEL_BADGE_COLORS: Record<number, string> = {
  0: "#1E3A8A", // L0 dark blue
  1: "#3B82F6", // L1 blue
  2: "#06B6D4", // L2 cyan
  3: "#10B981", // L3 green
  4: "#9CA3AF", // L4 gray
};

function levelBadgeColor(level: number): string {
  return LEVEL_BADGE_COLORS[Math.min(Math.max(level, 0), 4)];
}

// ---------------------------------------------------------------------------
// Tree model
// ---------------------------------------------------------------------------

interface TreeNode {
  element: ArchitectureElement;
  children: TreeNode[];
  level: number;
}

/** Sibling ordering inside the tree (REQ-003). "default" keeps API order. */
type TreeSortKey = "default" | "title" | "updated";

function siblingComparator(
  sortKey: TreeSortKey,
): ((a: ArchitectureElement, b: ArchitectureElement) => number) | null {
  switch (sortKey) {
    case "title":
      return (a, b) => a.title.localeCompare(b.title);
    case "updated":
      // ISO 8601 timestamps compare correctly as strings (newest first).
      return (a, b) => b.updated_at.localeCompare(a.updated_at);
    default:
      return null;
  }
}

/** Transform the flat API list into a tree via parent_id. */
function buildTree(
  elements: ArchitectureElement[],
  sortKey: TreeSortKey = "default",
): TreeNode[] {
  const byId = new Map<string, ArchitectureElement>();
  for (const el of elements) byId.set(el.id, el);

  const childrenByParent = new Map<string | null, ArchitectureElement[]>();
  for (const el of elements) {
    // Treat elements whose parent is unknown (other page / deleted) as roots.
    const parentKey =
      el.parent_id && byId.has(el.parent_id) ? el.parent_id : null;
    const bucket = childrenByParent.get(parentKey);
    if (bucket) bucket.push(el);
    else childrenByParent.set(parentKey, [el]);
  }

  // Sort siblings in place — buckets are local copies (REQ-003).
  const compare = siblingComparator(sortKey);
  if (compare) {
    for (const bucket of childrenByParent.values()) bucket.sort(compare);
  }

  const toNode = (
    el: ArchitectureElement,
    level: number,
    seen: Set<string>,
  ): TreeNode => {
    // Cycle guard — malformed parent chains must not blow the stack.
    seen.add(el.id);
    const kids = (childrenByParent.get(el.id) ?? []).filter(
      (child) => !seen.has(child.id),
    );
    return {
      element: el,
      level: el.level ?? level,
      children: kids.map((child) => toNode(child, level + 1, seen)),
    };
  };

  const seen = new Set<string>();
  return (childrenByParent.get(null) ?? []).map((root) =>
    toNode(root, 0, seen),
  );
}

/** Flattened, currently visible nodes (respects expand state + filter). */
interface VisibleNode {
  node: TreeNode;
  depth: number;
  hasChildren: boolean;
  isExpanded: boolean;
}

function flattenVisible(
  nodes: TreeNode[],
  expanded: Set<string>,
  visibleIds: Set<string> | null,
  depth = 0,
  out: VisibleNode[] = [],
): VisibleNode[] {
  for (const node of nodes) {
    if (visibleIds !== null && !visibleIds.has(node.element.id)) continue;
    const visibleChildren =
      visibleIds === null
        ? node.children
        : node.children.filter((c) => visibleIds.has(c.element.id));
    const hasChildren = visibleChildren.length > 0;
    // While searching, matched subtrees are force-expanded so results show.
    const isExpanded =
      visibleIds !== null ? true : expanded.has(node.element.id);
    out.push({ node, depth, hasChildren, isExpanded });
    if (hasChildren && isExpanded) {
      flattenVisible(node.children, expanded, visibleIds, depth + 1, out);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Toolbar filter options (REQ-003)
// ---------------------------------------------------------------------------

const ELEMENT_TYPE_OPTIONS: { value: ElementType; labelKey: string }[] = [
  { value: "component", labelKey: "arch.elementType.component" },
  { value: "interface", labelKey: "arch.elementType.interface" },
  { value: "subsystem", labelKey: "arch.elementType.subsystem" },
  { value: "layer", labelKey: "arch.elementType.layer" },
  { value: "module", labelKey: "arch.elementType.module" },
];

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------

interface ContextMenuState {
  x: number;
  y: number;
  element: ArchitectureElement;
}

export interface DecompositionTreeProps {
  elements: ArchitectureElement[];
  selectedId?: string;
  /** Click / Enter on a node — switches the main editor. */
  onSelect: (id: string) => void;
  /** Context menu: create a child element under the given parent. */
  onAddChild: (parentId: string) => void;
  /** Context menu: delete the element (parent shows its confirm dialog). */
  onDelete: (element: ArchitectureElement) => void;
  /**
   * Drag&drop reparenting (REQ-001): move an element under a new parent.
   * `newParentId = null` detaches the element to root level (L0).
   * The parent component performs the PATCH and refreshes the tree.
   */
  onReparent: (elementId: string, newParentId: string | null) => void;
}

export function DecompositionTree({
  elements,
  selectedId,
  onSelect,
  onAddChild,
  onDelete,
  onReparent,
}: DecompositionTreeProps): JSX.Element {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  // Toolbar filter/sort state (REQ-003 — scalable list panel).
  const [typeFilter, setTypeFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState("");
  const [sortKey, setSortKey] = useState<TreeSortKey>("default");
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  // Drag&drop reparenting state (REQ-001). "__root__" marks the root
  // dropzone as the current drop target.
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const treeRef = useRef<HTMLUListElement | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const didInitExpandRef = useRef(false);

  const tree = useMemo(() => buildTree(elements, sortKey), [elements, sortKey]);

  // Default-expand the root level once elements arrive (design journey step 1).
  useEffect(() => {
    if (didInitExpandRef.current || tree.length === 0) return;
    didInitExpandRef.current = true;
    setExpanded(new Set(tree.map((n) => n.element.id)));
  }, [tree]);

  // 300ms debounce on the search input (design doc section 4).
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setSearchQuery(searchInput), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchInput]);

  // Search + type/level filter: matching nodes and all their ancestors stay
  // visible so the hierarchy context is preserved (REQ-001, REQ-003).
  const visibleIds = useMemo((): Set<string> | null => {
    const q = searchQuery.trim().toLowerCase();
    if (!q && !typeFilter && !levelFilter) return null;
    const parentById = new Map<string, string | null>();
    const idSet = new Set(elements.map((e) => e.id));
    for (const el of elements) {
      parentById.set(
        el.id,
        el.parent_id && idSet.has(el.parent_id) ? el.parent_id : null,
      );
    }
    const visible = new Set<string>();
    for (const el of elements) {
      const matchesSearch =
        !q ||
        el.title.toLowerCase().includes(q) ||
        el.id.toLowerCase().includes(q);
      const matchesType = !typeFilter || el.element_type === typeFilter;
      const matchesLevel =
        !levelFilter || String(el.level ?? 0) === levelFilter;
      if (!matchesSearch || !matchesType || !matchesLevel) continue;
      // Include the match and walk up the ancestor chain.
      let cursor: string | null = el.id;
      while (cursor && !visible.has(cursor)) {
        visible.add(cursor);
        cursor = parentById.get(cursor) ?? null;
      }
    }
    return visible;
  }, [elements, searchQuery, typeFilter, levelFilter]);

  const visibleNodes = useMemo(
    () => flattenVisible(tree, expanded, visibleIds),
    [tree, expanded, visibleIds],
  );

  // Level filter options are derived from the data — only levels that
  // actually occur are offered (REQ-003).
  const levelOptions = useMemo((): string[] => {
    const levels = new Set<number>();
    for (const el of elements) levels.add(el.level ?? 0);
    return [...levels].sort((a, b) => a - b).map(String);
  }, [elements]);

  const hasActiveFilter =
    searchQuery.trim() !== "" || typeFilter !== "" || levelFilter !== "";

  const toggleExpand = useCallback((id: string): void => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // Close the context menu on outside click / Escape.
  useEffect(() => {
    if (!contextMenu) return;
    const handleClick = (): void => setContextMenu(null);
    const handleKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") setContextMenu(null);
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [contextMenu]);

  // ---- Drag & drop reparenting (REQ-001) ------------------------------------

  const parentById = useMemo((): Map<string, string | null> => {
    const map = new Map<string, string | null>();
    for (const el of elements) map.set(el.id, el.parent_id ?? null);
    return map;
  }, [elements]);

  const resetDrag = useCallback((): void => {
    setDraggingId(null);
    setDropTargetId(null);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent, newParentId: string | null): void => {
      e.preventDefault();
      e.stopPropagation();
      const draggedId = e.dataTransfer.getData("text/plain") || draggingId;
      resetDrag();
      if (!draggedId) return;
      // Self-drop is a no-op. Deeper cycle attempts (dropping onto an
      // own descendant) are sent to the backend, which rejects them via
      // the hierarchy invariants — the parent shows the error inline.
      if (newParentId === draggedId) return;
      // Dropping onto the current parent changes nothing.
      if ((parentById.get(draggedId) ?? null) === newParentId) return;
      onReparent(draggedId, newParentId);
    },
    [draggingId, parentById, resetDrag, onReparent],
  );

  // ---- Keyboard navigation (design doc section 10) -------------------------

  const focusNode = useCallback((id: string): void => {
    setFocusedId(id);
    // Move DOM focus to the treeitem for screen readers.
    const el = treeRef.current?.querySelector<HTMLElement>(
      `[data-node-id="${id}"]`,
    );
    el?.focus();
  }, []);

  const handleTreeKeyDown = useCallback(
    (e: React.KeyboardEvent): void => {
      if (visibleNodes.length === 0) return;
      const currentIndex = visibleNodes.findIndex(
        (v) => v.node.element.id === (focusedId ?? selectedId),
      );

      switch (e.key) {
        case "ArrowDown": {
          e.preventDefault();
          const next = visibleNodes[Math.min(currentIndex + 1, visibleNodes.length - 1)];
          if (next) focusNode(next.node.element.id);
          break;
        }
        case "ArrowUp": {
          e.preventDefault();
          const prev = visibleNodes[Math.max(currentIndex - 1, 0)];
          if (prev) focusNode(prev.node.element.id);
          break;
        }
        case "ArrowRight": {
          e.preventDefault();
          const current = visibleNodes[currentIndex];
          if (!current) break;
          if (current.hasChildren && !current.isExpanded) {
            toggleExpand(current.node.element.id);
          } else if (current.hasChildren) {
            const next = visibleNodes[currentIndex + 1];
            if (next) focusNode(next.node.element.id);
          }
          break;
        }
        case "ArrowLeft": {
          e.preventDefault();
          const current = visibleNodes[currentIndex];
          if (!current) break;
          if (current.hasChildren && current.isExpanded) {
            toggleExpand(current.node.element.id);
          }
          break;
        }
        case "Enter":
        case " ": {
          e.preventDefault();
          const current = visibleNodes[currentIndex];
          if (current) onSelect(current.node.element.id);
          break;
        }
        case "Escape": {
          e.preventDefault();
          setContextMenu(null);
          setSearchInput("");
          break;
        }
        default:
          break;
      }
    },
    [visibleNodes, focusedId, selectedId, focusNode, toggleExpand, onSelect],
  );

  // ---- Render ---------------------------------------------------------------

  return (
    <div
      data-testid="decomposition-tree"
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}
    >
      {/* Toolbar: search box (design doc section 6 — search_box) plus
          type/level filters and sibling sort (REQ-003). */}
      <ListToolbar
        testIdPrefix="tree"
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        searchPlaceholder={t("arch.tree.searchPlaceholder", "Search elements...")}
        filters={[
          {
            id: "type",
            allLabel: t("arch.tree.allTypes", "All types"),
            value: typeFilter,
            options: ELEMENT_TYPE_OPTIONS.map((et) => ({
              value: et.value,
              label: t(et.labelKey),
            })),
            onChange: setTypeFilter,
          },
          {
            id: "level",
            allLabel: t("arch.tree.allLevels", "All levels"),
            value: levelFilter,
            options: levelOptions.map((lvl) => ({
              value: lvl,
              label: `L${lvl}`,
            })),
            onChange: setLevelFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: "default", label: t("arch.tree.sortDefault", "Default order") },
          { value: "title", label: t("arch.tree.sortTitleAsc", "Title (A–Z)") },
          { value: "updated", label: t("arch.tree.sortUpdatedDesc", "Last updated") },
        ]}
        onSortChange={(value) => setSortKey(value as TreeSortKey)}
        sortLabel={t("arch.tree.sortLabel", "Sort by")}
        countLabel={
          hasActiveFilter
            ? t("arch.tree.filteredCount", {
                defaultValue: "{{shown}} of {{total}}",
                shown: visibleNodes.length,
                total: elements.length,
              })
            : null
        }
      />

      {/* Root dropzone — visible while dragging; dropping detaches the
          element to root level L0 (REQ-001). */}
      {draggingId && (
        <div
          data-testid="tree-root-dropzone"
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            if (dropTargetId !== "__root__") setDropTargetId("__root__");
          }}
          onDragLeave={(e) => {
            const related = e.relatedTarget as Node | null;
            if (related && e.currentTarget.contains(related)) return;
            if (dropTargetId === "__root__") setDropTargetId(null);
          }}
          onDrop={(e) => handleDrop(e, null)}
          style={{
            border:
              dropTargetId === "__root__"
                ? "2px dashed #3B82F6"
                : "2px dashed var(--color-border)",
            background:
              dropTargetId === "__root__" ? "#EFF6FF" : "transparent",
            borderRadius: "var(--radius-sm)",
            padding: "var(--space-2)",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            textAlign: "center",
            userSelect: "none",
          }}
        >
          {t("arch.tree.dropRoot", "Drop here to make root (L0)")}
        </div>
      )}

      {visibleNodes.length === 0 ? (
        <p
          data-testid="tree-empty"
          style={{
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
            margin: "var(--space-2) 0",
          }}
        >
          {hasActiveFilter
            ? t("arch.tree.noMatches", "No matching elements")
            : t("editor.empty")}
        </p>
      ) : (
        <ul
          ref={treeRef}
          role="tree"
          aria-label={t("nav.architecture")}
          data-testid="tree-root"
          onKeyDown={handleTreeKeyDown}
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "2px",
          }}
        >
          {visibleNodes.map(({ node, depth, hasChildren, isExpanded }) => {
            const el = node.element;
            const isSelected = el.id === selectedId;
            const isFocused = el.id === (focusedId ?? selectedId);
            const isDropTarget = dropTargetId === el.id;
            const isDragging = draggingId === el.id;
            const level = Math.min(Math.max(el.level ?? depth, 0), 4);
            return (
              <li
                key={el.id}
                role="treeitem"
                aria-expanded={hasChildren ? isExpanded : undefined}
                aria-selected={isSelected}
                aria-level={depth + 1}
                data-node-id={el.id}
                data-testid={`tree-node-${el.id}`}
                tabIndex={isFocused ? 0 : -1}
                onClick={() => {
                  setFocusedId(el.id);
                  onSelect(el.id);
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setFocusedId(el.id);
                  setContextMenu({ x: e.clientX, y: e.clientY, element: el });
                }}
                // Drag&drop reparenting (REQ-001) — native HTML5 D&D.
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("text/plain", el.id);
                  e.dataTransfer.effectAllowed = "move";
                  setDraggingId(el.id);
                }}
                onDragEnd={resetDrag}
                onDragOver={(e) => {
                  if (!draggingId || draggingId === el.id) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  if (dropTargetId !== el.id) setDropTargetId(el.id);
                }}
                onDragLeave={(e) => {
                  // Native D&D fires dragleave when the pointer crosses onto a
                  // nested child (expand button, title span, badge) even though
                  // it's still logically over the same row — ignore those to
                  // avoid the drop-target highlight flickering during drag.
                  const related = e.relatedTarget as Node | null;
                  if (related && e.currentTarget.contains(related)) return;
                  if (dropTargetId === el.id) setDropTargetId(null);
                }}
                onDrop={(e) => handleDrop(e, el.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-1)",
                  minHeight: "32px",
                  padding: "4px 8px",
                  paddingLeft: `${8 + depth * 16}px`,
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  userSelect: "none",
                  // Selected styling per design doc section 6 (node_styling.selected)
                  background: isDropTarget
                    ? "#EFF6FF"
                    : isSelected
                      ? "#DBEAFE"
                      : "transparent",
                  borderLeft: isSelected
                    ? "3px solid #3B82F6"
                    : "3px solid transparent",
                  color: "var(--color-text)",
                  transition: "var(--transition-fast)",
                  // Drop-zone highlight while dragging over (REQ-001).
                  outline: isDropTarget ? "2px dashed #3B82F6" : "none",
                  outlineOffset: "-2px",
                  opacity: isDragging ? 0.5 : 1,
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLLIElement).style.background =
                      "var(--color-surface-raised)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLLIElement).style.background =
                      "transparent";
                  }
                }}
              >
                {/* Expand / collapse icon */}
                {hasChildren ? (
                  <button
                    type="button"
                    data-testid={`tree-toggle-${el.id}`}
                    aria-label={
                      isExpanded
                        ? t("arch.tree.collapse", "Collapse")
                        : t("arch.tree.expand", "Expand")
                    }
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleExpand(el.id);
                    }}
                    style={{
                      width: "16px",
                      height: "16px",
                      padding: 0,
                      border: "none",
                      background: "transparent",
                      color: "#6B7280",
                      cursor: "pointer",
                      fontSize: "0.7rem",
                      lineHeight: 1,
                      flexShrink: 0,
                      transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                      transition: "transform 200ms ease-out",
                    }}
                  >
                    ▶
                  </button>
                ) : (
                  <span
                    aria-hidden="true"
                    style={{ width: "16px", flexShrink: 0 }}
                  />
                )}

                {/* Node title */}
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    fontSize: "var(--font-size-sm)",
                    fontWeight: isSelected ? 600 : 500,
                  }}
                  title={el.title || t("editor.untitled")}
                >
                  {el.title || t("editor.untitled")}
                </span>

                {/* Level badge (design doc section 6 — level_badge) */}
                <span
                  data-testid={`tree-level-badge-${el.id}`}
                  style={{
                    flexShrink: 0,
                    fontSize: "12px",
                    padding: "1px 6px",
                    borderRadius: "var(--radius-full)",
                    background: levelBadgeColor(level),
                    color: "white",
                    fontWeight: 600,
                    lineHeight: "16px",
                  }}
                >
                  L{level}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {/* Context menu (design doc section 6 — context_menu) */}
      {contextMenu && (
        <ul
          role="menu"
          data-testid="tree-context-menu"
          // Prevent the outside-click closer from firing on menu clicks.
          onMouseDown={(e) => e.stopPropagation()}
          style={{
            position: "fixed",
            top: `${contextMenu.y}px`,
            left: `${contextMenu.x}px`,
            width: "180px",
            listStyle: "none",
            margin: 0,
            padding: "var(--space-1)",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "4px",
            boxShadow: "0 10px 15px rgba(0,0,0,0.1)",
            zIndex: 1000,
          }}
        >
          <ContextMenuItem
            testId="tree-ctx-show-details"
            label={t("arch.tree.showDetails", "Show Details")}
            onClick={() => {
              onSelect(contextMenu.element.id);
              setContextMenu(null);
            }}
          />
          <ContextMenuItem
            testId="tree-ctx-edit"
            label={t("arch.tree.edit", "Edit")}
            onClick={() => {
              // The detail editor IS the edit surface — same navigation.
              onSelect(contextMenu.element.id);
              setContextMenu(null);
            }}
          />
          <ContextMenuItem
            testId="tree-ctx-add-child"
            label={t("arch.tree.addChild", "Add Child")}
            onClick={() => {
              onAddChild(contextMenu.element.id);
              setContextMenu(null);
            }}
          />
          <ContextMenuItem
            testId="tree-ctx-link-requirement"
            label={t("arch.tree.linkRequirement", "Link to Requirement")}
            onClick={() => {
              // Linking happens in the detail view's TraceLink panel.
              onSelect(contextMenu.element.id);
              setContextMenu(null);
            }}
          />
          <li
            aria-hidden="true"
            style={{
              borderTop: "1px solid #E5E7EB",
              margin: "var(--space-1) 0",
            }}
          />
          <ContextMenuItem
            testId="tree-ctx-delete"
            label={t("actions.delete")}
            danger
            onClick={() => {
              onDelete(contextMenu.element);
              setContextMenu(null);
            }}
          />
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Context menu item
// ---------------------------------------------------------------------------

interface ContextMenuItemProps {
  label: string;
  onClick: () => void;
  testId: string;
  danger?: boolean;
}

function ContextMenuItem({
  label,
  onClick,
  testId,
  danger = false,
}: ContextMenuItemProps): JSX.Element {
  return (
    <li role="none">
      <button
        type="button"
        role="menuitem"
        data-testid={testId}
        onClick={onClick}
        style={{
          display: "block",
          width: "100%",
          height: "32px",
          padding: "0 var(--space-3)",
          border: "none",
          background: "transparent",
          color: danger ? "var(--color-danger)" : "var(--color-text)",
          fontSize: "var(--font-size-sm)",
          fontFamily: "inherit",
          textAlign: "left",
          cursor: "pointer",
          borderRadius: "var(--radius-sm)",
          transition: "var(--transition-fast)",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.background =
            "var(--color-surface-raised)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.background =
            "transparent";
        }}
      >
        {label}
      </button>
    </li>
  );
}
