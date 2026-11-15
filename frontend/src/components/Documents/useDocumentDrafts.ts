/**
 * ARCH-L1-001 ReactFrontend — inline edit drafts for the document reading view
 * (R5/R6, plan 2026-11-15-document-view-on-document.md).
 *
 * One hook owns every unsaved edit of one reading object, in both save modes:
 *
 * - **immediate** (`saveField`) → one `PATCH /documents/{id}/` per field with
 *   `If-Match: "<version>"`. A 412 marks exactly the field that lost the race.
 * - **batch** (`saveAll`) → one `PATCH /artifacts/bulk-update/` for the whole
 *   document. The server writes all-or-nothing, so a rejected batch leaves
 *   every draft in place and the surface can offer "reload" instead of data
 *   loss.
 *
 * The hook is deliberately not a query/mutation consumer: it holds *drafts*,
 * not server state. `version` is the only server fact it keeps, because the
 * next write must echo the version the surface has actually seen. The caller
 * learns about a successful write through `onSaved` (typically a refetch of
 * the reading object), which keeps the hook renderable in a plain component
 * test without a `QueryClient`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { documentsApi } from "../../api/documents";
import { artifactsApi, extractBulkErrors } from "../../api/artifacts";
import type { DocumentReading, UUID } from "../../types";

/** What a successful write tells the caller: which document, at which version. */
export type UpdatedDocument = { id: string; version: number };

/** Where one field's draft stands. `clean` = saved, still shown optimistically. */
export type DocumentDraftStatus =
  | "clean"
  | "dirty"
  | "saving"
  | "conflict"
  | "error";

/** How the surface saves: per field, or collected into one batch. */
export type DocumentSaveMode = "immediate" | "batch";

export interface DocumentDraft {
  field: string;
  value: unknown;
  status: DocumentDraftStatus;
  /** Server message, only set for `conflict` / `error`. */
  error?: string;
}

/**
 * `saveAll` reports this when the reading object carries no `artifact_id`:
 * the bulk endpoint keys on the backing artifact, so without one there is
 * nothing to address. The view translates it — the hook never renders text.
 */
export const MISSING_ARTIFACT = "MISSING_ARTIFACT";

export interface UseDocumentDraftsOptions {
  /** Needed for the bulk request body (`workspace_id`), not for single saves. */
  workspaceId?: UUID;
  /** Called after a successful write so the caller can refetch the reading. */
  onSaved?: (document: UpdatedDocument) => void;
}

export interface DocumentDraftsResult {
  /** Only touched fields, in reading order (never the untouched ones). */
  drafts: DocumentDraft[];
  setDraft: (field: string, value: unknown) => void;
  resetField: (field: string) => void;
  isDirty: boolean;
  saveField: (field: string) => Promise<void>;
  /** Fields currently in conflict, in reading order. */
  conflicts: string[];
  /** Number of unsaved (dirty, error or conflict) fields. */
  dirtyCount: number;
  draftFor: (field: string) => DocumentDraft | undefined;
  /** One bulk request for every unsaved field; drafts survive a rejection. */
  saveAll: () => Promise<void>;
  /** Drop every draft without a request. */
  resetAll: () => void;
  /** A single-field save or a batch is in flight. */
  saving: boolean;
  /** Batch-level message (`MISSING_ARTIFACT` or a server message). */
  saveError: string | null;
  /** The version the surface has seen — the next write echoes it. */
  version: number;
}

type DraftMap = Record<string, DocumentDraft>;

/** Compare a control's string value against a wire value (`null` ≡ empty). */
function sameValue(a: unknown, b: unknown): boolean {
  const left = a === null || a === undefined ? "" : String(a);
  const right = b === null || b === undefined ? "" : String(b);
  return left === right;
}

/**
 * Sort a draft map into reading order. Fields the server no longer reports
 * (e.g. after a reload with a changed field list) keep their relative order at
 * the end instead of disappearing — a draft is not silently droppable.
 */
function toOrderedDrafts(
  map: DraftMap,
  reading: DocumentReading
): DocumentDraft[] {
  const order = reading.fields.map((field) => field.name);
  const rank = (name: string): number => {
    const index = order.indexOf(name);
    return index === -1 ? order.length : index;
  };
  return Object.values(map).sort((a, b) => rank(a.field) - rank(b.field));
}

