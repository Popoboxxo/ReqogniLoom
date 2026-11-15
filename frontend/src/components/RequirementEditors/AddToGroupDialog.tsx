/**
 * G2 (spec 2026-11-08 §4.5.3, plan 2026-11-15 G2.1) — "Zu Gruppe hinzufügen…".
 *
 * The per-row action on the requirement list used to have no counterpart at
 * all: a requirement could only be assigned to a group through the group
 * manager dialog, which means finding the requirement again by search inside
 * every group. This dialog starts from the requirement instead — it lists the
 * workspace's groups, one checkbox each.
 *
 * Read model: the dialog consumes the *existing* membership view
 * (`useRequirementGroups` → `GroupManagerGroup[]`), never a second source. A
 * requirement that already belongs to a group is shown **checked and
 * disabled** — unchecking would be a removal, which stays the group manager's
 * job (one interaction per dialog, no hidden second write path).
 *
 * Write model: ticking a checkbox calls `onAdd(groupId, requirementId)`
 * immediately. The caller (`RequirementEditors`) owns the hook, which re-reads
 * the groups after the write succeeded, so the folder counters and the
 * "in N Gruppen" row marker update without a route reload. The dialog closes
 * only through `onClose` — a rejected add keeps it open with a `role="alert"`
 * message so the user can pick another group instead of losing the context.
 *
 * The panel itself is the shared `<Dialog>` (focus trap, Escape, focus return
 * to the row trigger), exactly like G1's group manager dialog.
 */

import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../api/client";
import { Dialog } from "../shared/Dialog";
import type { GroupManagerGroup } from "./useRequirementGroups";
import styles from "./AddToGroupDialog.module.css";

export interface AddToGroupDialogProps {
  /** Requirement *entity* id — the id every membership write keys on. */
  requirementId: string;
  /** The requirement's title; the dialog title names it so it is unambiguous. */
  requirementTitle: string;
  /** Groups with their resolved membership (the hook's `managerGroups`). */
  groups: GroupManagerGroup[];
  /** Append the requirement to one group. Rejecting keeps the dialog open. */
  onAdd: (groupId: string, requirementId: string) => Promise<void>;
  onClose: () => void;
  /**
   * Optional: create a group without leaving the dialog. Feeds the empty
   * state — the plan asks the empty state to keep the existing create path
   * reachable instead of only pointing at another dialog. Same function the
   * group manager uses (`useRequirementGroups.createGroup`), no new endpoint.
   */
  onCreateGroup?: (title: string, description?: string) => Promise<void>;
  /** The group read is still in flight (the hook's `isLoading`). */
  isLoading?: boolean;
  /** The group read failed (the hook's `error`). */
  groupsError?: string | null;
}

