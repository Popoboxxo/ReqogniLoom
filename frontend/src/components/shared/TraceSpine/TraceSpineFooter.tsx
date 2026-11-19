/**
 * TraceSpineFooter — horizontal derivation-chain footer (plan §3.1/§3.3/§3.4).
 *
 * Schnitt 2a: the chain is mounted as a sibling of `<SplitView>` spanning the
 * full content width. `useDerivationChain` lives HERE (not in the 8 hosts), so
 * the `impact()`/`resolve` RPCs only fire while a footer with a selection is
 * actually mounted. Hosts pass only an artifact descriptor plus callbacks.
 *
 * Rendering rules:
 *  - length <= 4            -> every station, no `[+N]`
 *  - length >= 5            -> first 3 + the active station + `[+N weitere]`;
 *                              the active station is NEVER collapsed away and
 *                              carries `aria-current="step"`/`data-active`
 *  - expanded               -> all stations, horizontal overflow
 *  - length === 1           -> one-line placeholder ("artifact without chain")
 *  - no artifact            -> render nothing (0 px reserved)
 *
 * A station chip is disabled (and opens no popover) whenever none of its
 * artifacts is openable — `useDerivationChain.isOpenable` is false for
 * resolved:false, in-flight and failed resolves (all three collapse into one
 * boolean); an optional host `isOpenable` narrows it further. No dead links.
 *
 * The station popover is a NON-modal `role="dialog"`, ESC closes it and focus
 * returns to the chip that opened it (APG dialog pattern, non-modal variant).
 * The binding WCAG verdict stays with `accessibility-specialist`; this is the
 * component-level baseline only.
 *
 * On a phone (< --bp-md, plan §3.5) the footer becomes a NON-modal bottom
 * sheet: a collapsed bar (the always-visible >=44px tap target) expands to the
 * full chain in a sheet with its own close control. It shares the single
 * "expanded sheet" slot with the artifact inspector through
 * `mobileSheetCoordinator` — opening one collapses the other. Both surfaces
 * stay `role="region"` (no scrim / focus trap); the covered detail area is
 * `inert` instead. The slot is never claimed on desktop, where footer and
 * inspector sit side by side.
 *
 * All colours/geometry come from `styles/tokens.css`; every button carries a
 * `btn-*` design-system chrome class (design-system-ratchet) and geometry comes
 * from the `--btn-h-*`/`--radius-btn` scale (button-geometry ratchet).
 */

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useInertBehindSheet } from "../ArtifactInspector/useInertBehindSheet";
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { TriangleAlert } from "lucide-react";

import { ArtifactId } from "../ArtifactId";
import { LevelBadge } from "../LevelBadge";
import { useViewportWidth } from "../../../hooks/useViewportWidth";
import { BREAKPOINTS } from "../../../hooks/useBreakpoint";
import {
  getExpandedMobileSheet,
  releaseMobileSheet,
  requestMobileSheet,
  subscribeToMobileSheet,
} from "../mobileSheetCoordinator";
import type { ArchitectureElement, UUID } from "../../../types";
import {
  ARTIFACT_TYPE_ARCHITECTURE,
  ARTIFACT_TYPE_NEED,
  ARTIFACT_TYPE_REQUIREMENT,
  ARTIFACT_TYPE_GOAL,
  ARTIFACT_TYPE_ADR,
  ARTIFACT_TYPE_RISK,
  ARTIFACT_TYPE_ISSUE,
  ARTIFACT_TYPE_TESTCASE,
  useDerivationChain,
  type ChainArtifact,
  type ChainStation,
  type ResolvedChainEntry,
} from "./useDerivationChain";
import styles from "./TraceSpineFooter.module.css";

/** Minimal descriptor a host hands over; everything else is derived internally. */
export interface TraceFooterArtifact {
  /** Trace-graph Artifact id (preferred). Falls back to `id`. */
  artifactId?: UUID | null;
  /** Domain-entity id (fallback artifact key for hosts without an artifact id). */
  id?: UUID | null;
  /** Artifact type token consumed by `useDerivationChain` (e.g. "Requirement"). */
  artifactType: string;
  /** Architecture tree depth; null/omitted for every other type. */
  level?: number | null;
}

