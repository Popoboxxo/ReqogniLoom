/**
 * `<AiActionSection>` + `<AiActionIcon>` — the ONE home for every AI
 * (LLM-backed) action in the app.
 *
 * Issue #1092 ("KI-Aktionen verstreut in Panel-Kopfzeilen, Emoji '✨' als
 * UI-Icon"). Two defects, one cause:
 *
 *   1. `✨` is an **emoji**, not an icon. It renders platform-dependently
 *      (Apple Color Emoji / Segoe UI Emoji / Noto Color Emoji), so next to a
 *      design-system button it has no shared size, weight or colour. It is
 *      replaced here by lucide's `Sparkles` — the repo's existing icon set
 *      (`lucide-react`, already used by ~20 component groups), a flat
 *      single-colour stroke glyph in `currentColor`, so it inherits the
 *      button's colour in both themes instead of fighting it.
 *   2. Each AI action used to render itself in whatever panel header it
 *      happened to live in, so the same "KI-Ableitung" action appeared in a
 *      different place on every route. This section makes the *group* the
 *      unit: one titled region per route, all actions inside it carrying the
 *      same icon, so they read as "the AI things on this page" at a glance.
 *
 * Why the actions are passed as data rather than as `children`: the shared
 * icon is the whole point of the group, and a `children` API would let any
 * call site drop an un-iconned button into it. An `AiActionDescriptor[]`
 * makes "every AI action has the AI icon" true by construction — there is no
 * way to render a button here without it.
 *
 * Context awareness (#1092, DoD): the section renders **nothing** when
 * `actions` is empty, so a route without AI capability — or a user without
 * the role that grants it (`useHasRole('editor')`, the app's existing
 * workspace-role gate) — never sees an AI region at all. The caller decides
 * capability; this component only enforces the "no actions, no section"
 * contract.
 *
 * Button variant: `btn-secondary`, deliberately not `btn-primary`. Every
 * artifact route has exactly one primary action (its "New <Entity>" trigger,
 * `PageHeader.primaryAction`); an AI derivation that also renders as primary
 * is the #797 duplicate-primary complaint. With the section heading and the
 * shared icon carrying the AI meaning, the button hierarchy can stay honest.
 */

import { useId } from "react";
import { Sparkles } from "lucide-react";

import styles from "./AiActionSection.module.css";

/**
 * The one AI glyph, from the repo's existing icon set. Exported so an AI
 * panel/dialog that is *itself* the AI surface (e.g. the test-case draft
 * dialog) can carry the same mark — same icon, `currentColor`, 16px, matching
 * `ArtifactForm/widgets/StepsEditor.tsx`'s `Trash2 size={16}` convention.
 */
export function AiActionIcon(): JSX.Element {
  return <Sparkles aria-hidden="true" size={16} />;
}

/** One AI action rendered inside an {@link AiActionSection}. */
export interface AiActionDescriptor {
  /**
   * Already-translated label. Doubles as the button's accessible name, so it
   * must name the action and its object ("KI-Testfall", "KI-Ableitung") —
   * never a bare verb.
   */
  label: string;
  onClick: () => void;
  /** Disabled while the action's request is in flight. */
  disabled?: boolean;
  /** E2E hook (repo convention: every interactive element carries one). */
  testId: string;
  /**
   * Longer explanation, surfaced as the button's `title`. Same copy the
   * button carried before (#927): the AI proposes, the human confirms.
   */
  hint?: string;
  /** Accessible name to announce while `disabled` (e.g. "KI-Ableitung läuft…"). */
  busyLabel?: string;
}

export interface AiActionSectionProps {
  /** Route-local AI actions. An empty array renders no section at all. */
  actions: readonly AiActionDescriptor[];
  /** Already-translated section heading. */
  title: string;
  /** Already-translated one-liner under the heading. */
  hint?: string;
  /** E2E hook for the section itself. */
  testId?: string;
}

export function AiActionSection({
  actions,
  title,
  hint,
  testId = "ai-actions-section",
}: AiActionSectionProps): JSX.Element | null {
  const headingId = useId();
  // Context awareness: no capability, no region — not an empty box.
  if (actions.length === 0) return null;

  return (
    <section
      className={styles.section}
      data-testid={testId}
      aria-labelledby={headingId}
    >
      <h3 className={styles.heading} id={headingId}>
        <AiActionIcon />
        <span>{title}</span>
      </h3>
      {hint && <p className={styles.hint}>{hint}</p>}
      <div className={styles.actions}>
        {actions.map((action) => (
          <button
            key={action.testId}
            type="button"
            className="btn-secondary"
            onClick={action.onClick}
            disabled={action.disabled}
            data-testid={action.testId}
            {...(action.hint ? { title: action.hint } : {})}
            {...(action.disabled && action.busyLabel
              ? { "aria-label": action.busyLabel }
              : {})}
          >
            <AiActionIcon />
            {action.label}
          </button>
        ))}
      </div>
    </section>
  );
}
