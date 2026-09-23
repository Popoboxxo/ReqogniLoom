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
import styles from "./ProfileSection.module.css";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

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
    <section className={styles.section} data-testid="profile-section">
      <h3 className={styles.heading}>{t("profile.nameHeading", "Name")}</h3>

      {error && (
        <div
          role="alert"
          data-testid="profile-error"
          className={styles.error}
        >
          {error}
        </div>
      )}

      {saved && !isEditing && (
        <div
          data-testid="profile-saved"
          className={styles.saved}
        >
          {t("profile.saved", "Profil gespeichert")}
        </div>
      )}

      {!isEditing ? (
        <div className={styles.readRow}>
          <span data-testid="profile-display-name" className={styles.name}>
            {displayName || t("profile.noName", "Kein Name hinterlegt")}
          </span>
          <button
            type="button"
            data-testid="profile-edit-button"
            onClick={startEdit}
            className={styles.secondaryButton}
          >
            {t("profile.edit", "Bearbeiten")}
          </button>
        </div>
      ) : (
        <div className={styles.fieldStack}>
          <div>
            <label htmlFor="profile-first-name" className={styles.label}>
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
              className={styles.input}
            />
          </div>
          <div>
            <label htmlFor="profile-last-name" className={styles.label}>
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
              className={styles.input}
            />
          </div>
          <div className={styles.actions}>
            <button
              type="button"
              data-testid="profile-save-button"
              onClick={() => void handleSave()}
              disabled={isSaving}
              className={styles.primaryButton}
            >
              {isSaving ? t("profile.saving", "Speichern…") : t("profile.save", "Speichern")}
            </button>
            <button
              type="button"
              data-testid="profile-cancel-button"
              onClick={cancelEdit}
              disabled={isSaving}
              className={styles.secondaryButton}
            >
              {t("profile.cancel", "Abbrechen")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
