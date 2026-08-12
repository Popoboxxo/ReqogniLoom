/**
 * Workflow status helpers shared by every artifact list (GH-453).
 *
 * req_id: REQ-165/REQ-166 (per-entity workflows), REQ-003 (list toolbar)
 *
 * Background
 * ----------
 * Every artifact list used to build its status filter from one hardcoded
 * `WORKFLOW_STATES` array. That array matched *no* entity exactly: the backend
 * gives each entity type its own vocabulary in
 * `backend/workflow/definition_store.py` — lowercase `draft`/`in_review`/
 * `approved` for Requirement/StakeholderNeed, Title Case `Draft`/`In Review`/
 * `Approved` for Adr, `Identified`/`Mitigated` for Risk, `Open`/`Resolved` for
 * Issue, German `Entwurf`/`Freigegeben` for Goal — and workspaces may edit
 * their state machine on top of that. Picking any option that the loaded items
 * did not literally carry produced an empty list, because the lists compare
 * with `===`.
 *
 * Approach
 * --------
 * Derive the options from the data instead of hardcoding them. The set of
 * values actually present is correct for every entity type, every rigor preset
 * and every workspace-customized state machine at once, and it cannot drift
 * away from `PRESET_SCHEMAS`. A state that no loaded item carries is not
 * offered — filtering on it would have yielded an empty list anyway.
 *
 * `STATUS_LABELS` / `humanizeStatus` keep the raw value out of the UI: the
 * GH-453 rename lowercased the *values* of `TestCase.Status` while its Django
 * labels stayed Title Case, and the UI must keep rendering the readable form.
 * Same split as `components/TestRuns/testRunStatusLabel.ts`, which does this
 * for the (separate) test-run execution states.
 */

/**
 * Canonical lifecycle ordering, lowercased. Used only for sorting, so it may
 * span all entity vocabularies at once: two states from different entities
 * never meet in one list. Unknown states sort last, in alphabetical order.
 */
const STATUS_ORDER: readonly string[] = [
  // Pre-work / intake
  'draft',
  'entwurf',
  'open',
  'identified',
  'submitted',
  // Under way
  'in progress',
  'in_progress',
  'ready',
  'in review',
  'in_review',
  'review',
  'under review',
  'under_review',
  'monitored',
  // Settled
  'approved',
  'freigegeben',
  'accepted',
  'mitigated',
  'resolved',
  'implemented',
  'verified',
  'done',
  'closed',
  // Terminal / withdrawn
  'rejected',
  'wontfix',
  'superseded',
  'outdated',
  'archiviert',
  'archived',
  'deprecated',
  'deleted',
];

const STATUS_RANK: ReadonlyMap<string, number> = new Map(
  STATUS_ORDER.map((state, index) => [state, index]),
);

/**
 * Display labels for values whose readable form is not just a capitalization
 * of the raw value. Keys are the lowercased raw value.
 */
const STATUS_LABELS: Readonly<Record<string, string>> = {
  in_review: 'In Review',
  'in review': 'In Review',
  in_progress: 'In Progress',
  'in progress': 'In Progress',
  under_review: 'Under Review',
  'under review': 'Under Review',
  wontfix: "Won't Fix",
};

/** Fallback humanizer: `in_review` / `in review` -> `In Review`. */
function humanizeStatus(status: string): string {
  return status
    .split(/[\s_]+/)
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(' ');
}

/**
 * Human-readable label for a raw workflow status value.
 *
 * The backend sends the machine value (`draft`, `in_review`, `Approved`); this
 * is the only place a list or badge turns it into display text.
 */
export function getWorkflowStatusLabel(status: string): string {
  const key = status.trim().toLowerCase();
  return STATUS_LABELS[key] ?? humanizeStatus(status.trim());
}

/**
 * Lifecycle rank of a status, for "sort by status".
 *
 * Unknown states (workspace-defined ones) get a rank past every known state so
 * they collect at the end rather than interleaving arbitrarily.
 */
function statusRank(status: string): number {
  return STATUS_RANK.get(status.trim().toLowerCase()) ?? STATUS_ORDER.length;
}

/**
 * Compare two statuses by lifecycle position, then alphabetically.
 *
 * Callers still tie-break on title; this only orders the status component.
 */
export function compareWorkflowStatus(a: string, b: string): number {
  const rankDiff = statusRank(a) - statusRank(b);
  if (rankDiff !== 0) return rankDiff;
  return a.localeCompare(b);
}

export interface WorkflowStatusOption {
  value: string;
  label: string;
}

/**
 * Build the status filter options for a list of artifacts.
 *
 * Returns one option per distinct, non-empty status present in `items`, in
 * lifecycle order, with `value` as the raw API value (what the list compares
 * against) and `label` as the readable form. Deriving from the items is what
 * makes the filter correct for every entity type and every custom workflow —
 * see the module docstring.
 *
 * `activeValue` is always included even when no item carries it any more.
 * Without it the `<select>` would silently fall back to displaying its first
 * option ("All Statuses") while the filter state was still active — the list
 * would look unfiltered but render the empty "no match" state. This happens
 * whenever the last item of the filtered status leaves the set, e.g. after
 * transitioning the only `ready` item to `approved`.
 */
export function buildStatusFilterOptions(
  items: readonly { status?: string | null }[],
  activeValue?: string,
): WorkflowStatusOption[] {
  const seen = new Set<string>();
  for (const item of items) {
    const status = item.status?.trim();
    if (status) seen.add(status);
  }
  const active = activeValue?.trim();
  if (active) seen.add(active);
  return [...seen]
    .sort(compareWorkflowStatus)
    .map((value) => ({ value, label: getWorkflowStatusLabel(value) }));
}
