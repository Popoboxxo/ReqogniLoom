/**
 * ARCH-L1-001 ReactFrontend — ProfileSection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings)
 * req_id:  REQ-006 (editable user profile — first_name / last_name)
 *
 * Displays the authenticated user's name and lets them edit it:
 *   - read mode: shows current first/last name (or a placeholder),
 *   - edit mode: input fields + Save/Cancel,
 *   - Save → PATCH /api/v1/auth/me/ via AuthContext.updateProfile.
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../context/AuthContext";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

const sectionStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const inputStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-base)",
  boxSizing: "border-box",
  width: "100%",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
  marginBottom: "var(--space-1)",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "var(--color-on-primary)",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

const secondaryButtonStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

export function ProfileSection(): JSX.Element {
  const { t } = useTranslation();
  const { user, updateProfile } = useAuth();

  const [isEditing, setIsEditing] = useState(false);
  const [firstName, setFirstName] = useState(user?.first_name ?? "");
  const [lastName, setLastName] = useState(user?.last_name ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const startEdit = useCallback(() => {
    setFirstName(user?.first_name ?? "");
    setLastName(user?.last_name ?? "");
    setError(null);
    setSaved(false);
    setIsEditing(true);
  }, [user]);

  const cancelEdit = useCallback(() => {
    setError(null);
    setIsEditing(false);
  }, []);

  const handleSave = useCallback(async (): Promise<void> => {
    setError(null);
    setSaved(false);
    setIsSaving(true);
    try {
      await updateProfile({ first_name: firstName.trim(), last_name: lastName.trim() });
      setIsEditing(false);
      setSaved(true);
    } catch (err: unknown) {
      setError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }, [firstName, lastName, updateProfile]);

  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(" ");

  return (
    <section style={sectionStyle} data-testid="profile-section">
      <h3 style={headingStyle}>{t("profile.nameHeading", "Name")}</h3>

      {error && (
        <div
          data-testid="profile-error"
          style={{
            color: "var(--color-danger)",
            marginBottom: "var(--space-3)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {error}
        </div>
      )}

      {saved && !isEditing && (
        <div
          data-testid="profile-saved"
          style={{
            color: "var(--color-success)",
            marginBottom: "var(--space-3)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {t("profile.saved", "Profil gespeichert")}
        </div>
      )}

      {!isEditing ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span data-testid="profile-display-name" style={{ color: "var(--color-text)" }}>
            {displayName || t("profile.noName", "Kein Name hinterlegt")}
          </span>
          <button
            type="button"
            data-testid="profile-edit-button"
            onClick={startEdit}
            style={secondaryButtonStyle}
          >
            {t("profile.edit", "Bearbeiten")}
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          <div>
            <label htmlFor="profile-first-name" style={labelStyle}>
              {t("profile.firstName", "Vorname")}
            </label>
            <input
              id="profile-first-name"
              data-testid="profile-first-name-input"
              type="text"
              value={firstName}
              maxLength={150}
              disabled={isSaving}
              onChange={(e) => setFirstName(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div>
            <label htmlFor="profile-last-name" style={labelStyle}>
              {t("profile.lastName", "Nachname")}
            </label>
            <input
              id="profile-last-name"
              data-testid="profile-last-name-input"
              type="text"
              value={lastName}
              maxLength={150}
              disabled={isSaving}
              onChange={(e) => setLastName(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div style={{ display: "flex", gap: "var(--space-3)" }}>
            <button
              type="button"
              data-testid="profile-save-button"
              onClick={() => void handleSave()}
              disabled={isSaving}
              style={primaryButtonStyle}
            >
              {isSaving ? t("profile.saving", "Speichern…") : t("profile.save", "Speichern")}
            </button>
            <button
              type="button"
              data-testid="profile-cancel-button"
              onClick={cancelEdit}
              disabled={isSaving}
              style={secondaryButtonStyle}
            >
              {t("profile.cancel", "Abbrechen")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
