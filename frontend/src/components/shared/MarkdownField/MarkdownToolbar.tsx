/**
 * ARCH-L1-001 ReactFrontend — markdown formatting toolbar (#1287, Plan C
 * T-C2-8).
 *
 * Presentational only: it reports the clicked action and never touches the
 * textarea. `MarkdownPreview` owns the ref, applies `applyMarkdownFormat`, and
 * restores the returned selection — so this component has no second editor and
 * no duplicated insert logic.
 *
 * Every control is the shared `btn-icon` variant and carries an accessible name
 * (`btn-icon` has no text content, see `styles/global.css`); the icon is
 * `aria-hidden` so the name is not read twice.
 */

import {
  Bold,
  Code,
  Heading2,
  Italic,
  Link,
  List,
  ListOrdered,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import styles from "./MarkdownField.module.css";
import type { MarkdownAction } from "./markdown-format";

interface ToolbarAction {
  action: MarkdownAction;
  Icon: LucideIcon;
}

/** Order is the reading order of the toolbar (inline → block → link). */
const ACTIONS: readonly ToolbarAction[] = [
  { action: "bold", Icon: Bold },
  { action: "italic", Icon: Italic },
  { action: "heading", Icon: Heading2 },
  { action: "bulletList", Icon: List },
  { action: "numberedList", Icon: ListOrdered },
  { action: "link", Icon: Link },
  { action: "code", Icon: Code },
];

export interface MarkdownToolbarProps {
  onAction: (action: MarkdownAction) => void;
  disabled?: boolean;
}

export function MarkdownToolbar({
  onAction,
  disabled = false,
}: MarkdownToolbarProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div
      role="toolbar"
      aria-label={t("markdown.toolbar.label")}
      className={styles.toolbar}
      data-testid="md-toolbar"
    >
      {ACTIONS.map(({ action, Icon }) => {
        const label = t(`markdown.toolbar.${action}`);
        return (
          <button
            key={action}
            type="button"
            className="btn-icon"
            data-testid={`md-toolbar-${action}`}
            aria-label={label}
            title={label}
            disabled={disabled}
            // Keep focus and the text selection in the textarea: without this
            // the button steals focus on mousedown and the caret context is
            // already gone when `onClick` runs.
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onAction(action)}
          >
            <Icon size={16} aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
