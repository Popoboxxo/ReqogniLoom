import type { GlossaryTerm } from "../../types";
import styles from "./GlossaryTooltip.module.css";

interface GlossaryTooltipProps {
  termText: string;
  termData: GlossaryTerm;
}

export function GlossaryTooltip({ termText, termData }: GlossaryTooltipProps): JSX.Element {
  return (
    <span title={termData.definition} className={styles.term}>
      @{termText}
    </span>
  );
}
