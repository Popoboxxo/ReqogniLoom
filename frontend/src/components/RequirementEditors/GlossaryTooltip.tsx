import React from "react";
import type { GlossaryTerm } from "../../types";

interface GlossaryTooltipProps {
  termText: string;
  termData: GlossaryTerm;
}

export function GlossaryTooltip({ termText, termData }: GlossaryTooltipProps): JSX.Element {
  return (
    <span
      title={termData.definition}
      style={{
        borderBottom: "1px dashed var(--color-primary)",
        color: "var(--color-primary)",
        cursor: "help",
        fontWeight: "bold",
        backgroundColor: "var(--color-surface)",
        padding: "0 2px",
        borderRadius: "2px",
      }}
    >
      @{termText}
    </span>
  );
}
