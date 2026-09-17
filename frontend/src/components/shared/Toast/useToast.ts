/**
 * ARCH-L1-001 ReactFrontend — shared transient-notification primitive (UI-51).
 *
 * leaf_id: COMP-RF-001 (shared primitives)
 * req_id:  REQ-L2-RF-030 (generic reusable frontend components)
 *
 * Four page-local toast re-implementations had converged on the same shape
 * (`useState<string | null>` + `window.setTimeout` + a `role="status"` div)
 * with three different auto-dismiss timings and, in three of them, a timer
 * that was never cleared — so a navigation away during the dismiss window
 * left a `setState` scheduled against an unmounted component (UI-38).
 *
 * This hook is that shape, once:
 *   - one canonical dismiss delay for every page,
 *   - the pending timer cancelled on re-show *and* on unmount,
 *   - `clear()` for the "a modal opened, hide the page toast" case.
 *
 * Not a global notification centre: a toast still belongs to the view that
 * raised it and is rendered by that view via `<Toast>`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Canonical auto-dismiss delay in ms. The replaced implementations used
 * 2000/3000/3000/4000; 3000 is the value three of the four already had and is
 * long enough to read a one-line confirmation.
 */
export const TOAST_DISMISS_MS = 3000;

export interface ToastController {
  /** Currently displayed message, or `null` when nothing is shown. */
  message: string | null;
  /** Shows *message* and (re)starts the auto-dismiss timer. */
  show: (message: string) => void;
  /** Hides the current message and cancels the pending timer. */
  clear: () => void;
}

export function useToast(dismissMs: number = TOAST_DISMISS_MS): ToastController {
  const [message, setMessage] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const cancelTimer = useCallback((): void => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const clear = useCallback((): void => {
    cancelTimer();
    setMessage(null);
  }, [cancelTimer]);

  const show = useCallback(
    (next: string): void => {
      cancelTimer();
      setMessage(next);
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        setMessage(null);
      }, dismissMs);
    },
    [cancelTimer, dismissMs]
  );

  // The whole point of the primitive: no timer outlives the component.
  useEffect(() => cancelTimer, [cancelTimer]);

  return { message, show, clear };
}
