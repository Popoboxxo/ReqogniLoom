/**
 * ARCH-L1-001 ReactFrontend — BaselinesView stub.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L2-RF-007 (Preset-basierte Sichtbarkeit — Baselines gated)
 *
 * Baseline management view — stub until full implementation.
 * Hidden in Minimal preset (REQ-L2-RF-007 AC: Minimal → baselines ausgeblendet).
 */

import React from "react";
import { useTranslation } from "react-i18next";

export default function BaselinesView(): JSX.Element {
  const { t } = useTranslation();
  return (
    <div>
      <h2>{t("nav.baselines")}</h2>
      <p>{t("baselines.placeholder")}</p>
    </div>
  );
}
