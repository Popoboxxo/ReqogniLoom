/**
 * ARCH-L1-001 ReactFrontend — GoalForm (REQ-L2-TE-020).
 *
 * Create/edit form for a single Goal, rendered in the detail pane of the
 * Goals split view instead of below the list (UI concept ch. 6.2 — the
 * detail pane is where an artifact is worked on).
 *
 * "Edit" is not an in-place update: it appends a new immutable row to the
 * same lineage (`goalsApi.createVersion`, design spec 2.3), which is why the
 * submit label changes with the mode. The API call itself lives in the page
 * so that a rejection surfaces in one place (ch. 12.12).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Goal } from "../../types";

export interface GoalFormProps {
  /** `null` = create a new lineage; a Goal = append a version to its lineage. */
  editing: Goal | null;
  onSubmit: (values: { title: string; description: string }) => void;
  onCancel: () => void;
}

const labelStyle: React.CSSProperties = {
  fontSize: "var(--font-size-sm)",
  fontWeight: "var(--weight-semibold)",
  color: "var(--color-text)",
};

const inputStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

export function GoalForm({ editing, onSubmit, onCancel }: GoalFormProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState(editing?.title ?? "");
  const [description, setDescription] = useState(editing?.description ?? "");

  // Switching the edited goal (or from edit to create) without remounting
  // must not keep the previous values in the fields.
  useEffect(() => {
    setTitle(editing?.title ?? "");
    setDescription(editing?.description ?? "");
  }, [editing]);

  return (
    <form
      data-testid="goal-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ title, description });
      }}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
      }}
    >
      <h2
        style={{
          margin: "0 0 var(--space-2)",
          fontSize: "var(--font-size-xl)",
          lineHeight: "var(--leading-tight)",
          letterSpacing: "var(--tracking-tight)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--color-text)",
        }}
      >
        {editing
          ? t("goals.editTitle", "Ziel bearbeiten")
          : t("goals.newGoal", "Neues Ziel")}
      </h2>

      <label htmlFor="goal-title" style={labelStyle}>
        {t("goals.goalTitle", "Titel")}
      </label>
      <input
        id="goal-title"
        data-testid="goal-title-input"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={inputStyle}
      />

      <label htmlFor="goal-description" style={labelStyle}>
        {t("goals.goalDescription", "Beschreibung")}
      </label>
      <input
        id="goal-description"
        data-testid="goal-description-input"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        style={inputStyle}
      />

      <div
        style={{
          display: "flex",
          gap: "var(--space-2)",
          justifyContent: "flex-end",
          marginTop: "var(--space-2)",
        }}
      >
        <button
          type="button"
          className="btn-ghost"
          data-testid="goal-edit-cancel-button"
          onClick={onCancel}
        >
          {t("actions.cancel", "Abbrechen")}
        </button>
        <button type="submit" className="btn-primary" data-testid="goal-create-button">
          {editing
            ? t("goals.saveVersion", "Neue Version speichern")
            : t("goals.create", "Ziel anlegen")}
        </button>
      </div>
    </form>
  );
}

GoalForm.displayName = "GoalForm";
