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
 * All colours/geometry come from `styles/tokens.css`; every button carries a
 * `btn-*` design-system chrome class (design-system-ratchet) and geometry comes
 * from the `--btn-h-*`/`--radius-btn` scale (button-geometry ratchet).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { TriangleAlert } from "lucide-react";

import { ArtifactId } from "../ArtifactId";
import { LevelBadge } from "../LevelBadge";
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
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverCloseRef = useRef<HTMLButtonElement | null>(null);

  // A different opened artifact invalidates the local expansion/popover state.
  useEffect(() => {
    setExpanded(false);
    setOpenStationKey(null);
  }, [artifactId]);

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
  const collapsed = stations.length >= 5 && !expanded;

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
    <div className={styles.footer} data-testid={testId} role="region" aria-label={regionLabel}>
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
          {expanded && stations.length >= 5 && (
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
