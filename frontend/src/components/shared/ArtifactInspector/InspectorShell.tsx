/**
 * ArtifactInspector — the tabbed shell (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L0-062 (unified artifact inspector),
 *          REQ-L1-089 (unified shell), REQ-L1-093 (accessibility baseline)
 *
 * One component, three forms (spec §2.1, D3/B1):
 *
 *   panel       inline third zone of the detail area (R1/R2)
 *   rail        40 px strip, the collapsed state of the *same* node
 *   sheet       non-modal overlay over the detail area (R3/R4)
 *   fullscreen  one-column surface that replaces the content (R5)
 *
 * Rail and sheet are not two components: this is one `<aside>` whose content
 * changes. In the rail state the sheet content is not rendered, in the sheet
 * state the rail content is not rendered — so the accessibility tree never
 * holds a second, invisible set of counters or tabs (WCAG 1.3.1/4.1.2).
 *
 * What the shell owns (and therefore what the four panels no longer own):
 *
 *  - the tablist and the **manual activation** model (spec §5.1/§5.2),
 *  - the two live regions — one polite, one alert (spec §5.3),
 *  - the splitter and its keyboard model (spec §5.1 #5),
 *  - the `inert` bracket around the covered detail area in sheet form
 *    (spec §4.2, WCAG 2.2 SC 2.4.11),
 *  - the type matrix: which tabs exist is derived from `kind` + `artifactPk`
 *    only, never from a route switch (spec §8.2).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import {
  INSPECTOR_HEADING_ID,
  INSPECTOR_RESIZE_STEP_PX,
  INSPECTOR_SURFACE_ID,
  INSPECTOR_TEST_IDS,
  INSPECTOR_WIDTHS,
  INSPECTOR_DEFAULT_TAB,
  inspectorPanelId,
  inspectorTabId,
  inspectorTabKeys,
  inspectorTabStorageKey,
  type InspectorTabKey,
} from "./inspectorContract";
import {
  InspectorAnnounceProvider,
  useInspectorAnnouncer,
  useInspectorCounts,
} from "./InspectorLiveRegions";
import { InspectorRail } from "./InspectorRail";
import { InspectorSheet } from "./InspectorSheet";
import { InspectorTabs } from "./InspectorTabs";
import {
  readStoredTab,
  readTabFromUrl,
  useInspectorLayout,
  writeStoredTab,
  writeTabToUrl,
  type InspectorLayout,
} from "./useInspectorLayout";
import { useInertBehindSheet } from "./useInertBehindSheet";
import { VersionTab } from "./tabs/VersionTab";
import { DiffTab } from "./tabs/DiffTab";
import { LinksTab } from "./tabs/LinksTab";
import { CommentsTab } from "./tabs/CommentsTab";
import type { ArtifactKind, VersionRef } from "./types";
import styles from "./InspectorShell.module.css";

export interface InspectorShellProps {
  kind: ArtifactKind;
  /**
   * The **domain-entity** id (`Requirement.id`, `Risk.id`, …). Version, diff
   * and links are keyed on it.
   */
  entityId: string | number;
  /**
   * The **backing generic Artifact UUID** — the only id space the comments
   * route accepts (#1763, spec D5). `null` means "not published for this
   * kind": the comments tab is then **not rendered** (spec §4.3).
   */
  artifactPk: string | null;
  currentVersion?: VersionRef;
  /** Deep link / test override; otherwise storage, then the default tab. */
  initialTab?: InspectorTabKey;
  /**
   * The detail area the sheet covers. It gets `inert` while the sheet is
   * open (spec §4.2). Routes that do not pass it keep the inspector usable —
   * they just do not get the non-modal bracket.
   */
  coveredRef?: React.RefObject<HTMLElement | null>;
  /** Jump target of the Links tab's summary line (spec §2.3). */
  onShowInSpine?: () => void;
}

