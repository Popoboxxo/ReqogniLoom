import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import type { ActorCandidate, ActorValue } from "../../../../api/actors";
import { actorsApi } from "../../../../api/actors";
import { extractErrorMessage } from "../../../../api/client";
import { useWorkspace } from "../../../../context/WorkspaceContext";
import formStyles from "../ArtifactForm.module.css";
import styles from "./ActorPicker.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

/** The `actor` attribute's value: one entry, or the `multiple` wrapper. */
export type ActorFieldValue = ActorValue | { multiple: true; items: ActorValue[] } | null;

function isMultipleValue(
  value: ActorFieldValue
): value is { multiple: true; items: ActorValue[] } {
  return typeof value === "object" && value !== null && "multiple" in value;
}

function actorKey(actor: ActorValue): string {
  return actor.kind === "user" ? `user:${actor.id}` : `external:${actor.name}`;
}

/**
 * The user-visible label of a stored actor entry.
 *
 * An internal entry resolves against the loaded candidates; when the actor row
 * is not (yet) a workspace member (or the directory is unreadable) the id is
 * shown instead of silently rendering an empty chip, so an assigned owner is
 * never mistaken for "unassigned".
 */
function actorLabel(
  actor: ActorValue,
  candidates: ActorCandidate[],
  unknownLabel: string
): string {
  if (actor.kind === "external") return actor.name;
  const match = candidates.find((candidate) => candidate.id === actor.id);
  return match?.name ?? unknownLabel.replace("{{value}}", actor.id);
}

/**
 * ActorPicker (Attribut v3 WS2, #936, spec section 4) — the renderer of the
 * `actor` attribute type, replacing the legacy `user` `<select>` as the
 * people/team field.
 *
 * Shape: a searchable combobox (`role="combobox"` + `aria-autocomplete="list"`
 * on the input, `role="listbox"` popup). Internal users come from the
 * workspace-member directory (`actorsApi.list`); a search with no match offers
 * "create as external person" — but only when the attribute's
 * `allow_external` is true (spec section 4). `multiple` switches between the
 * single entry form and the `{"multiple": true, "items": [...]}` form, and the
 * component stores exactly that wire shape (`onChange` receives it verbatim).
 *
 * States: loading (members being fetched), error (directory unreadable — the
 * control stays usable for the already-stored value, only new picks are
 * blocked), empty (no candidates and no query), success, and disabled
 * (readOnly / `ArtifactForm` read mode) rendered as static text rather than a
 * dead input. All interactive elements carry `data-testid` (E2E requirement).
 */
