/**
 * One resolver for the create/edit field contract — GitHub #1393 (required)
 * and #1392 (server length limits).
 *
 * WHAT WAS BROKEN
 * ---------------
 * `ArtifactForm` renders required markers and `maxLength` from the resolved
 * attribute definition. Nine of the eleven artifact routes do not use it: their
 * create dialogs are hand-written, so a field's requiredness was whatever the
 * dialog hardcoded (nothing, in nine of them) and its length limit was nothing
 * at all — the user could type 400 characters into a 200-character ADR title
 * and only learn about it from a 400 whose reason the dialog then dropped.
 *
 * WHY A HOOK AND NOT A CONSTANT
 * -----------------------------
 * Both facts are already published by the server and both are *configurable per
 * workspace*, so any client-side copy would drift:
 *
 * | Fact | Authority | Route |
 * |------|-----------|-------|
 * | required (create) | create-form definition | `GET …/create-form-config/?resolve=effective` (#1263) |
 * | required (fallback) | attribute definition | `GET /workspaces/<id>/attribute-defaults/<type>/` |
 * | maxLength | attribute definition `validation.length` | same |
 *
 * Precedence follows the #1263 contract: the create-form definition is the
 * authority for `required` **where it resolves**; when it degrades (the hook's
 * documented `entries === null` path: unknown item type, no workspace, failed
 * request) the attribute definition answers, which is exactly the pre-#1263
 * behaviour. `maxLength` is never the form definition's business — it belongs
 * to the attribute, so it is always read from the definition.
 *
 * `staticContracts` covers item types with NO attribute definition at all —
 * `Diagram` is not an `ITEM_TYPES` member (it has no artifact lineage), so its
 * dialog declares its contract here instead of hand-writing `required` on the
 * input. It is a fallback, never an override.
 */

import { useCallback, useMemo } from "react";

import type { AttributeItemType } from "../api/attribute-definitions";
// Direct module import, not the `ArtifactForm` barrel: a create dialog must not
// pull the whole form renderer (and its field registry) into its module graph
// just to read the definition. Same reason the required predicate is imported
// from `utils/attributeRequired` rather than from `fields/FieldShell`: one
// definition, two callers (GitHub #1393 review finding M2).
import { useArtifactDefinition } from "../components/shared/ArtifactForm/useArtifactDefinition";
import { isEffectiveRequired } from "../utils/attributeRequired";
import { useCreateFormFields } from "./useCreateFormFields";

/** What one field is: its requiredness and, when bounded, its server length cap. */
export interface FieldContract {
  required: boolean;
  /** `validation.length` of the attribute definition, when the server publishes one. */
  maxLength?: number;
}

/** Exactly the DOM props a raw control needs to honour the contract. */
export interface FieldContractControlProps {
  /** Native constraint validation + `:required` styling; mirrors `aria-required`. */
  required?: true;
  "aria-required"?: true;
  maxLength?: number;
}

/**
 * Props for a `<select>`: the same required semantics, but NO `maxLength` —
 * `maxlength` is not a valid attribute on a select (React would ignore it
 * today and a future enum with `validation.length` would silently produce an
 * invalid prop).
 */
export interface FieldContractSelectProps {
  required?: true;
  "aria-required"?: true;
}

export interface FieldContractBinding extends FieldContract {
  /** Spread onto a text control: `<input {...title.controlProps} />`. */
  controlProps: FieldContractControlProps;
  /** Spread onto a `<select {...title.selectProps} />`. */
  selectProps: FieldContractSelectProps;
}

export interface UseFieldContractOptions {
  /**
   * Only fetch while the dialog is open. The dialogs are always mounted (they
   * render `null` when closed), so without this every route load would pull a
   * definition it may never show.
   */
  enabled?: boolean;
  /**
   * Contract for item types the attribute catalogue does not cover
   * (`Diagram`). Used only when neither server source resolves the field.
   */
  staticContracts?: Readonly<Record<string, FieldContract>>;
}

export interface UseFieldContractResult {
  /** Resolve one field. Stable across renders, safe to call in JSX. */
  field: (fieldKey: string) => FieldContractBinding;
}

const EMPTY: FieldContract = { required: false };

function binding(contract: FieldContract): FieldContractBinding {
  const requiredProps = {
    required: contract.required ? (true as const) : undefined,
    "aria-required": contract.required ? (true as const) : undefined,
  };
  return {
    required: contract.required,
    maxLength: contract.maxLength,
    controlProps: { ...requiredProps, maxLength: contract.maxLength },
    // No `maxLength` here — see FieldContractSelectProps.
    selectProps: requiredProps,
  };
}

export function useFieldContract(
  itemType: AttributeItemType | null,
  options: UseFieldContractOptions = {}
): UseFieldContractResult {
  const { enabled = true, staticContracts } = options;
  const active = enabled && itemType !== null;

  const { definition } = useArtifactDefinition(itemType, { enabled: active });
  const { entries } = useCreateFormFields(itemType ?? "", active);

  const attributes = useMemo(() => {
    const map = new Map<string, FieldContract>();
    // `Array.isArray` rather than `?? []`: a definition mocked or degraded to a
    // partial payload must make the dialog fall back to "no contract", never
    // throw while the user is typing.
    for (const attribute of Array.isArray(definition?.attributes) ? definition.attributes : []) {
      map.set(attribute.name, {
        // The shared predicate (GitHub #1193): `required` plus the #1192
        // approval-gate overlay. The resolved-definition payload does not emit
        // `is_required` today, so the second operand only bites when an
        // overlay supplies it.
        required: isEffectiveRequired(attribute),
        maxLength: attribute.validation?.length,
      });
    }
    return map;
  }, [definition]);

  const formDefinition = useMemo(() => {
    // `null` is the documented "could not resolve, use the attribute
    // definition" state; anything that is not an array is treated the same way.
    if (!Array.isArray(entries)) return null;
    const map = new Map<string, boolean>();
    for (const entry of entries) map.set(entry.field_key, entry.required);
    return map;
  }, [entries]);

  const field = useCallback(
    (fieldKey: string): FieldContractBinding => {
      const fromDefinition = attributes.get(fieldKey);
      const fromFormDefinition = formDefinition?.get(fieldKey);
      const fromStatic = staticContracts?.[fieldKey];

      // #1263 contract: the form definition wins for `required` when it
      // resolved. A field the form definition dropped entirely keeps the
      // attribute's own flag — removing a field from the dialog is a visibility
      // decision, not a "no longer required" one.
      const required =
        fromFormDefinition ?? fromDefinition?.required ?? fromStatic?.required ?? EMPTY.required;

      return binding({
        required,
        // Length is an attribute-level fact; there is no form-definition
        // equivalent, so it is never overridden.
        maxLength: fromDefinition?.maxLength ?? fromStatic?.maxLength,
      });
    },
    [attributes, formDefinition, staticContracts]
  );

  // No `loading` flag on purpose: every consumer renders the dialog's controls
  // immediately and the contract's sources are additive (before the server
  // answers, `field()` falls back to `staticContracts`, then to
  // `required: false` / no `maxLength` — the pre-#1393 behaviour). A flag
  // nothing reads would only invite a "flash a spinner" branch that never
  // needed to exist.
  return { field };
}
