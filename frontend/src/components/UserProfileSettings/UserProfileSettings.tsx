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
import { ProfileSection } from "./ProfileSection";
import { useWorkspace } from "../../context/WorkspaceContext";
import { OPTIONAL_FEATURES, type OptionalArtifactFeature } from "../../api/preferences";
import { useState, useCallback } from "react";
import { PageHeader } from "../shared/PageHeader";

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

  const labelStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
    padding: "var(--space-2) 0",
    cursor: "pointer",
    fontSize: "var(--font-size-base)",
  };

  return (
    <div data-testid="user-profile-settings" style={{ maxWidth: "640px" }}>
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

      {activeWorkspace && (
        <section style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-5)",
          marginTop: "var(--space-5)",
          boxShadow: "var(--shadow-card)",
        }} data-testid="visibility-section">
          <h3 style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            color: "var(--color-text)",
            margin: "0 0 var(--space-4) 0",
          }}>{t("settings.visibility", "Sichtbarkeit")} (Workspace: {activeWorkspace.name})</h3>
          <p
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              marginBottom: "var(--space-3)",
            }}
          >
            {t(
              "settings.visibilityHint",
              "Blendet einzelne optionale Artefakttypen in der Navigation und den Editoren ein oder aus. Overrides wirken nur für dich in diesem Workspace und überschreiben die Preset-Vorgabe."
            )}
          </p>

          {saveError && (
            <div
              role="alert"
              style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)", fontSize: "var(--font-size-sm)" }}
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
                style={{
                  ...labelStyle,
                  justifyContent: "space-between",
                  padding: "var(--space-2) 0",
                  borderTop: "1px solid var(--color-border)",
                }}
                data-testid={`visibility-row-${feature}`}
              >
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--space-3)",
                    cursor: isPending ? "wait" : "pointer",
                    flex: 1,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={effective}
                    disabled={isPending}
                    onChange={(e) => void handleFeatureToggle(feature, e.target.checked)}
                    data-testid={`visibility-checkbox-${feature}`}
                  />
                  <span>
                    <span style={{ fontWeight: 500 }}>{VISIBILITY_LABELS[feature]}</span>
                    <span
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-muted)",
                        marginLeft: "var(--space-2)",
                      }}
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
                  style={{
                    background: "transparent",
                    color: "var(--color-text-muted)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "var(--space-1) var(--space-3)",
                    fontSize: "var(--font-size-sm)",
                    cursor: isPending || !overridden ? "not-allowed" : "pointer",
                    opacity: overridden ? 1 : 0.5,
                  }}
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