/**
 * Classify a rejected single-field write.
 *
 * - a lost `If-Match` precondition (`412 PRECONDITION_FAILED`, or the legacy
 *   `409 CONFLICT`) is a **conflict**: reload is the only honest next step.
 * - anything else (`409 FIELD_FROZEN`, `400` with `details[].field`, a network
 *   error) is an **error** that belongs next to the field.
 */
function classifyFieldError(
  error: unknown,
  field: string
): {
  status: "conflict" | "error";
  message?: string;
} {
  const body = error as
    | {
        error?: {
          code?: string;
          message?: string;
          details?: ReadonlyArray<{ field?: string; errors?: string[] }>;
        };
        message?: string;
      }
    | null
    | undefined;

  const code = body?.error?.code;
  const message = body?.error?.message ?? body?.message;

  if (code === "PRECONDITION_FAILED" || code === "CONFLICT") {
    return { status: "conflict", message };
  }

  // A validation rejection names the offender per field
  // (`details: [{field, errors[]}]`). That sentence is the actionable one —
  // the envelope's top-level message is only the generic "Validation failed"
  // placeholder — so it wins over the generic text.
  const details = body?.error?.details;
  if (Array.isArray(details)) {
    const match =
      details.find((detail) => detail.field === field) ??
      details.find((detail) => detail.field);
    const detailMessage = match?.errors?.[0];
    if (detailMessage) return { status: "error", message: detailMessage };
  }

  return { status: "error", message };
}

