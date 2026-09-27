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

import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../context/AuthContext";
import { SAVE_SHORTCUT_ARIA, useSaveShortcut } from "../../hooks/useSaveShortcut";
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
  // Issue #1087 (behaviour rule 2): same-tick guard for the same reason as in
  // `shared/ArtifactForm` — the `isSaving` state is not yet updated when a
  // second Save click or `Ctrl+S` arrives in the same event-loop turn.
  const savingRef = useRef(false);

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
    if (savingRef.current) return;
    savingRef.current = true;
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
      savingRef.current = false;
      setIsSaving(false);
    }
  }, [firstName, lastName, updateProfile]);

  /**
   * Issue #1087: `Ctrl`/`Cmd`+`S` while the name is being edited.
   *
   * Covered because the saving mechanism is the same shape as the artifact
   * form's — an async PATCH behind one primary button with an in-flight state —
   * so the same hook and the same three rules apply unchanged. `enabled` is
   * `isEditing`: in read mode there is nothing to save, and swallowing the
   * shortcut there would only deny the browser its own action.
   */
  useSaveShortcut({ onSave: handleSave, enabled: isEditing, isSaving });

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
              // Issue #1087: the shortcut this button also answers to. See the
              // ArtifactForm save button for why it is announced here rather
              // than in a shortcuts overview.
              aria-keyshortcuts={SAVE_SHORTCUT_ARIA}
              title={t("profile.saveShortcutHint", "Speichern (Strg/Cmd+S)")}
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
