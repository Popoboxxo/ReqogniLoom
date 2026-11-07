/**
 * P5 Task 5.4 — UI ↔ REST error parity (lock, cycle, N:1 conflict).
 *
 * The REST error envelope is `{error: {code, message, details}}`. `apiClient`
 * throws that body verbatim for non-2xx responses, so the graph can render the
 * exact code and message the server sent instead of inventing local copy.
 * Typed errors thrown by the client itself (ForbiddenError, timeouts) are
 * mapped to a code too, but the envelope's own code always wins.
 */

export interface AllocationErrorInfo {
  /** Server error code (`WORKFLOW_FROZEN`, `VALIDATION_ERROR`, `CONFLICT`, …). */
  code: string;
  /** Server message; shown verbatim. */
  message: string;
  /** HTTP status when the structure happens to carry one. */
  status?: number;
}

interface ErrorEnvelope {
  error?: {
    code?: unknown;
    message?: unknown;
  };
  status?: unknown;
  code?: unknown;
  message?: unknown;
}

/** Map any rejected allocation write to the code/message shown to the user. */
export function toAllocationError(err: unknown): AllocationErrorInfo {
  const envelope = err as ErrorEnvelope | null | undefined;

  const envelopeCode = envelope?.error?.code;
  const envelopeMessage = envelope?.error?.message;
  const status =
    typeof envelope?.status === "number" ? envelope.status : undefined;

  if (typeof envelopeCode === "string" && envelopeCode) {
    return {
      code: envelopeCode,
      message:
        typeof envelopeMessage === "string" && envelopeMessage
          ? envelopeMessage
          : envelopeCode,
      status,
    };
  }

  if (err && typeof err === "object") {
    const typed = err as { status?: unknown; code?: unknown; message?: unknown };
    const code =
      typeof typed.code === "string" && typed.code
        ? typed.code
        : typeof typed.status === "number" && typed.status === 403
          ? "PERMISSION_DENIED"
          : "UNKNOWN_ERROR";
    return {
      code,
      message:
        typeof typed.message === "string" && typed.message
          ? typed.message
          : code,
      status: typeof typed.status === "number" ? typed.status : status,
    };
  }

  return { code: "UNKNOWN_ERROR", message: String(err), status };
}
