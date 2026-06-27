/**
 * ARCH-L1-001 ReactFrontend — Risk list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Lists all Risks for the active workspace.
 */

import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { risksApi } from "../../api/risks";
import type { Risk } from "../../types";

export default function RiskList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Risk[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    risksApi
      .list(activeWorkspace.id)
      .then((resp) => setItems(resp.results))
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, [activeWorkspace]);

  if (isLoading) return <p>{t("loading")}</p>;

  return (
    <div>
      <h2
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          marginTop: 0,
          marginBottom: "var(--space-6)",
        }}
      >
        {t("nav.risks")}
      </h2>
      {items.length === 0 ? (
        <p
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {t("editor.empty")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((item) => (
            <li
              key={item.id}
              style={{
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "var(--space-2)",
                background: "var(--color-surface)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
              }}
            >
              <strong>{item.title}</strong>{" "}
              <span
                style={{
                  color: "var(--color-text-muted)",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                — {item.severity} | {item.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
