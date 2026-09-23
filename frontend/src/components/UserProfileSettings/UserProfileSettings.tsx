/**
 * ARCH-L1-001 ReactFrontend — UserProfileSettings (COMP-RF-006).
 *
 * leaf_id: COMP-RF-006
 * req_id:  REQ-L2-RF-027 (User-Profile Dialog für PAT-Verwaltung),
 *          REQ-L3-RF006-001 (Token-Liste und UI-Controls)
 *
 * Standalone, workspace-independent page for managing the authenticated
 * user's Personal Access Tokens. Deliberately outside WorkspaceSettings —
 * tokens are bound to the user, not to a workspace, and must be generatable
 * without first selecting/activating a workspace.
 */

import { useTranslation } from "react-i18next";
import { ApiKeysSection } from "./ApiKeysSection";
import { MemorySection } from "./MemorySection";
import { NotificationsSection } from "./NotificationsSection";
import { ProfileSection } from "./ProfileSection";
import { useWorkspace } from "../../context/WorkspaceContext";
import { OPTIONAL_FEATURES, type OptionalArtifactFeature } from "../../api/preferences";
import { useState, useCallback } from "react";
import { PageHeader } from "../shared/PageHeader";
import styles from "./UserProfileSettings.module.css";

const VISIBILITY_LABELS: Record<OptionalArtifactFeature, string> = {
  adr: "ADR (Architecture Decision Records)",
  risk: "Risks",
  issue: "Issues",
  diagrams: "Diagrams",
  icds: "ICDs (Interface Control Documents)",
  metrics: "Metrics",
};

export default function UserProfileSettings(): JSX.Element {
  const { t } = useTranslation();
  const {
    activeWorkspace,
    isFeatureVisible,
    setFeatureVisible,
    resetFeatureOverride,
    isFeatureOverridden,
  } = useWorkspace();

  const [pendingFeature, setPendingFeature] = useState<OptionalArtifactFeature | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleFeatureToggle = useCallback(
    async (feature: OptionalArtifactFeature, value: boolean): Promise<void> => {
      setSaveError(null);
      setPendingFeature(feature);
      try {
        await setFeatureVisible(feature, value);
      } catch (err: unknown) {
        setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
      } finally {
        setPendingFeature(null);
      }
    },
    [setFeatureVisible]
  );

  const handleResetFeature = useCallback(
    async (feature: OptionalArtifactFeature): Promise<void> => {
      setSaveError(null);
      setPendingFeature(feature);
      try {
        await resetFeatureOverride(feature);
      } catch (err: unknown) {
        setSaveError((err as { error?: { message?: string } })?.error?.message ?? String(err));
      } finally {
        setPendingFeature(null);
      }
    },
    [resetFeatureOverride]
  );

  return (
    <div data-testid="user-profile-settings" className={styles.container}>
      <PageHeader
        title={t("nav.profile")}
        summary={t(
          "profile.pageSummary",
          "Persönliche Einstellungen: Profil, Personal Access Tokens und Sichtbarkeit optionaler Artefakttypen.",
        )}
      />

      <ProfileSection />

      <ApiKeysSection />

      <MemorySection />

      {/* User-global section: keep it contiguous with the three above and
          before the workspace-scoped visibility block below. */}
      <NotificationsSection />

      {activeWorkspace && (
        <section className={styles.visibilitySection} data-testid="visibility-section">
          <h3 className={styles.visibilityHeading}>{t("settings.visibility", "Sichtbarkeit")} (Workspace: {activeWorkspace.name})</h3>
          <p
            className={styles.visibilityHint}
          >
            {t(
              "settings.visibilityHint",
              "Blendet einzelne optionale Artefakttypen in der Navigation und den Editoren ein oder aus. Overrides wirken nur für dich in diesem Workspace und überschreiben die Preset-Vorgabe."
            )}
          </p>

          {saveError && (
            <div
              role="alert"
              className={styles.saveError}
            >
              {saveError}
            </div>
          )}

          {OPTIONAL_FEATURES.map((feature) => {
            const effective = isFeatureVisible(feature);
            const overridden = isFeatureOverridden(feature);
            const isPending = pendingFeature === feature;
            return (
              <div
                key={feature}
                className={styles.visibilityRow}
                data-testid={`visibility-row-${feature}`}
              >
                <label
                  className={
                    styles.featureLabel +
                    (isPending ? " " + styles.featureLabelPending : "")
                  }
                >
                  <input
                    type="checkbox"
                    checked={effective}
                    disabled={isPending}
                    onChange={(e) => void handleFeatureToggle(feature, e.target.checked)}
                    data-testid={`visibility-checkbox-${feature}`}
                  />
                  <span>
                    <span className={styles.featureName}>{VISIBILITY_LABELS[feature]}</span>
                    <span
                      className={styles.featureSource}
                    >
                      {overridden
                        ? t("settings.visibilityOverridden", "(überschrieben)")
                        : t("settings.visibilityFromPreset", "(aus Preset)")}
                    </span>
                  </span>
                </label>
                {/*
                  BUG-16 fix: always render the reset control, disabled when
                  there is nothing to reset. Previously this was gated on
                  `overridden` alone, so a successful reset (which clears
                  `overridden`) unmounted the button entirely instead of
                  disabling it — the E2E assertion `toBeDisabled()` could
                  never be satisfied because the element left the DOM.
                */}
                <button
                  type="button"
                  data-testid={`visibility-reset-${feature}`}
                  onClick={() => void handleResetFeature(feature)}
                  disabled={isPending || !overridden}
                  className={
                    styles.resetButton +
                    (overridden ? "" : " " + styles.resetButtonInactive)
                  }
                >
                  {t("settings.visibilityReset", "Auf Preset zurücksetzen")}
                </button>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
