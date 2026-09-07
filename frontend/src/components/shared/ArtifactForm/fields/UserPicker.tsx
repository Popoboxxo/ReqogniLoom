import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { usersApi, type ManagedUser } from "../../../../api/users";
import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

/**
 * Picks a tenant user. The `user` attribute type exists so the
 * Menschen-im-System spec's `owner`/`assignee` FKs render without a new field
 * kind — this component is that type's renderer.
 *
 * DEVIATION from the plan brief: the brief imported a `User` type with a
 * `full_name` field from `api/users`. The real module (verified against the
 * live file) exports `ManagedUser` (no `User` export exists) with
 * `username`/`email` — no `full_name` field. Uses `username` as the display
 * label, falling back to `email`, mirroring the brief's own fallback pattern.
 */
export function UserPicker({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n, t } = useTranslation();
  const [users, setUsers] = useState<ManagedUser[]>([]);

  useEffect(() => {
    let cancelled = false;
    usersApi
      .list()
      .then((resolved) => {
        if (!cancelled) setUsers(resolved);
      })
      .catch(() => {
        if (!cancelled) setUsers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const current = value ?? "";
  const isUnknown = current !== "" && !users.some((u) => u.id === current);

  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <select
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        value={current}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      >
        <option value="">{t("artifactForm.unassignedOption")}</option>
        {isUnknown ? (
          <option value={current}>
            {t("artifactForm.unknownValue", { value: current })}
          </option>
        ) : null}
        {users.map((user) => (
          <option key={user.id} value={user.id}>
            {user.username || user.email}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}
