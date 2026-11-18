/**
 * Structured action state for the definition-driven artifact form
 * (R2F-002 — "boolean trap" correction).
 *
 * The action area used to receive 23 flat props, eight of them booleans. Two
 * of those booleans are genuinely dependent (`changeReason.invalid` only means
 * something when `changeReason.needed` is true; `deprecate.missing` and
 * `deprecate.confirm` only mean something when `deprecate.needed` is true), and
 * the "invalid" combination `changeReasonNeeded && confirmDeprecate` is
 * REACHABLE: an edit under a mandatory-change-reason policy can still have the
 * deprecate confirmation open. A discriminated `mode` union would make that
 * valid state unrepresentable, so we deliberately keep ONE object with all
 * four groups present at all times.
 *
 * Grouping makes the dependencies explicit without forbidding concurrency:
 * ``changeReason.invalid`` lives next to ``changeReason.needed``, and the
 * deprecate flags live together. The nested groups are all *required*, so a
 * caller cannot silently omit one (see the compile-time probe at the bottom).
 */

import type { RefObject } from "react";

import type { WorkflowAllowedTransition } from "../../../api/workflow-transitions";

export interface ArtifactFormActionState {
  /** Form-wide flags that are not tied to one action. */
  common: {
    isReadOnly: boolean;
    saving: boolean;
    missingCreateValue: boolean;
  };
  /** Create-mode presentation inputs (the save label and the required hint). */
  create: {
    artifactId: string | null;
    saveTestId: string;
    missingCreateLabels: readonly string[];
  };
  /**
   * The mandatory-change-reason field. `invalid` is nested here on purpose:
   * its meaning depends on `needed`, so the two travel together. `invalid` and
   * `deprecate.confirm` may be true at the same time — that is a valid state.
   */
  changeReason: {
    needed: boolean;
    value: string;
    invalid: boolean;
    ref: RefObject<HTMLInputElement | null>;
    errorId: string;
    onChange: (value: string) => void;
  };
  /** Deprecate flow, including the optional confirmation dialog. */
  deprecate: {
    needed: boolean;
    missing: boolean;
    confirm: boolean;
    value: string;
    transition: WorkflowAllowedTransition | undefined;
    onDeprecate?: (targetState: string, changeReason?: string) => Promise<void>;
    onRequest: () => void;
    onCancel: () => void;
    onChangeReason: (value: string) => void;
    onConfirm: () => Promise<void>;
  };
}

/** Short alias used by the component and its tests. */
export type ActionState = ArtifactFormActionState;

/**
 * Compile-time contract probe (R2F-002 regression (a)).
 *
 * A class that omits the `deprecate` group cannot implement the interface, so
 * `@ts-expect-error` is required here. If a group is ever made optional or
 * removed from `ArtifactFormActionState`, the directive becomes unused and
 * `tsc` fails with TS2578 — the build itself guards the contract. `declare`
 * emits no runtime code.
 */
// @ts-expect-error - omitting a nested group of `ActionState` must not compile
export declare class MissingDeprecateGroupProbe implements ArtifactFormActionState {
  common: ArtifactFormActionState["common"];
  create: ArtifactFormActionState["create"];
  changeReason: ArtifactFormActionState["changeReason"];
}