export function useDocumentDrafts(
  reading: DocumentReading,
  options: UseDocumentDraftsOptions = {}
): DocumentDraftsResult {
  const { workspaceId, onSaved } = options;

  const [drafts, setDraftsState] = useState<DraftMap>({});
  const [version, setVersion] = useState<number>(reading.version);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Async save paths read the current drafts/version without re-creating the
  // callbacks on every keystroke (and without stale closures).
  const draftsRef = useRef<DraftMap>(drafts);
  const versionRef = useRef<number>(version);
  const readingRef = useRef<DocumentReading>(reading);
  readingRef.current = reading;

  const commit = useCallback((next: DraftMap) => {
    draftsRef.current = next;
    setDraftsState(next);
  }, []);

  const commitVersion = useCallback((next: number) => {
    versionRef.current = next;
    setVersion(next);
  }, []);

  // A different document is a different draft set: never let one document's
  // unsaved edit travel into another one's request body.
  const previousId = useRef(reading.id);
  useEffect(() => {
    if (previousId.current === reading.id) return;
    previousId.current = reading.id;
    commit({});
    setSaveError(null);
  }, [reading.id, commit]);

  // The reading object is refetched after a save (or after "reload"): adopt
  // the server's version so the *next* write carries a valid precondition.
  useEffect(() => {
    commitVersion(reading.version);
  }, [reading.id, reading.version, commitVersion]);

  const setDraft = useCallback(
    (field: string, value: unknown) => {
      const current = draftsRef.current;
      const meta = readingRef.current.fields.find((f) => f.name === field);
      if (!meta || !meta.editable) return;

      // Typing a value back to what the server has is not a change.
      if (sameValue(meta.value, value)) {
        if (!(field in current)) return;
        const next = { ...current };
        delete next[field];
        commit(next);
        return;
      }

      commit({
        ...current,
        [field]: {
          field,
          value,
          // Re-editing a conflicted or rejected field starts a fresh attempt;
          // the old server message no longer describes the new value.
          status: "dirty",
        },
      });
    },
    [commit]
  );

  const resetField = useCallback(
    (field: string) => {
      if (!(field in draftsRef.current)) return;
      const next = { ...draftsRef.current };
      delete next[field];
      commit(next);
    },
    [commit]
  );

  const resetAll = useCallback(() => {
    commit({});
    setSaveError(null);
  }, [commit]);

  const saveField = useCallback(
    async (field: string) => {
      const draft = draftsRef.current[field];
      if (!draft || draft.status === "saving") return;
      const meta = readingRef.current.fields.find((f) => f.name === field);
      if (!meta || !meta.editable) return;

      setSaveError(null);
      commit({
        ...draftsRef.current,
        [field]: { ...draft, status: "saving", error: undefined },
      });
      setSaving(true);
      try {
        const updated = await documentsApi.updateField(
          readingRef.current.id,
          field,
          draft.value,
          versionRef.current
        );
        // Keep the saved value with `clean` status: the input must show what
        // the server now stores, not the stale reading prop, while
        // `isDirty`/`dirtyCount` ignore it.
        commit({
          ...draftsRef.current,
          [field]: { field, value: draft.value, status: "clean" },
        });
        commitVersion(updated.version);
        onSaved?.(updated);
      } catch (error) {
        const { status, message } = classifyFieldError(error, field);
        commit({
          ...draftsRef.current,
          [field]: { ...draft, status, error: message },
        });
      } finally {
        setSaving(false);
      }
    },
    [commit, commitVersion, onSaved]
  );

  const saveAll = useCallback(async () => {
    const pending = Object.values(draftsRef.current).filter(
      (draft) => draft.status !== "clean" && draft.status !== "saving"
    );
    if (pending.length === 0) return;

    const artifactId = readingRef.current.artifact_id;
    if (!artifactId) {
      setSaveError(MISSING_ARTIFACT);
      return;
    }

    setSaveError(null);
    setSaving(true);
    const fields = pending.reduce<Record<string, unknown>>((acc, draft) => {
      acc[draft.field] = draft.value;
      return acc;
    }, {});

    try {
      const result = await artifactsApi.bulkUpdate(workspaceId as UUID, [
        {
          artifact_id: artifactId,
          expected_version: versionRef.current,
          fields,
        },
      ]);

      const errors = result.errors ?? [];
      if (errors.length > 0) {
        applyBulkErrors(errors, pending);
        return;
      }

      // Whole batch written: every pending draft is now what the server has.
      const next: DraftMap = { ...draftsRef.current };
      for (const draft of pending) {
        next[draft.field] = { ...draft, status: "clean", error: undefined };
      }
      commit(next);

      const updated = result.updated?.find(
        (entry) => entry.artifact_id === artifactId
      );
      if (updated) {
        commitVersion(updated.version);
        onSaved?.({
          id: readingRef.current.id,
          version: updated.version,
        });
      }
    } catch (error) {
      const errors = extractBulkErrors(error);
      applyBulkErrors(errors, pending);
    } finally {
      setSaving(false);
    }

    /**
     * Map a rejected batch back onto the drafts. Two shapes matter:
     *
     * - an entry naming a `field` → that field is marked `error` with the
     *   server message (the batch is rolled back, so it is still unsaved);
     * - an entry without a field, or no entries at all → every pending field
     *   of this artifact is a `conflict`: the batch failed for the artifact as
     *   a whole (typically a stale `expected_version`), so none of them may
     *   claim to be valid. Drafts are never cleared here.
     */
    function applyBulkErrors(
      errors: ReturnType<typeof extractBulkErrors>,
      stillPending: DocumentDraft[]
    ): void {
      const byField = new Map<string, string>();
      let artifactMessage: string | null = null;

      for (const entry of errors) {
        if (entry.field) {
          byField.set(entry.field, entry.message);
        } else {
          artifactMessage = entry.message || artifactMessage;
        }
      }

      const next: DraftMap = { ...draftsRef.current };
      for (const draft of stillPending) {
        const fieldMessage = byField.get(draft.field);
        if (fieldMessage !== undefined) {
          next[draft.field] = { ...draft, status: "error", error: fieldMessage };
          continue;
        }
        if (artifactMessage !== null) {
          next[draft.field] = {
            ...draft,
            status: "conflict",
            error: artifactMessage,
          };
        }
      }
      commit(next);
      if (artifactMessage !== null) setSaveError(artifactMessage);
      else if (errors.length > 0) setSaveError(errors[0].message);
      else setSaveError(null);
    }
  }, [commit, commitVersion, onSaved, workspaceId]);

  const orderedDrafts = toOrderedDrafts(drafts, reading);
  const dirty = orderedDrafts.filter((draft) => draft.status !== "clean");

  const draftFor = useCallback((field: string) => drafts[field], [drafts]);

  return {
    drafts: orderedDrafts,
    setDraft,
    resetField,
    isDirty: dirty.length > 0,
    saveField,
    conflicts: dirty
      .filter((draft) => draft.status === "conflict")
      .map((draft) => draft.field),
    dirtyCount: dirty.length,
    draftFor,
    saveAll,
    resetAll,
    saving,
    saveError,
    version,
  };
}
