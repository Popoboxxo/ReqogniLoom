import { useEffect, useState } from "react";

import {
  attributeDefinitionsApi,
  type AttributeItemType,
} from "../../../api/attribute-definitions";
import { useWorkspace } from "../../../context/WorkspaceContext";

const EMPTY: ReadonlySet<string> = new Set();

/**
 * The effective approval-gate field names for `(activeWorkspace, itemType)`
 * (GitHub #1192).
 *
 * Rule 5 (`workflow.precondition_rules.check_mandatory_fields`) refuses an
 * approval while the workspace preset's mandatory fields are empty, but the
 * resolved definition the form renders only carries the definition's own
 * `required` flags — `acceptance_criteria` is `required: false` there yet
 * gate-required under the standard/extended preset, so it used to be marked
 * only after a refused "Freigeben".
 *
 * `GET /api/v1/attribute-schema/` now exposes the effective set
 * (`is_required`), mirrored here so the form can mark those fields up front.
 * The lookup is best-effort: a missing workspace, an unsupported item type or
 * a failed request degrade to an empty set — the form must never fail to render
 * because a discovery request did.
 */
export function useGateRequiredFields(
  itemType: AttributeItemType
): ReadonlySet<string> {
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const [names, setNames] = useState<ReadonlySet<string>>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId) {
      setNames(EMPTY);
      return undefined;
    }
    // Guarded: test suites that mock `api/attribute-definitions` with only the
    // subset they need predate this method; an undefined call would throw inside
    // the effect and take the whole form down. `Promise.resolve` additionally
    // absorbs a mock that returns nothing. Production always returns a promise.
    if (typeof attributeDefinitionsApi.getSchema !== "function") {
      setNames(EMPTY);
      return undefined;
    }
    let request: Promise<
      import("../../../api/attribute-definitions").AttributeSchemaRow[]
    >;
    try {
      request = Promise.resolve(
        attributeDefinitionsApi.getSchema(workspaceId, itemType)
      );
    } catch {
      setNames(EMPTY);
      return undefined;
    }
    request
      .then((rows) => {
        if (cancelled) return;
        setNames(
          new Set(
            (rows ?? [])
              .filter((row) => row.is_required)
              .map((row) => row.attribute_name)
          )
        );
      })
      .catch(() => {
        if (!cancelled) setNames(EMPTY);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, itemType]);

  return names;
}
