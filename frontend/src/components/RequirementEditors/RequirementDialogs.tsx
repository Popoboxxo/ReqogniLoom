/**
 * Page-level dialogs of the Requirements route.
 *
 * Extracted from `RequirementEditors.tsx` (repowise CCN 44): each dialog owns
 * its own visibility conditional, so the page component just mounts them.
 * Group dialogs stay at page level on purpose — the SplitView column clips
 * overflow. All test ids, labels and handlers are unchanged.
 */
import { useTranslation } from "react-i18next";
import type { Requirement } from "../../types";
import { AiDerivationDialog, type AiDerivationDraft } from "../shared/AiDerivationDialog";
import { Dialog } from "../shared/Dialog";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { DeriveTestCasePanel } from "../TestCaseEditors/DeriveTestCasePanel";
import { GroupManager } from "./GroupManager";
import { AddToGroupDialog } from "./AddToGroupDialog";
import type { useRequirementGroups } from "./useRequirementGroups";

type RequirementGroups = ReturnType<typeof useRequirementGroups>;

export interface UnsavedChangesDialogProps {
  pendingSelectId: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function UnsavedChangesDialog({
  pendingSelectId,
  onConfirm,
  onCancel,
}: UnsavedChangesDialogProps): JSX.Element | null {
  const { t } = useTranslation();
  return pendingSelectId ? (
    <ConfirmDialog
      title={t("editor.unsavedChangesTitle")}
      message={t("editor.unsavedChangesMessage")}
      confirmLabel={t("editor.discardChanges")}
      onConfirm={onConfirm}
      onCancel={onCancel}
      testId="req-unsaved-changes-dialog"
    />
  ) : null;
}

export interface DeriveTestcaseDialogProps {
  show: boolean;
  requirement: Requirement | null | undefined;
  workspaceId: string | undefined;
  onClose: () => void;
}

export function DeriveTestcaseDialog({
  show,
  requirement,
  workspaceId,
  onClose,
}: DeriveTestcaseDialogProps): JSX.Element | null {
  const { t } = useTranslation();
  return show && requirement && workspaceId ? (
    <Dialog
      title={t("deriveTestcase.title")}
      description={requirement.title}
      onClose={onClose}
      size="lg"
      testId="derive-testcase-dialog"
    >
      <DeriveTestCasePanel
        workspaceId={workspaceId}
        requirement={{ id: requirement.id, title: requirement.title }}
        onCreated={onClose}
      />
    </Dialog>
  ) : null;
}

export interface AiDerivationDialogProps {
  show: boolean;
  requirement: Requirement | null | undefined;
  drafts: AiDerivationDraft[] | null;
  isLoading: boolean;
  loadError: string | null;
  isSubmitting: boolean;
  submitError: string | null;
  onDecision: (drafts: AiDerivationDraft[], parked: boolean) => void;
  onDiscard: () => void;
}

export function RequirementAiDerivationDialog({
  show,
  requirement,
  drafts,
  isLoading,
  loadError,
  isSubmitting,
  submitError,
  onDecision,
  onDiscard,
}: AiDerivationDialogProps): JSX.Element | null {
  const { t } = useTranslation();
  return show && requirement ? (
    <AiDerivationDialog
      open
      title={t("actions.deriveAi")}
      sourceLabel={requirement.title}
      drafts={drafts}
      isLoading={isLoading}
      loadError={loadError}
      isSubmitting={isSubmitting}
      submitError={submitError}
      selectable
      onConfirm={(drafts) => onDecision(drafts, false)}
      onReviewLater={(drafts) => onDecision(drafts, true)}
      onDiscard={onDiscard}
      testIdPrefix="req-derive-drafts"
    />
  ) : null;
}

export interface RequirementGroupDialogsProps {
  isManagerOpen: boolean;
  hasEditorRole: boolean;
  groups: RequirementGroups;
  requirements: Requirement[];
  addToGroupRequirement: Requirement | null | undefined;
  onManagerClose: () => void;
  onAddToGroupClose: () => void;
}

export function RequirementGroupDialogs({
  isManagerOpen,
  hasEditorRole,
  groups,
  requirements,
  addToGroupRequirement,
  onManagerClose,
  onAddToGroupClose,
}: RequirementGroupDialogsProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <>
      {isManagerOpen && hasEditorRole ? (
        <Dialog
          title={t("groups.title")}
          description={t("groups.dialogHint")}
          size="lg"
          testId="group-manager-dialog"
          onClose={onManagerClose}
        >
          <GroupManager
            groups={groups.managerGroups}
            requirements={requirements}
            isLoading={groups.isLoading}
            error={groups.error}
            onCreate={groups.createGroup}
            onAddMember={groups.addMember}
            onRemoveMember={groups.removeMember}
          />
        </Dialog>
      ) : null}
      {addToGroupRequirement && hasEditorRole ? (
        <AddToGroupDialog
          requirementId={addToGroupRequirement.id}
          requirementTitle={addToGroupRequirement.title || t("editor.untitled")}
          groups={groups.managerGroups}
          isLoading={groups.isLoading}
          groupsError={groups.error}
          onAdd={groups.addMember}
          onCreateGroup={groups.createGroup}
          onClose={onAddToGroupClose}
        />
      ) : null}
    </>
  );
}