export interface TraceSpineFooterProps {
  /**
   * The currently opened artifact. `null`/`undefined` means "no selection":
   * the component renders nothing and fires no RPC.
   */
  artifact: TraceFooterArtifact | null | undefined;
  /**
   * Navigate to a linked artifact. The footer never routes itself; it hands
   * over the chain artifact plus the resolved `(entityType, entityId)` entry
   * so a host can build its detail route without owning the resolve call.
   */
  onOpenArtifact?: (artifact: ChainArtifact, entry: ResolvedChainEntry | null) => void;
  /**
   * Optional host-side routing check (e.g. ArchitectureEditors' local map).
   * ANDed with the hook's own `isOpenable` — a false here always disables.
   */
  isOpenable?: (artifact: ChainArtifact) => boolean;
  /** Already-loaded architecture elements, used to bucket stations by depth. */
  architectureElements?: ArchitectureElement[];
  testId?: string;
}

/** ch. 5 "Zeichensprache" — same glyph semantics as the vertical rail. */
function stationGlyph(station: ChainStation): string {
  if (station.isCurrent) return "●";
  if (station.artifacts.length > 0) return "○";
  return "◍";
}

export function TraceSpineFooter({
  artifact,
  onOpenArtifact,
  isOpenable,
  architectureElements,
  testId = "trace-footer",
}: TraceSpineFooterProps): JSX.Element | null {
  const { t } = useTranslation();
  const viewportWidth = useViewportWidth();
  const isMobile = viewportWidth < BREAKPOINTS.md;
  // Shared single-expanded-sheet owner (plan §3.5). A stable string/null
  // snapshot keeps `useSyncExternalStore` from re-rendering on every notify.
  const expandedSheet = useSyncExternalStore(
    subscribeToMobileSheet,
    getExpandedMobileSheet,
    getExpandedMobileSheet,
  );

  const artifactId = artifact?.artifactId ?? artifact?.id ?? null;
  // The hook owns both RPCs. `enabled` keeps it dormant for an empty selection.
  const chain = useDerivationChain(
    artifactId,
    artifact?.artifactType ?? "",
    artifact?.artifactType === ARTIFACT_TYPE_ARCHITECTURE ? (artifact?.level ?? 0) : null,
    { architectureElements, enabled: !!artifact && !!artifactId },
  );

  const [expanded, setExpanded] = useState(false);
  const [openStationKey, setOpenStationKey] = useState<string | null>(null);
  // Mobile bottom-sheet state (plan §3.5). Distinct from `expanded`, which is
  // the desktop station-overflow disclosure and must keep its own semantics.
  const [mobileSheetOpen, setMobileSheetOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverCloseRef = useRef<HTMLButtonElement | null>(null);
  const mobileExpandRef = useRef<HTMLButtonElement | null>(null);
  const mobileCloseRef = useRef<HTMLButtonElement | null>(null);

  // WCAG 2.2 SC 2.4.11: the mobile sheet covers the host-owned SplitView detail
  // area. Find it by its stable E2E testid (same pattern as hosts' focusSpine)
  // so no host route needs a new prop; make it inert only while the sheet is open.
  const coveredRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    coveredRef.current = document.querySelector<HTMLElement>(
      '[data-testid="splitview-detail"]'
    );
  }, [mobileSheetOpen]);
  useInertBehindSheet(coveredRef, !!isMobile && mobileSheetOpen);

  // A different opened artifact invalidates every local expansion/popover state.
  useEffect(() => {
    setExpanded(false);
    setOpenStationKey(null);
    setMobileSheetOpen(false);
    releaseMobileSheet("trace-footer");
  }, [artifactId]);

  const openMobileSheet = (): void => {
    if (!isMobile) return;
    setOpenStationKey(null);
    setMobileSheetOpen(true);
    requestMobileSheet("trace-footer");
  };

  const closeMobileSheet = useCallback((): void => {
    setMobileSheetOpen(false);
    setOpenStationKey(null);
    releaseMobileSheet("trace-footer");
    mobileExpandRef.current?.focus();
  }, []);

  // Claim the single expanded-sheet slot only while the MOBILE sheet is open.
  useEffect(() => {
    if (!isMobile || !mobileSheetOpen) return;
    requestMobileSheet("trace-footer");
  }, [isMobile, mobileSheetOpen]);

  // Opening the inspector takes the slot -> collapse the footer sheet (§3.5).
  useEffect(() => {
    if (expandedSheet === "inspector" && mobileSheetOpen) {
      setMobileSheetOpen(false);
      setOpenStationKey(null);
      mobileExpandRef.current?.focus();
    }
  }, [expandedSheet, mobileSheetOpen]);

  // Leaving mobile or unmounting releases the slot (no stale owner across routes).
  useEffect(() => {
    if (!isMobile && mobileSheetOpen) setMobileSheetOpen(false);
  }, [isMobile, mobileSheetOpen]);
  useEffect(() => () => releaseMobileSheet("trace-footer"), []);

  // Move focus into the sheet on open, Escape closes it (and returns focus).
  useEffect(() => {
    if (mobileSheetOpen) mobileCloseRef.current?.focus();
  }, [mobileSheetOpen]);
  useEffect(() => {
    if (!mobileSheetOpen) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && !openStationKey) {
        event.stopPropagation();
        closeMobileSheet();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileSheetOpen, openStationKey, closeMobileSheet]);

  const effectiveIsOpenable = (item: ChainArtifact): boolean =>
    chain.isOpenable(item) && (isOpenable ? isOpenable(item) : true);

  const stationLabel = useCallback(
    (station: ChainStation): string => {
      switch (station.artifactType) {
        case ARTIFACT_TYPE_NEED:
          return t("nav.needs", "Stakeholder-Bedarf");
        case ARTIFACT_TYPE_REQUIREMENT:
          return t("nav.requirements", "Requirement");
        case ARTIFACT_TYPE_ARCHITECTURE:
          return t("nav.architecture", "Architektur");
        case ARTIFACT_TYPE_GOAL:
          return t("nav.goals", "Ziele");
        case ARTIFACT_TYPE_ADR:
          return t("nav.adrs", "ADRs");
        case ARTIFACT_TYPE_RISK:
          return t("nav.risks", "Risiken");
        case ARTIFACT_TYPE_ISSUE:
          return t("nav.issues", "Probleme");
        case ARTIFACT_TYPE_TESTCASE:
          return t("nav.testCases", "Testfälle");
        default:
          return station.artifactType;
      }
    },
    [t],
  );

  const stations = chain.stations;
  const activeIndex = stations.findIndex((station) => station.isCurrent);
  // The station-overflow disclosure is a desktop affordance only: on mobile the
  // bottom sheet shows the whole chain, so `more`/`collapse` never render there.
  const collapsed = stations.length >= 5 && !expanded && !isMobile;
  const currentStation = stations.find((station) => station.isCurrent);
  const currentStationLabel = currentStation ? stationLabel(currentStation) : "";

  /**
   * Plan §3.3 algorithm: <= 4 -> all; >= 5 -> first three + active station
   * (or four first ones when the active is already in the head) + `[+N]`.
   * Keeping the index alongside the station preserves the original chain order
   * for the retained active station at position 4 or 6.
   */
  const visibleStations = useMemo((): Array<{ station: ChainStation; index: number }> => {
    if (!collapsed || activeIndex < 0) {
      return stations.map((station, index) => ({ station, index }));
    }
    if (activeIndex < 3) {
      return stations.slice(0, 4).map((station, index) => ({ station, index }));
    }
    return [
      ...stations.slice(0, 3).map((station, index) => ({ station, index })),
      { station: stations[activeIndex], index: activeIndex },
    ];
  }, [stations, activeIndex, collapsed]);

  const hiddenCount = collapsed ? stations.length - 4 : 0;

  const activeStation = openStationKey
    ? stations.find((station) => station.key === openStationKey) ?? null
    : null;
  const popoverItems: ChainArtifact[] = activeStation
    ? [...activeStation.artifacts, ...activeStation.verifications]
    : [];

  const openPopover = (event: MouseEvent<HTMLButtonElement>, station: ChainStation): void => {
    triggerRef.current = event.currentTarget;
    setOpenStationKey(station.key);
  };

  const closePopover = useCallback((): void => {
    setOpenStationKey(null);
    triggerRef.current?.focus();
  }, []);

  // Move focus into the non-modal dialog on open, return it to the trigger on
  // ESC (the document listener also covers focus sitting on a popover item).
  useEffect(() => {
    if (openStationKey) popoverCloseRef.current?.focus();
  }, [openStationKey]);

  useEffect(() => {
    if (!openStationKey) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.stopPropagation();
        closePopover();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [openStationKey, closePopover]);

  // No selection: no element, no reserved height, no RPC (hook disabled above).
  if (!artifact || !artifactId) return null;

  const regionLabel = t("traceSpine.title", "Ableitungskette");

  return (
    <div
      className={`${styles.footer} ${mobileSheetOpen ? styles.mobileSheetOpen : ""}`}
      data-testid={testId}
      data-mobile-sheet-open={mobileSheetOpen ? "true" : undefined}
      role="region"
      aria-label={regionLabel}
    >
      {/* Mobile collapsed bar — the always-visible tap target that expands the
          sheet (plan §3.5). Hidden from --bp-md up by the stylesheet. */}
      <button
        ref={mobileExpandRef}
        type="button"
        className={`btn-ghost ${styles.mobileBar}`}
        data-testid={`${testId}-expand`}
        aria-expanded={mobileSheetOpen}
        // A one-station chain renders a placeholder, not the <ol>; a dangling
        // aria-controls would be a 4.1.2 defect.
        aria-controls={stations.length >= 2 ? `${testId}-station-list` : undefined}
        onClick={openMobileSheet}
      >
        <span className={styles.mobileBarLabel} aria-hidden="true">◆</span>
        <span className={styles.mobileBarText}>
          {regionLabel}
          {currentStationLabel ? ` · ${currentStationLabel}` : ""}
        </span>
        <span className={styles.mobileBarChevron} aria-hidden="true">
          {mobileSheetOpen ? "▲" : "▼"}
        </span>
      </button>

      {chain.isLoading && stations.length === 0 && (
        <span className={styles.hint} role="status" data-testid={`${testId}-loading`}>
          {t("traceSpine.loading", "Kette wird geladen...")}
        </span>
      )}
      {chain.error && (
        <span className={styles.error} role="alert" data-testid={`${testId}-error`}>
          {chain.error}
        </span>
      )}

      <div className={styles.chainWrap}>
      {stations.length === 0 ? (
        <span className={styles.hint} role="status" data-testid={`${testId}-placeholder`}>
          {t("traceSpine.loading", "Kette wird geladen...")}
        </span>
      ) : stations.length === 1 ? (
        // One station = the opened artifact with no chain. One line, no crash.
        <p className={styles.placeholder} data-testid={`${testId}-placeholder`}>
          <span className={styles.glyph} aria-hidden="true">
            {stationGlyph(stations[0])}
          </span>
          <span
            className={styles.placeholderStation}
            tabIndex={-1}
            data-testid={`${testId}-station`}
            data-station-key={stations[0].key}
            data-active={stations[0].isCurrent ? "true" : undefined}
            aria-current={stations[0].isCurrent ? "step" : undefined}
          >
            {stationLabel(stations[0])}
          </span>
          <span className={styles.placeholderHint}>
            {t(
              "traceSpine.footer.singleStation",
              "Dieses Artefakt ist noch mit keinem anderen verknüpft.",
            )}
          </span>
        </p>
      ) : (
        <ol id={`${testId}-station-list`} className={styles.chain} aria-label={regionLabel}>
          {visibleStations.map(({ station }, position) => {
            const artifacts = station.artifacts;
            const verifications = station.verifications;
            const canOpen =
              artifacts.some(effectiveIsOpenable) || verifications.some(effectiveIsOpenable);
            return (
              <li
                key={station.key}
                className={styles.stationItem}
                data-testid={`${testId}-station-item`}
                data-station-key={station.key}
                data-active={station.isCurrent ? "true" : undefined}
              >
                <span className={styles.glyph} aria-hidden="true">
                  {stationGlyph(station)}
                </span>
                <button
                  type="button"
                  className={`btn-ghost ${styles.stationTrigger}`}
                  data-testid={`${testId}-station`}
                  data-station-key={station.key}
                  data-active={station.isCurrent ? "true" : undefined}
                  aria-current={station.isCurrent ? "step" : undefined}
                  aria-haspopup="dialog"
                  disabled={!canOpen}
                  title={stationLabel(station)}
                  onClick={(event) => openPopover(event, station)}
                >
                  <span className={styles.stationName}>{stationLabel(station)}</span>
                  {station.artifactType === ARTIFACT_TYPE_ARCHITECTURE && (
                    <LevelBadge level={station.level} testId={`${testId}-level`} />
                  )}
                  {station.isCurrent && (
                    <span className={styles.here}>
                      <span aria-hidden="true">◀ </span>
                      {t("traceSpine.here", "hier")}
                    </span>
                  )}
                </button>

                <span className={styles.markers}>
                  {artifacts.length > 0 && (
                    <span
                      className={styles.countBadge}
                      data-testid={`${testId}-count`}
                      title={t("traceSpine.stationCount_other", {
                        count: artifacts.length,
                        defaultValue: "{{count}} Artefakte",
                      })}
                    >
                      {artifacts.length}
                    </span>
                  )}
                  {artifacts.length === 0 && !station.isCurrent && (
                    <span
                      className={styles.warning}
                      data-testid={`${testId}-no-coverage`}
                      role="img"
                      aria-label={t("traceSpine.noCoverage", "Keine Abdeckung")}
                    >
                      <TriangleAlert aria-hidden="true" size={14} />
                    </span>
                  )}
                  {(verifications.length > 0 ||
                    station.artifactType === ARTIFACT_TYPE_REQUIREMENT ||
                    station.artifactType === ARTIFACT_TYPE_ARCHITECTURE) && (
                    <span
                      className={
                        verifications.length > 0 ? styles.verification : styles.verificationEmpty
                      }
                      data-testid={`${testId}-verification`}
                    >
                      <span aria-hidden="true">V</span>
                      <span>·{verifications.length}</span>
                    </span>
                  )}
                </span>

                {position < visibleStations.length - 1 && (
                  <span className={styles.arrow} aria-hidden="true">
                    →
                  </span>
                )}
              </li>
            );
          })}

          {hiddenCount > 0 && (
            <li className={styles.moreItem}>
              <button
                type="button"
                className={`btn-ghost ${styles.more}`}
                data-testid={`${testId}-more`}
                aria-expanded={expanded}
                aria-controls={`${testId}-station-list`}
                onClick={() => setExpanded(true)}
              >
                {t("traceSpine.footer.more", {
                  count: hiddenCount,
                  defaultValue: "+{{count}} weitere",
                })}
              </button>
            </li>
          )}
          {expanded && stations.length >= 5 && !isMobile && (
            <li className={styles.moreItem}>
              <button
                type="button"
                className={`btn-ghost ${styles.more}`}
                data-testid={`${testId}-collapse`}
                aria-expanded={expanded}
                aria-controls={`${testId}-station-list`}
                onClick={() => setExpanded(false)}
              >
                <span aria-hidden="true">▲ </span>
                {t("traceSpine.footer.collapse", "Einklappen")}
              </button>
            </li>
          )}
        </ol>
      )}
      </div>

      {/* Mobile sheet close/back control — the single visible sheet dismissal
          while the footer sheet is expanded (plan §3.5). */}
      {mobileSheetOpen && (
        <button
          ref={mobileCloseRef}
          type="button"
          className={`btn-ghost ${styles.mobileSheetClose}`}
          data-testid={`${testId}-collapse`}
          onClick={closeMobileSheet}
        >
          <span aria-hidden="true">▼ </span>
          {t("traceSpine.close", "Schließen")}
        </button>
      )}

      {activeStation && (
        <div
          className={styles.popover}
          role="dialog"
          aria-label={t("traceSpine.footer.popoverTitle", "Verknüpfte Artefakte")}
          data-testid="trace-station-popover"
        >
          <div className={styles.popoverHead}>
            <strong className={styles.popoverTitle}>{stationLabel(activeStation)}</strong>
            <button
              ref={popoverCloseRef}
              type="button"
              className="btn-ghost"
              data-testid={`${testId}-popover-close`}
              onClick={closePopover}
            >
              {t("traceSpine.close", "Schließen")}
            </button>
          </div>
          {popoverItems.length === 0 ? (
            <p className={styles.hint}>{t("traceSpine.empty", "Noch keine Verknüpfungen.")}</p>
          ) : (
            <ul className={styles.popoverList}>
              {popoverItems.map((item) => (
                <li key={item.id} className={styles.popoverItem}>
                  <button
                    type="button"
                    className={`btn-ghost ${styles.popoverItemButton}`}
                    data-testid={`${testId}-popover-item`}
                    disabled={!effectiveIsOpenable(item)}
                    onClick={() => onOpenArtifact?.(item, chain.resolveEntry(item))}
                  >
                    <ArtifactId
                      readOnly
                      value={item.uid}
                      fallback={item.id.slice(0, 8)}
                      testId={`${testId}-popover-item-id`}
                    />
                    <span className={styles.popoverItemTitle}>{item.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
