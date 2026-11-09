/**
 * ARCH-L1-001 ReactFrontend — group administration (P6 Task 6.3).
 *
 * Create a visual requirement group and manage its membership with a
 * requirement search. Purely presentational: the group API state lives in
 * `useRequirementGroups`, which the requirement page owns and passes down.
 *
 * Groups are visual clusters (V11): adding or removing a member never changes
 * a requirement, its allocation or its workflow state.
 */

import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../api/client";
import { useRequiredValidation } from "../shared/useRequiredValidation";
import type { Requirement } from "../../types";
import type {
  GroupManagerGroup,
  UseRequirementGroupsResult,
} from "./useRequirementGroups";
import styles from "./GroupManager.module.css";

/** Maximum number of search hits offered per group (keeps the panel compact). */
const MAX_SEARCH_RESULTS = 8;

export interface GroupManagerProps {
  groups: GroupManagerGroup[];
  /** The full (unfiltered) requirement list the search runs over. */
  requirements: readonly Requirement[];
  isLoading: boolean;
  error: string | null;
  onCreate: UseRequirementGroupsResult["createGroup"];
  onAddMember: UseRequirementGroupsResult["addMember"];
  onRemoveMember: UseRequirementGroupsResult["removeMember"];
}

function matchesQuery(requirement: Requirement, query: string): boolean {
  if (!query) return false;
  const needle = query.trim().toLowerCase();
  if (!needle) return false;
  return (
    requirement.title.toLowerCase().includes(needle) ||
    (requirement.uid ?? "").toLowerCase().includes(needle)
  );
}