export function InspectorShell(props: InspectorShellProps): JSX.Element {
  const { kind } = props;
  const layout = useInspectorLayout(kind);
  const surfaceRef = useRef<HTMLElement | null>(null);

  // The panel width lives in a CSS custom property, not in an inline
  // style-object literal: the ratchet counts those under `components/`, and
  // a CSSOM write is the documented alternative (spec §6.1, §8.3).
  useEffect(() => {
    surfaceRef.current?.style.setProperty("--inspector-width", `${layout.widthPx}px`);
  }, [layout.widthPx]);

  return (
    <aside
      ref={surfaceRef}
      id={INSPECTOR_SURFACE_ID}
      className={`${styles.shell} ${styles[layout.form] ?? ""}`}
      aria-labelledby={INSPECTOR_HEADING_ID}
      // Literal on purpose: the E2E testid-drift gate (issue #1113) only
      // resolves literal ids, and this is the shell's public root marker.
      data-testid="inspector-shell"
      data-artifact-kind={kind}
      data-inspector-form={layout.form}
      data-inspector-width={layout.widthPx}
    >
      <InspectorAnnounceProvider>
        <InspectorShellBody {...props} layout={layout} />
      </InspectorAnnounceProvider>
    </aside>
  );
}

interface InspectorShellBodyProps extends InspectorShellProps {
  layout: InspectorLayout;
}