export function ActorPicker({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<ActorFieldValue>): JSX.Element {
  const { i18n, t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const multiple = Boolean(attribute.multiple);
  const allowExternal = Boolean(attribute.allow_external);

  const [candidates, setCandidates] = useState<ActorCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const listboxId = `${testId}-listbox`;

  const workspaceId = activeWorkspace?.id;

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId) {
      setCandidates([]);
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    setLoadError(null);
    actorsApi
      .list(workspaceId)
      .then((resolved) => {
        if (cancelled) return;
        setCandidates(resolved);
        setLoading(false);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setCandidates([]);
        setLoadError(extractErrorMessage(exc));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const selected: ActorValue[] = useMemo(() => {
    if (isMultipleValue(value)) return value.items;
    return value ? [value] : [];
  }, [value]);

  const selectedKeys = useMemo(() => new Set(selected.map(actorKey)), [selected]);

  const trimmedQuery = query.trim();
  const matches = useMemo(() => {
    const needle = trimmedQuery.toLocaleLowerCase();
    return candidates.filter((candidate) => {
      if (selectedKeys.has(`user:${candidate.id}`)) return false;
      if (!needle) return true;
      return (
        candidate.name.toLocaleLowerCase().includes(needle) ||
        candidate.email.toLocaleLowerCase().includes(needle)
      );
    });
  }, [candidates, selectedKeys, trimmedQuery]);

  const externalKey = trimmedQuery.toLocaleLowerCase();
  const canCreateExternal =
    allowExternal &&
    trimmedQuery.length > 0 &&
    !selectedKeys.has(`external:${externalKey}`) &&
    !candidates.some(
      (candidate) => candidate.name.toLocaleLowerCase() === externalKey
    );
  const clearable = !attribute.required && selected.length > 0;

  // The popup's option list: member matches first, the external-create
  // affordance and the unassign affordance last (never mixed into search
  // order). `activeIndex` is a plain option index (-1 = nothing selected yet).
  const optionCount = matches.length + (canCreateExternal ? 1 : 0) + (clearable ? 1 : 0);
  const externalIndex = matches.length;
  const clearIndex = matches.length + (canCreateExternal ? 1 : 0);

  useEffect(() => {
    setActiveIndex(-1);
  }, [trimmedQuery, open, optionCount]);

  const inputRef = useRef<HTMLInputElement>(null);

  const emit = (next: ActorValue[]): void => {
    if (multiple) {
      onChange({ multiple: true, items: next });
    } else {
      onChange(next[0] ?? null);
    }
  };

  const addActor = (actor: ActorValue): void => {
    if (multiple) {
      emit([...selected, actor]);
      setQuery("");
      setActiveIndex(-1);
      inputRef.current?.focus();
    } else {
      emit([actor]);
      setQuery("");
      setOpen(false);
    }
  };

  const removeActor = (actor: ActorValue): void => {
    emit(selected.filter((entry) => actorKey(entry) !== actorKey(actor)));
  };

  const clearAll = (): void => {
    emit([]);
    setQuery("");
    setOpen(false);
  };

  const chooseActiveOption = (): void => {
    if (activeIndex >= 0 && activeIndex < matches.length) {
      addActor({ kind: "user", id: matches[activeIndex].id });
      return;
    }
    if (canCreateExternal && activeIndex === externalIndex) {
      addActor({ kind: "external", name: trimmedQuery });
      return;
    }
    if (clearable && activeIndex === clearIndex) clearAll();
  };

  const onInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => (optionCount ? (current + 1) % optionCount : -1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) =>
        optionCount ? (current - 1 + optionCount) % optionCount : -1
      );
    } else if (event.key === "Enter") {
      if (open && optionCount && activeIndex >= 0) {
        event.preventDefault();
        chooseActiveOption();
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  if (disabled) {
    const label = selected
      .map((actor) => actorLabel(actor, candidates, t("artifactForm.unknownValue")))
      .join(", ");
    return (
      <FieldShell
        attribute={attribute}
        language={i18n.language}
        errors={errors}
        testId={testId}
      >
        <textarea
          id={testId}
          data-testid={testId}
          className={`${formStyles.control} ${styles.readOnly}`}
          readOnly
          rows={1}
          value={label || t("artifactForm.unassignedOption")}
          {...ariaProps(attribute, testId, errors)}
        />
      </FieldShell>
    );
  }

  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <div
        className={styles.root}
        data-testid={testId}
        role={multiple ? "group" : undefined}
        aria-labelledby={multiple ? `${testId}-label` : undefined}
      >
        {multiple && selected.length > 0 ? (
          <div className={styles.chipRow}>
            {selected.map((actor) => {
              const label = actorLabel(
                actor,
                candidates,
                t("artifactForm.unknownValue")
              );
              return (
                <span
                  key={actorKey(actor)}
                  className={styles.chip}
                  data-testid={`${testId}-chip`}
                >
                  <span className={styles.chipLabel}>{label}</span>
                  <button
                    type="button"
                    className={styles.chipRemove}
                    data-testid={`${testId}-chip-remove`}
                    aria-label={t("artifactForm.actorRemove", { name: label })}
                    onClick={() => removeActor(actor)}
                  >
                    <X aria-hidden="true" size={14} />
                  </button>
                </span>
              );
            })}
          </div>
        ) : null}

        {/* The label's `htmlFor` targets `${testId}`, so that id must sit on
            the actual control in both variants (single + multiple); the wrapper
            only carries the group role in multiple mode. */}
        <input
          id={testId}
          data-testid={multiple ? `${testId}-search` : `${testId}-input`}
          ref={inputRef}
          className={`${formStyles.control} ${
            errors?.length ? formStyles.controlInvalid : ""
          }`}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && activeIndex >= 0 ? `${testId}-option-${activeIndex}` : undefined
          }
          placeholder={
            !multiple && selected.length
              ? actorLabel(selected[0], candidates, t("artifactForm.unknownValue"))
              : t("artifactForm.actorSearchPlaceholder")
          }
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onInputKeyDown}
          {...ariaProps(attribute, testId, errors)}
        />

        {open ? (
          <ul
            className={styles.listbox}
            id={listboxId}
            role="listbox"
            data-testid={listboxId}
          >
            {loading ? (
              <li className={styles.status} role="presentation" aria-busy="true">
                {t("artifactForm.actorLoading")}
              </li>
            ) : null}
            {!loading && loadError ? (
              <li className={styles.error} role="alert">
                {t("artifactForm.actorDirectoryUnavailable")}
              </li>
            ) : null}
            {!loading && !loadError && matches.length === 0 ? (
              <li
                className={styles.status}
                role="presentation"
                data-testid={`${testId}-empty`}
              >
                {candidates.length === 0
                  ? t("artifactForm.actorEmpty")
                  : t("artifactForm.actorNoMatches", { query: trimmedQuery })}
              </li>
            ) : null}

            {!loading &&
              matches.map((candidate, index) => {
                const active = activeIndex === index;
                return (
                  <li key={candidate.id} role="presentation">
                    <button
                      type="button"
                      id={`${testId}-option-${index}`}
                      role="option"
                      aria-selected={active}
                      className={`${styles.option} ${active ? styles.optionActive : ""}`}
                      data-testid={`${testId}-option-${candidate.id}`}
                      onClick={() => addActor({ kind: "user", id: candidate.id })}
                    >
                      <span>{candidate.name}</span>
                      {candidate.email && candidate.email !== candidate.name ? (
                        <span className={styles.optionMeta}>{candidate.email}</span>
                      ) : null}
                    </button>
                  </li>
                );
              })}

            {!loading && canCreateExternal ? (
              <li role="presentation">
                <button
                  type="button"
                  id={`${testId}-option-${externalIndex}`}
                  role="option"
                  aria-selected={activeIndex === externalIndex}
                  className={`${styles.option} ${styles.optionCreate} ${
                    activeIndex === externalIndex ? styles.optionActive : ""
                  }`}
                  data-testid={`${testId}-create-external`}
                  onClick={() => addActor({ kind: "external", name: trimmedQuery })}
                >
                  <Plus aria-hidden="true" size={14} />
                  {t("artifactForm.actorCreateExternal", { name: trimmedQuery })}
                </button>
              </li>
            ) : null}

            {!loading && clearable ? (
              <li role="presentation">
                <button
                  type="button"
                  id={`${testId}-option-${clearIndex}`}
                  role="option"
                  aria-selected={activeIndex === clearIndex}
                  className={styles.option}
                  data-testid={`${testId}-clear`}
                  onClick={clearAll}
                >
                  {t("artifactForm.unassignedOption")}
                </button>
              </li>
            ) : null}
          </ul>
        ) : null}
      </div>
    </FieldShell>
  );
}