export function GroupManager({
  groups,
  requirements,
  isLoading,
  error,
  onCreate,
  onAddMember,
  onRemoveMember,
}: GroupManagerProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [searchByGroup, setSearchByGroup] = useState<Record<string, string>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // #1732: the Create button is only blocked by an in-flight action. An empty
  // name is explained on click (field-level role="alert" + focus).
  const {
    errors: requiredErrors,
    validate,
    focusFirstInvalid,
    clearError,
    fieldProps,
    errorId,
  } = useRequiredValidation();

  const run = async (key: string, action: () => Promise<void>): Promise<void> => {
    setBusyKey(key);
    setActionError(null);
    try {
      await action();
    } catch (err: unknown) {
      setActionError(
        extractApiErrorMessage(err) ?? t("groups.actionFailed")
      );
    } finally {
      setBusyKey(null);
    }
  };

  const handleCreate = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (busyKey !== null) return;
    const fields = [{ name: "title", value: title, inputId: "group-title-input" }];
    const invalid = validate(fields);
    if (invalid.length > 0) {
      focusFirstInvalid(fields, invalid);
      return;
    }
    void run("create", async () => {
      await onCreate(title.trim(), description.trim());
      setTitle("");
      setDescription("");
    });
  };

  const searchCandidates = useMemo(() => {
    const byGroup: Record<string, Requirement[]> = {};
    for (const group of groups) {
      const query = searchByGroup[group.id] ?? "";
      const memberIds = new Set(group.members.map((member) => member.requirementId));
      byGroup[group.id] =
        query.trim().length === 0
          ? []
          : requirements
              .filter(
                (requirement) =>
                  !memberIds.has(requirement.id) &&
                  matchesQuery(requirement, query)
              )
              .slice(0, MAX_SEARCH_RESULTS);
    }
    return byGroup;
  }, [groups, requirements, searchByGroup]);

  return (
    <section
      className={styles.manager}
      data-testid="group-manager"
      aria-labelledby="group-manager-heading"
    >
      <h3 id="group-manager-heading" className={styles.heading}>
        {t("groups.title")}
      </h3>

      <form className={styles.createForm} onSubmit={handleCreate}>
        <label className={styles.field}>
          {t("groups.name")}
          <input
            id="group-title-input"
            type="text"
            className={styles.input}
            data-testid="group-title-input"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              clearError("title");
            }}
            placeholder={t("groups.namePlaceholder")}
            disabled={busyKey !== null}
            {...fieldProps("title")}
          />
        </label>
        {requiredErrors.title ? (
          <p
            id={errorId("title")}
            role="alert"
            className={styles.error}
            data-testid="group-title-error"
          >
            {requiredErrors.title}
          </p>
        ) : null}
        <label className={styles.field}>
          {t("groups.description")}
          <input
            type="text"
            className={styles.input}
            data-testid="group-description-input"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            disabled={busyKey !== null}
          />
        </label>
        <button
          type="submit"
          className={`btn-ghost ${styles.createButton}`}
          data-testid="group-create-btn"
          disabled={busyKey !== null}
        >
          {t("groups.create")}
        </button>
      </form>

      {(error || actionError) && (
        <p role="alert" className={styles.error} data-testid="group-manager-error">
          {actionError ?? error}
        </p>
      )}

      {isLoading ? (
        <p className={styles.status} data-testid="group-manager-loading">
          {t("groups.loading")}
        </p>
      ) : groups.length === 0 ? (
        <p className={styles.status} data-testid="group-manager-empty">
          {t("groups.empty")}
        </p>
      ) : (
        <ul className={styles.groupList} data-testid="group-list">
          {groups.map((group) => {
            const candidates = searchCandidates[group.id] ?? [];
            const query = searchByGroup[group.id] ?? "";
            return (
              <li
                key={group.id}
                className={styles.group}
                data-testid={`group-item-${group.id}`}
              >
                <div className={styles.groupHeader}>
                  <span className={styles.groupTitle}>{group.title}</span>
                  {group.description && (
                    <span className={styles.groupDescription}>
                      {group.description}
                    </span>
                  )}
                </div>

                {group.members.length === 0 ? (
                  <p
                    className={styles.status}
                    data-testid={`group-members-empty-${group.id}`}
                  >
                    {t("groups.noMembers")}
                  </p>
                ) : (
                  <ul
                    className={styles.memberList}
                    data-testid={`group-members-${group.id}`}
                  >
                    {group.members.map((member) => (
                      <li
                        key={member.requirementId}
                        className={styles.member}
                        data-testid={`group-member-${group.id}-${member.requirementId}`}
                      >
                        <span className={styles.memberLabel}>
                          {member.uid ? `${member.uid} · ` : ""}
                          {member.label}
                        </span>
                        <button
                          type="button"
                          className={`btn-icon ${styles.removeButton}`}
                          data-testid={`group-member-remove-${group.id}-${member.requirementId}`}
                          aria-label={t("groups.removeMember", {
                            name: member.label,
                          })}
                          title={t("groups.removeMember", { name: member.label })}
                          disabled={busyKey === `remove:${group.id}:${member.requirementId}`}
                          onClick={() =>
                            void run(`remove:${group.id}:${member.requirementId}`, () =>
                              onRemoveMember(group.id, member.requirementId)
                            )
                          }
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <label className={styles.field}>
                  {t("groups.addMember")}
                  <input
                    type="search"
                    className={styles.input}
                    data-testid={`group-search-${group.id}`}
                    value={query}
                    placeholder={t("groups.searchPlaceholder")}
                    aria-label={t("groups.searchPlaceholder")}
                    onChange={(event) =>
                      setSearchByGroup((previous) => ({
                        ...previous,
                        [group.id]: event.target.value,
                      }))
                    }
                  />
                </label>

                {query.trim().length > 0 && (
                  <ul
                    className={styles.candidateList}
                    data-testid={`group-search-results-${group.id}`}
                  >
                    {candidates.length === 0 ? (
                      <li className={styles.status}>
                        {t("groups.searchEmpty")}
                      </li>
                    ) : (
                      candidates.map((candidate) => (
                        <li key={candidate.id} className={styles.candidate}>
                          <span className={styles.memberLabel}>
                            {candidate.uid ? `${candidate.uid} · ` : ""}
                            {candidate.title || t("editor.untitled")}
                          </span>
                          <button
                            type="button"
                            className={`btn-ghost ${styles.addButton}`}
                            data-testid={`group-add-${group.id}-${candidate.id}`}
                            disabled={busyKey === `add:${group.id}:${candidate.id}`}
                            onClick={() =>
                              void run(`add:${group.id}:${candidate.id}`, () =>
                                onAddMember(group.id, candidate.id)
                              )
                            }
                          >
                            {t("groups.add")}
                          </button>
                        </li>
                      ))
                    )}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