function InspectorShellBody({
  kind,
  entityId,
  artifactPk,
  currentVersion,
  initialTab,
  coveredRef,
  onShowInSpine,
  layout,
}: InspectorShellBodyProps): JSX.Element {
  const { t } = useTranslation();
  const announcer = useInspectorAnnouncer();
  const countsValue = useInspectorCounts();
  const counts = useMemo(() => countsValue?.counts ?? {}, [countsValue]);

  const tabs = useMemo(
    () => inspectorTabKeys(kind, artifactPk),
    [kind, artifactPk],
  );

  const storageKey = useMemo(
    () => inspectorTabStorageKey(kind, entityId),
    [kind, entityId],
  );

  const [tabState, setTabState] = useState<InspectorTabKey>(() => {
    if (initialTab && tabs.includes(initialTab)) return initialTab;
    return readTabFromUrl(tabs) ?? readStoredTab(storageKey, tabs) ?? tabs[0] ?? INSPECTOR_DEFAULT_TAB;
  });

  // A tab that disappeared (e.g. the comments tab after `artifactPk` went
  // null) must not leave the shell on a panel it no longer has.
  const activeTab = tabs.includes(tabState) ? tabState : (tabs[0] ?? INSPECTOR_DEFAULT_TAB);

  const headerRef = useRef<HTMLDivElement | null>(null);
  const noCoveredRef = useRef<HTMLElement | null>(null);

  // -------------------------------------------------------------------------
  // Diff selection (owned by the shell, as in the stacked sidebar)
  // -------------------------------------------------------------------------
  //
  // M-04: `diffLeft` starts equal to `diffRight` — an empty range that names
  // no comparison at all. `ArtifactDiff` treats it as a request and falls back
  // to its own seeding; the Diff tab's pair line reports what was *resolved*,
  // never this placeholder.
  const [diffLeft, setDiffLeft] = useState<number>(() => currentVersion?.version ?? 1);
  const [diffRight, setDiffRight] = useState<number>(() => currentVersion?.version ?? 1);

  useEffect(() => {
    if (currentVersion) {
      setDiffRight((prev) => (prev === currentVersion.version ? prev : currentVersion.version));
    }
  }, [currentVersion]);

  const handleSwitchVersion = useCallback(
    (version: number): void => {
      if (currentVersion) setDiffLeft(currentVersion.version);
      setDiffRight(version);
    },
    [currentVersion],
  );

  const handleCompareVersions = useCallback((a: number, b: number): void => {
    setDiffLeft(a);
    setDiffRight(b);
  }, []);

  // -------------------------------------------------------------------------
  // Wrap / bracket
  // -------------------------------------------------------------------------

  // Spec §4.2: the sheet covers the detail area, so that area is `inert`
  // while it is open — the list stays operable, and no focusable element is
  // left hidden behind the sheet (SC 2.4.11).
  useInertBehindSheet(
    coveredRef ?? noCoveredRef,
    layout.form === "sheet" && layout.open,
  );

  // -------------------------------------------------------------------------
  // Focus moves (spec §5.1)
  // -------------------------------------------------------------------------

  const previousFormRef = useRef(layout.form);
  useEffect(() => {
    const previous = previousFormRef.current;
    if (previous === layout.form) return;
    previousFormRef.current = layout.form;

    if (layout.form === "rail") {
      document
        .querySelector<HTMLElement>(`[data-testid="${INSPECTOR_TEST_IDS.railOpen}"]`)
        ?.focus();
      return;
    }
    if (layout.form === "sheet" || layout.form === "fullscreen") {
      document.getElementById(inspectorTabId(activeTab))?.focus();
      return;
    }
    headerRef.current?.focus();
  }, [layout.form, activeTab]);

  // -------------------------------------------------------------------------
  // Tab activation (manual activation, spec §5.2)
  // -------------------------------------------------------------------------

  const tabLabel = useCallback(
    (key: InspectorTabKey): string =>
      key === "version"
        ? t("sidebar.version.title")
        : key === "diff"
          ? t("sidebar.diff.title")
          : key === "links"
            ? t("sidebar.inspector.tab.links")
            : t("comments.heading"),
    [t],
  );

  const activateTab = useCallback(
    (next: InspectorTabKey): void => {
      if (next === activeTab) return;
      setTabState(next);
      writeStoredTab(storageKey, next);
      writeTabToUrl(next);
      // Deferred and superseded by the panel's own `xxxLoaded` message if it
      // answers in the same task — "exactly one announcement" (spec §5.3).
      announcer?.tabChanged(
        t("sidebar.inspector.live.tabChanged", {
          tab: tabLabel(next),
          count: counts[next] ?? 0,
          defaultValue: "{{tab}} section, {{count}} items.",
        }),
      );
    },
    [activeTab, announcer, counts, storageKey, tabLabel, t],
  );

  const openOnTab = useCallback(
    (next: InspectorTabKey): void => {
      setTabState(next);
      writeStoredTab(storageKey, next);
      writeTabToUrl(next);
      layout.setOpen(true);
    },
    [layout, storageKey],
  );

  const close = useCallback((): void => layout.setOpen(false), [layout]);

  // -------------------------------------------------------------------------
  // Keyboard contracts: Alt+I / Alt+Shift+I (spec §5.2)
  // -------------------------------------------------------------------------

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (!event.altKey || event.key.toLowerCase() !== "i") return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      if (event.shiftKey) {
        layout.toggleOpen();
        return;
      }
      if (!layout.open) {
        layout.setOpen(true);
        return;
      }
      document.getElementById(inspectorTabId(activeTab))?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [layout, activeTab]);

  // -------------------------------------------------------------------------
  // Splitter (spec §5.1 #5, §5.2)
  // -------------------------------------------------------------------------

  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const onSplitterPointerDown = useCallback(
    (event: React.MouseEvent<HTMLDivElement>): void => {
      dragRef.current = { startX: event.clientX, startWidth: layout.widthPx };
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
      event.preventDefault();
    },
    [layout.widthPx],
  );

  useEffect(() => {
    function onMove(event: MouseEvent): void {
      const drag = dragRef.current;
      if (!drag) return;
      // The inspector sits on the right edge: dragging left widens it.
      layout.setWidthPx(drag.startWidth + (drag.startX - event.clientX));
    }
    function onUp(): void {
      if (!dragRef.current) return;
      dragRef.current = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [layout]);

  const onSplitterKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>): void => {
      let next: number | null = null;
      if (event.key === "ArrowLeft") next = layout.widthPx + INSPECTOR_RESIZE_STEP_PX;
      else if (event.key === "ArrowRight") next = layout.widthPx - INSPECTOR_RESIZE_STEP_PX;
      else if (event.key === "Home") next = INSPECTOR_WIDTHS.min;
      else if (event.key === "End") next = INSPECTOR_WIDTHS.max;
      else if (event.key === "Enter") {
        event.preventDefault();
        close();
        return;
      }
      if (next === null) return;
      event.preventDefault();
      layout.setWidthPx(next);
      announcer?.polite(
        t("sidebar.inspector.live.resized", {
          width: next,
          defaultValue: "Inspector {{width}} pixels wide.",
        }),
      );
    },
    [announcer, close, layout, t],
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const header = (
    <div className={styles.header} ref={headerRef} tabIndex={-1}>
      <h2
        id={INSPECTOR_HEADING_ID}
        className={styles.heading}
        tabIndex={-1}
      >
        {t("sidebar.inspector.title")}
      </h2>
      <button
        type="button"
        className="btn-icon"
        aria-label={t("sidebar.inspector.close")}
        title={t("sidebar.inspector.close")}
        onClick={close}
        data-testid={INSPECTOR_TEST_IDS.close}
      >
        <X aria-hidden="true" size={16} />
      </button>
    </div>
  );

  const panel = (
    <>
      <InspectorTabs tabs={tabs} activeTab={activeTab} onActivate={activateTab} />
      {tabs.map((key) => (
        <div
          key={key}
          role="tabpanel"
          id={inspectorPanelId(key)}
          aria-labelledby={inspectorTabId(key)}
          tabIndex={0}
          hidden={key !== activeTab}
          className={styles.body}
          data-testid={INSPECTOR_TEST_IDS.panel(key)}
        >
          {/* Only the active area is mounted: an inactive one holds no data
              hook, so a tab switch is the only thing that can trigger its
              fetch (spec §5.1 "one activation, one fetch"). The container
              exists for every tab anyway, because `aria-controls` must
              resolve — a reference into nothing is a 4.1.2 defect (§7). */}
          {key === activeTab && key === "version" && (
            <VersionTab
              kind={kind}
              entityId={entityId}
              currentVersion={currentVersion}
              onSwitch={handleSwitchVersion}
              onCompare={handleCompareVersions}
            />
          )}
          {key === activeTab && key === "diff" && (
            <DiffTab
              kind={kind}
              entityId={entityId}
              leftVersion={diffLeft}
              rightVersion={diffRight}
            />
          )}
          {key === activeTab && key === "links" && (
            <LinksTab kind={kind} entityId={entityId} onShowInSpine={onShowInSpine} />
          )}
          {key === activeTab && key === "comments" && artifactPk !== null && (
            <CommentsTab kind={kind} artifactPk={artifactPk} />
          )}
        </div>
      ))}
    </>
  );

  const rail = (
    <InspectorRail
      tabs={tabs}
      counts={counts}
      activeTab={activeTab}
      onOpen={openOnTab}
    />
  );

  return (
    <>
      {layout.form === "panel" && (
        <div
          className={`btn-icon ${styles.splitter}`}
          role="separator"
          aria-orientation="vertical"
          aria-label={t("sidebar.inspector.resize")}
          aria-valuenow={layout.widthPx}
          aria-valuemin={INSPECTOR_WIDTHS.min}
          aria-valuemax={INSPECTOR_WIDTHS.max}
          aria-valuetext={t("sidebar.inspector.widthValue", {
            width: layout.widthPx,
            defaultValue: "{{width}} pixels",
          })}
          aria-controls={INSPECTOR_SURFACE_ID}
          tabIndex={0}
          onMouseDown={onSplitterPointerDown}
          onKeyDown={onSplitterKeyDown}
          data-testid={INSPECTOR_TEST_IDS.splitter}
        />
      )}
      {layout.form === "rail" && (
        <>
          <h2 id={INSPECTOR_HEADING_ID} className="visually-hidden">
            {t("sidebar.inspector.title")}
          </h2>
          {rail}
        </>
      )}
      {layout.form === "panel" && (
        <>
          {header}
          {panel}
        </>
      )}
      {(layout.form === "sheet" || layout.form === "fullscreen") && (
        <InspectorSheet mode={layout.form} onClose={close}>
          {header}
          {panel}
        </InspectorSheet>
      )}
    </>
  );
}
