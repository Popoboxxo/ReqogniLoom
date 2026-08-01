/**
 * ARCH-L1-001 ReactFrontend — <TraceSpine> (UI concept ch. 5, ch. 12.10).
 *
 * The signature element: a narrow vertical rail at the left edge of the
 * detail area showing the derivation chain around the opened artifact and
 * marking where it sits — and, more importantly, where nothing is.
 *
 * Scope of this first version (ch. 17 step 6, "Grundgerüst"):
 *
 *  - Stations are resolved from the real chain, N of them, no fixed L0–L4
 *    ladder (ch. 5.1). Architecture contributes one station per real tree
 *    depth.
 *  - Verification is a badge **per station**, never its own station.
 *  - Branching is shown as a plain count badge; picking one of several paths
 *    is deliberately not offered yet.
 *  - Clicking a station opens its artifacts in a panel next to the spine;
 *    clicking the verification badge opens the test cases separately —
 *    verification is its own question, not another derivation level.
 *
 * Below --bp-lg (1024px) the rail turns horizontal underneath the artifact
 * header and scrolls sideways rather than wrapping, so the order of the
 * chain stays readable (ch. 5 "Verhalten").
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArtifactId } from "../ArtifactId";
import { LevelBadge } from "../LevelBadge";
import {
  ARTIFACT_TYPE_ARCHITECTURE,
  ARTIFACT_TYPE_NEED,
  ARTIFACT_TYPE_REQUIREMENT,
  type ChainArtifact,
  type ChainStation,
} from "./useDerivationChain";
import styles from "./TraceSpine.module.css";

export interface TraceSpineProps {
  stations: ChainStation[];
  isLoading?: boolean;
  error?: string | null;
  /** Navigate to a linked artifact; the spine itself never routes. */
  onOpenArtifact?: (artifact: ChainArtifact) => void;
  /**
   * Whether the host can actually route to this artifact. The trace graph is
   * keyed by Artifact id while the detail routes take domain-entity ids, and
   * no endpoint resolves one to the other for every type — so a host that
   * cannot map an entry says so here instead of offering a dead link.
   */
  isOpenable?: (artifact: ChainArtifact) => boolean;
  testId?: string;
}

/** ch. 5 "Zeichensprache". */
function stationGlyph(station: ChainStation): string {
  if (station.isCurrent) return "●";
  if (station.artifacts.length > 0) return "○";
  return "◍";
}

function directionGlyph(station: ChainStation): string | null {
  if (station.isCurrent) return null;
  return station.direction === "origin" ? "↑" : "↓";
}