export function AddToGroupDialog({
  requirementId,
  requirementTitle,
  groups,
  onAdd,
  onClose,
  onCreateGroup,
  isLoading = false,
  groupsError = null,
}: AddToGroupDialogProps): JSX.Element {
  const { t } = useTranslation();
  /** Group id whose add request is in flight — all controls stay locked meanwhile. */
  const [busyGroupId, setBusyGroupId] = useState<string | null>(null);
  /** Last failed add/create; rendered as `role="alert"` and never closes the dialog. */
  const [actionError, setActionError] = useState<string | null>(null);
  const [newGroupTitle, setNewGroupTitle] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");

  const isMember = (group: GroupManagerGroup): boolean =>
    group.members.some((member) => member.requirementId === requirementId);

  const handleToggle = async (group: GroupManagerGroup): Promise<void> => {
    // A membership is never removed here, and one write at a time keeps the
    // reload's answer unambiguous (the second checkbox would otherwise be
    // decided on stale membership data).
    if (isMember(group) || busyGroupId !== null) return;
    setBusyGroupId(group.id);
    setActionError(null);
    try {
      await onAdd(group.id, requirementId);
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ?? t("groups.addFailed"),
      );
    } finally {
      setBusyGroupId(null);
    }
  };

  const handleCreate = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!onCreateGroup || busyGroupId !== null) return;
    const title = newGroupTitle.trim();
    if (!title) return;
    setBusyGroupId("__create__");
    setActionError(null);
    try {
      await onCreateGroup(title, newGroupDescription.trim());
      setNewGroupTitle("");
      setNewGroupDescription("");
    } catch (err: unknown) {
      setActionError(extractApiErrorMessage(err) ?? t("groups.actionFailed"));
    } finally {
      setBusyGroupId(null);
    }
  };

  return (
    <Dialog
      title={t("groups.addDialogTitle", { name: requirementTitle })}
      description={t("groups.addDialogHint")}
      size="md"
      testId="add-to-group-dialog"
      onClose={onClose}
      footer={
        <button
          type="button"
          className="btn-primary"
          data-testid="group-add-done-btn"
          onClick={onClose}
        >
          {t("groups.addDone")}
        </button>
      }
    >
      <div className={styles.body}>
        {isLoading ? (
          <p role="status" className={styles.status} data-testid="group-add-loading">
            {t("groups.loading")}
          </p>
        ) : groupsError ? (
          <p role="alert" className={styles.error} data-testid="group-add-load-error">
            {groupsError}
          </p>
        ) : groups.length === 0 ? (
          <>
            <p className={styles.status} data-testid="group-add-empty">
              {t("groups.empty")}
            </p>
            {onCreateGroup ? (
              // Same create fields as the group manager (name + description),
              // so the empty state is a real way forward, not a detour.
              <form className={styles.createForm} onSubmit={(e) => void handleCreate(e)}>
                <label className={styles.field} htmlFor="group-add-create-title">
                  {t("groups.name")}
                  <input
                    id="group-add-create-title"
                    type="text"
                    className={styles.input}
                    data-testid="group-add-create-title"
                    value={newGroupTitle}
                    onChange={(event) => setNewGroupTitle(event.target.value)}
                    placeholder={t("groups.namePlaceholder")}
                    disabled={busyGroupId !== null}
                  />
                </label>
                <label className={styles.field} htmlFor="group-add-create-description">
                  {t("groups.description")}
                  <input
                    id="group-add-create-description"
                    type="text"
                    className={styles.input}
                    data-testid="group-add-create-description"
                    value={newGroupDescription}
                    onChange={(event) => setNewGroupDescription(event.target.value)}
                    disabled={busyGroupId !== null}
                  />
                </label>
                <button
                  type="submit"
                  className="btn-ghost"
                  data-testid="group-add-create-btn"
                  disabled={busyGroupId !== null || newGroupTitle.trim().length === 0}
                >
                  {t("groups.create")}
                </button>
              </form>
            ) : (
              <p className={styles.hint} data-testid="group-add-empty-hint">
                {t("groups.addEmptyHint")}
              </p>
            )}
          </>
        ) : (
          <ul className={styles.list} data-testid="group-add-list">
            {groups.map((group) => {
              const member = isMember(group);
              return (
                <li key={group.id} className={styles.groupRow}>
                  <label className={styles.groupLabel} htmlFor={`group-add-${group.id}`}>
                    <input
                      id={`group-add-${group.id}`}
                      type="checkbox"
                      className={styles.checkbox}
                      data-testid={`group-add-member-${group.id}`}
                      // Members are checked *and* locked: a second tick would
                      // be a membership the server already has, an untick
                      // would be a removal this dialog does not offer.
                      checked={member}
                      disabled={member || busyGroupId !== null}
                      onChange={() => void handleToggle(group)}
                    />
                    <span className={styles.groupTitle}>{group.title}</span>
                    {group.description && (
                      <span className={styles.groupDescription}>{group.description}</span>
                    )}
                    {member && (
                      <span className={styles.memberHint} data-testid={`group-add-ismember-${group.id}`}>
                        {t("groups.alreadyMember")}
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        {actionError && (
          <p role="alert" className={styles.error} data-testid="group-add-error">
            {actionError}
          </p>
        )}
      </div>
    </Dialog>
  );
}

AddToGroupDialog.displayName = "AddToGroupDialog";
