/**
 * ARCH-L1-001 ReactFrontend — <MarkdownField> (#1287, Plan C T-C2-8).
 *
 * A thin preference-aware wrapper around the one markdown editor this app has
 * (`RequirementEditors/MarkdownPreview`). It does **not** render a second
 * textarea; it resolves `ui.markdown.toolbar` and tells the existing editor
 * whether to show the formatting toolbar.
 *
 * Resolution (`auto` is the registry default):
 *
 * | stored value | toolbar |
 * |--------------|---------|
 * | `auto`       | visible from `AUTO_MIN_LINES` lines on |
 * | `on` / `off` | fixed |
 *
 * The toggle in the editor head writes the **user** level through
 * `usePatchPreferenceLevel("user")`, so one person's choice never changes the
 * workspace or tenant default.
 *
 * Degradation: `usePreferenceValue` already answers `auto` while the query is
 * loading and on error. Additionally, a render without the Q1 query layer (a
 * unit harness or an embedded integration still on the old tree) keeps the
 * field usable in `auto` and simply omits the toggle — no throw, no blocking
 * spinner in front of a text editor.
 */

import { useContext } from "react";
import { QueryClientContext } from "@tanstack/react-query";

import {
  usePatchPreferenceLevel,
  usePreferenceValue,
} from "../../../queries/preferences";
import { MarkdownPreview } from "../../RequirementEditors/MarkdownPreview";

/** Q1 key (Plan C §2.4); the registry default is `auto`. */
export const MARKDOWN_TOOLBAR_PREFERENCE_KEY = "ui.markdown.toolbar";

export type MarkdownToolbarMode = "auto" | "on" | "off";

/** `auto` shows the toolbar once the value is at least this many lines long. */
const AUTO_MIN_LINES = 3;

export interface MarkdownFieldProps {
  /** Id of the underlying `<textarea>` (resolves the caller's `<label>`). */
  id: string;
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  /** Backing artifact id, used by the glossary-reference affordance. */
  artifactId?: string | null;
}

interface MarkdownFieldViewProps extends MarkdownFieldProps {
  mode: MarkdownToolbarMode;
  /** Omitted when no preference layer is available: no dead toggle. */
  onToggleToolbar?: () => void;
}

function normalizeMode(raw: unknown): MarkdownToolbarMode {
  return raw === "on" || raw === "off" || raw === "auto" ? raw : "auto";
}

function wantsToolbar(mode: MarkdownToolbarMode, value: string): boolean {
  if (mode === "on") return true;
  if (mode === "off") return false;
  return value.split("\n").length >= AUTO_MIN_LINES;
}

function MarkdownFieldView({
  id,
  value,
  onChange,
  disabled = false,
  artifactId = null,
  mode,
  onToggleToolbar,
}: MarkdownFieldViewProps): JSX.Element {
  return (
    <MarkdownPreview
      id={id}
      value={value}
      onChange={onChange}
      disabled={disabled}
      artifactId={artifactId}
      showToolbar={wantsToolbar(mode, value)}
      onToggleToolbar={onToggleToolbar}
    />
  );
}

function MarkdownFieldWithPreferences(
  props: MarkdownFieldProps
): JSX.Element {
  const stored = usePreferenceValue<unknown>(
    MARKDOWN_TOOLBAR_PREFERENCE_KEY,
    "auto"
  );
  const mode = normalizeMode(stored);
  const patch = usePatchPreferenceLevel("user");
  const showToolbar = wantsToolbar(mode, props.value);

  const onToggleToolbar = (): void => {
    patch.mutate({
      [MARKDOWN_TOOLBAR_PREFERENCE_KEY]: showToolbar ? "off" : "on",
    });
  };

  return (
    <MarkdownFieldView
      {...props}
      mode={mode}
      onToggleToolbar={onToggleToolbar}
    />
  );
}

export function MarkdownField(props: MarkdownFieldProps): JSX.Element {
  const queryClient = useContext(QueryClientContext);

  if (!queryClient) {
    // Degradation path (see file header): stays in `auto`, no toggle.
    return <MarkdownFieldView {...props} mode="auto" />;
  }

  return <MarkdownFieldWithPreferences {...props} />;
}
