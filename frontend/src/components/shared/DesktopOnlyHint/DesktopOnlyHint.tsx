/**
 * Honest mobile guard for graph/canvas editors (plan M8, REQ-212).
 *
 * These editors are mouse-driven (wheel zoom, drag handles, hover anchors).
 * Instead of offering a half-working editor on a phone we render a clear hint
 * and leave the canvas usable for reading/panning where the underlying
 * library supports touch. The hint is hidden on desktop.
 */
import { useTranslation } from "react-i18next";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import styles from "./DesktopOnlyHint.module.css";

/**
 * The call sites pass a human feature name (`Diagramm`, `Canvas`). Interpolate
 * a translated label instead of dropping a German literal into the English
 * sentence. Mapping lives here so the two callers cannot drift apart; unknown
 * values fall back to the neutral canvas label rather than raw text.
 */
const FEATURE_LABEL_KEYS: Record<string, string> = {
  Diagramm: "mobile.featureDiagram",
  Diagram: "mobile.featureDiagram",
  Canvas: "mobile.featureCanvas",
};

export function DesktopOnlyHint({ feature }: { feature: string }): JSX.Element | null {
  const { t } = useTranslation();
  const isMobile = useMediaQuery("(max-width: 768px)");
  if (!isMobile) return null;

  const featureLabel = t(FEATURE_LABEL_KEYS[feature] ?? "mobile.featureCanvas");

  return (
    <div className={styles.hint} role="status" data-testid="editor-desktop-hint">
      {t("mobile.desktopOnly", "{{feature}}: editing is available on desktop only.", { feature: featureLabel })}
    </div>
  );
}
