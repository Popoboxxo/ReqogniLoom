/**
 * ArtifactInspector — "Diff" tab (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-036
 *
 * The tab adds the **one** comparison row spec §2.2 asks for ("exactly one
 * pair line") above the field-level diff:
 *
 *   Basis <name> → Arbeitsstand vN      (with a baseline — D6, B2.0-1)
 *   Vergleich vA → vB                   (version-to-version, always available)
 *
 * The range shown is the range `ArtifactDiff` actually resolved — not the
 * shell's request. That distinction is the M-04 defect: the shell seeds both
 * sides to the current version, so a request-derived line would claim
 * "v1 → v1" while the panel shows something else.
 *
 * **M1 deviation (documented):** the baseline selector
 * (`data-testid="inspector-baseline-select"`) is not rendered yet. It needs
 * `GET /api/v1/artifacts/<pk>/baselines/` (plan task B2.0-1), which is not on
 * `main`; inventing a client-side filter over the workspace baseline list is
 * exactly the option spec §11 D6 rejects. The pair line therefore renders the
 * version pair until B2.0-1 lands — the testid is already reserved in the
 * contract so the inventory stays complete.
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { DiffPanel } from "../DiffPanel";
import type { ArtifactDiffRange } from "../../../ArtifactDiff/ArtifactDiff";
import { INSPECTOR_TEST_IDS } from "../inspectorContract";
import type { ArtifactKind } from "../types";
import styles from "../InspectorShell.module.css";

export interface DiffTabProps {
  kind: ArtifactKind;
  entityId: string | number;
  leftVersion: number;
  rightVersion: number;
}

export function DiffTab(props: DiffTabProps): JSX.Element {
  const { t } = useTranslation();
  // `null` until the version list has loaded — the same value DiffPanel's own
  // M-04 handling treats as "no resolved comparison yet".
  const [range, setRange] = useState<ArtifactDiffRange | null>(null);

  const handleRangeChange = useCallback((next: ArtifactDiffRange | null): void => {
    setRange((prev) => {
      if (prev && next && prev.from === next.from && prev.to === next.to) return prev;
      return next;
    });
  }, []);

  const pairText =
    range === null
      ? t("sidebar.inspector.diffPair.pending", {
          defaultValue: "Comparison is being prepared",
        })
      : t("sidebar.inspector.diffPair.versions", {
          from: range.from,
          to: range.to,
          defaultValue: "Comparison v{{from}} → v{{to}}",
        });

  return (
    <div className={styles.tabBody}>
      <p className={styles.diffPair} data-testid={INSPECTOR_TEST_IDS.diffPair}>
        {pairText}
      </p>
      <DiffPanel {...props} onRangeResolved={handleRangeChange} variant="tab" />
    </div>
  );
}
