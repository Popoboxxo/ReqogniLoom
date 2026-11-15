/**
 * ARCH-L1-001 ReactFrontend — serialized, last-click-wins queue for preference
 * writes.
 *
 * A switch that writes its value straight from the click handler
 * (`void save(next)`) has two failure modes as soon as the user is faster than
 * the network:
 *
 * 1. **Out-of-order requests.** Two rapid clicks fire two PATCHes. Nothing
 *    orders them on the wire, so the *older* value can land last and persist a
 *    state the user has already left. The switch then disagrees with the store,
 *    and the next reload "reverts" the setting.
 * 2. **Superseded intermediate values.** The value of click n is not the user's
 *    intent once click n+1 happened — writing it widens the window in which the
 *    server holds a state nobody asked for.
 *
 * The queue keeps **at most one request on the wire and one pending value**:
 * a click during an in-flight write replaces the pending value, and that value
 * is sent once the current request settles. The last click therefore always
 * wins, and the server never sees two writes for the same key in flight at the
 * same time.
 *
 * The transport is the caller's business: this module knows nothing about
 * preferences, only about ordering a boolean stream (the connection view's two
 * display switches). Retries are deliberately *not* built in — a failed write
 * is reported to the caller, which owns the local state, exactly like before.
 */

/** One queued click: the value plus the deferred of the caller that asked. */
interface QueuedWrite {
  value: boolean;
  resolve: () => void;
  reject: (reason: unknown) => void;
}

export interface PreferenceWriteQueue {
  /**
   * Ask for `value` to be stored.
   *
   * - Resolves once a write carrying this value — or a newer click that
   *   superseded it — has been stored.
   * - Rejects when the write that carried this value failed; a request that was
   *   superseded before it reached the wire resolves instead, because there is
   *   nothing to report: the user's later click already replaced it.
   */
  request(value: boolean): Promise<void>;
}

/**
 * Create a queue around `write`.
 *
 * `write` must be an async function (`(value) => Promise<void>`): a synchronous
 * throw would leave the queue believing a write is still on the wire, so it is
 * not defended against here — every caller in this app passes a `fetch`-backed
 * helper.
 */
export function createPreferenceWriteQueue(
  write: (value: boolean) => Promise<void>
): PreferenceWriteQueue {
  /** True while one `write` is unsettled — the queue never exceeds one. */
  let onTheWire = false;
  /** Newest click that arrived while a write was already in flight. */
  let queued: QueuedWrite | null = null;

  const start = (item: QueuedWrite): void => {
    onTheWire = true;
    void write(item.value)
      .then(item.resolve, item.reject)
      .finally(() => {
        onTheWire = false;
        const next = queued;
        queued = null;
        // Drain in click order; the request that just settled can never be
        // overtaken, because the successor only starts from here.
        if (next) start(next);
      });
  };

  return {
    request(value: boolean): Promise<void> {
      return new Promise<void>((resolve, reject) => {
        if (!onTheWire) {
          start({ value, resolve, reject });
          return;
        }
        // A write is on the wire: this click is the user's latest intent, so it
        // replaces whatever was queued. The replaced click is settled as
        // fulfilled — its value is never sent and must not surface as an error.
        queued?.resolve();
        queued = { value, resolve, reject };
      });
    },
  };
}