export function TraceSpine({
  stations,
  isLoading = false,
  error = null,
  onOpenArtifact,
  isOpenable,
  testId = "trace-spine",
}: TraceSpineProps): JSX.Element {
  const { t } = useTranslation();
  const [openPanel, setOpenPanel] = useState<
    { stationKey: string; kind: "links" | "verification" } | null
  >(null);

  const stationLabel = useMemo(
    () =>
      (station: ChainStation): string => {
        switch (station.artifactType) {
          case ARTIFACT_TYPE_NEED:
            return t("nav.needs", "Stakeholder-Bedarf");
          case ARTIFACT_TYPE_REQUIREMENT:
            return t("nav.requirements", "Requirement");
          case ARTIFACT_TYPE_ARCHITECTURE:
            return t("nav.architecture", "Architektur");
          default:
            return station.artifactType;
        }
      },
    [t],
  );

  const activeStation = openPanel
    ? stations.find((s) => s.key === openPanel.stationKey) ?? null
    : null;
  const panelItems: ChainArtifact[] = activeStation
    ? openPanel?.kind === "verification"
      ? activeStation.verifications
      : activeStation.artifacts
    : [];

  return (
    <div className={styles.wrapper} data-testid={testId}>
      <nav className={styles.rail} aria-label={t("traceSpine.title", "Ableitungskette")}>
        {isLoading && (
          <p className={styles.hint} role="status" data-testid={`${testId}-loading`}>
            {t("traceSpine.loading", "Kette wird geladen...")}
          </p>
        )}
        {error && (
          <p className={styles.error} role="alert" data-testid={`${testId}-error`}>
            {error}
          </p>
        )}

        <ol className={styles.stations}>
          {stations.map((station) => {
            const verificationCount = station.verifications.length;
            const linkCount = station.artifacts.length;
            return (
              <li
                key={station.key}
                className={styles.station}
                data-testid={`${testId}-station`}
                data-station-key={station.key}
                data-current={station.isCurrent || undefined}
              >
                <span className={styles.glyph} aria-hidden="true">
                  {stationGlyph(station)}
                </span>

                <button
                  type="button"
                  className={styles.stationButton}
                  data-testid={`${testId}-station-button`}
                  disabled={linkCount === 0}
                  aria-expanded={
                    openPanel?.stationKey === station.key && openPanel.kind === "links"
                  }
                  title={
                    linkCount === 0
                      ? t("traceSpine.noCoverage", "Keine Abdeckung")
                      : // Hover preview of the linked titles (ch. 5 "Verhalten").
                        station.artifacts.map((a) => a.title).join("\n")
                  }
                  onClick={() =>
                    setOpenPanel((prev) =>
                      prev?.stationKey === station.key && prev.kind === "links"
                        ? null
                        : { stationKey: station.key, kind: "links" },
                    )
                  }
                >
                  <span className={styles.stationLabel}>{stationLabel(station)}</span>
                  {station.artifactType === ARTIFACT_TYPE_ARCHITECTURE && (
                    <LevelBadge level={station.level} testId={`${testId}-level`} />
                  )}
                  {station.isCurrent && (
                    <span className={styles.here} data-testid={`${testId}-here`}>
                      ◀ {t("traceSpine.here", "hier")}
                    </span>
                  )}
                </button>

                <span className={styles.markers}>
                  {linkCount > 0 && (
                    // Branching is a count, not a path picker (see file docs).
                    <span
                      className={styles.countBadge}
                      data-testid={`${testId}-count`}
                      title={t("traceSpine.stationCount", {
                        count: linkCount,
                        defaultValue: `${linkCount}`,
                      })}
                    >
                      {linkCount}
                      <span aria-hidden="true">{directionGlyph(station)}</span>
                    </span>
                  )}

                  {/* ch. 5: a station without any link to THIS artifact is the
                      most important line on the screen. */}
                  {linkCount === 0 && !station.isCurrent && (
                    <span
                      className={styles.warning}
                      data-testid={`${testId}-no-coverage`}
                      title={t("traceSpine.noCoverage", "Keine Abdeckung")}
                    >
                      ⚠
                    </span>
                  )}

                  {/* Verification badge — only meaningful on requirement and
                      architecture stations (ch. 5.2). */}
                  {(station.artifactType === ARTIFACT_TYPE_REQUIREMENT ||
                    station.artifactType === ARTIFACT_TYPE_ARCHITECTURE) && (
                    <button
                      type="button"
                      className={
                        verificationCount > 0 ? styles.verification : styles.verificationEmpty
                      }
                      data-testid={`${testId}-verification`}
                      disabled={verificationCount === 0}
                      aria-expanded={
                        openPanel?.stationKey === station.key &&
                        openPanel.kind === "verification"
                      }
                      title={
                        verificationCount > 0
                          ? t("traceSpine.verificationOpen", "Verknuepfte Testfaelle anzeigen")
                          : t("traceSpine.noCoverage", "Keine Abdeckung")
                      }
                      onClick={() =>
                        setOpenPanel((prev) =>
                          prev?.stationKey === station.key &&
                          prev.kind === "verification"
                            ? null
                            : { stationKey: station.key, kind: "verification" },
                        )
                      }
                    >
                      <span aria-hidden="true">V</span>
                      <span>·{verificationCount}</span>
                    </button>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      {activeStation && (
        // ch. 5 "Verhalten": opens NEXT to the spine — the page is not left.
        <aside
          className={styles.panel}
          data-testid={`${testId}-panel`}
          aria-label={stationLabel(activeStation)}
        >
          <div className={styles.panelHead}>
            <strong className={styles.panelTitle}>
              {openPanel?.kind === "verification"
                ? t("traceSpine.verificationOpen", "Testfaelle")
                : stationLabel(activeStation)}
            </strong>
            <button
              type="button"
              className="btn-ghost"
              data-testid={`${testId}-panel-close`}
              onClick={() => setOpenPanel(null)}
            >
              {t("traceSpine.close", "Schliessen")}
            </button>
          </div>
          {panelItems.length === 0 ? (
            <p className={styles.hint}>{t("traceSpine.empty", "Noch keine Verknuepfungen")}</p>
          ) : (
            <ul className={styles.panelList}>
              {panelItems.map((artifact) => (
                <li key={artifact.id} className={styles.panelItem}>
                  <button
                    type="button"
                    className={styles.panelItemButton}
                    data-testid={`${testId}-panel-item`}
                    disabled={isOpenable ? !isOpenable(artifact) : !onOpenArtifact}
                    onClick={() => onOpenArtifact?.(artifact)}
                  >
                    <ArtifactId
                      readOnly
                      value={artifact.uid}
                      fallback={artifact.id.slice(0, 8)}
                      testId={`${testId}-panel-item-id`}
                    />
                    <span className={styles.panelItemTitle}>{artifact.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      )}
    </div>
  );
}
