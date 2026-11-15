/**
 * Serialized, last-click-wins preference writes (connection view V.5).
 *
 * The regression these tests pin: two rapid clicks on a switch used to fire two
 * unrelated PATCHes, so the *older* value could land last and the next reload
 * showed a state the user had already left.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { createPreferenceWriteQueue } from "./preference-write-queue";

/** A `write` whose settlement the test drives by hand, one call at a time. */
function controllableWrite(): {
  write: (value: boolean) => Promise<void>;
  calls: Array<{ value: boolean; settle: () => void; fail: (e: unknown) => void }>;
} {
  const calls: Array<{
    value: boolean;
    settle: () => void;
    fail: (e: unknown) => void;
  }> = [];
  const write = (value: boolean): Promise<void> =>
    new Promise<void>((resolve, reject) => {
      calls.push({ value, settle: resolve, fail: reject });
    });
  return { write, calls };
}

describe("createPreferenceWriteQueue", () => {
  beforeEach(() => vi.clearAllMocks());

  it("writes the first request straight away", async () => {
    const { write, calls } = controllableWrite();
    const queue = createPreferenceWriteQueue(write);

    void queue.request(false);

    expect(calls.map((call) => call.value)).toEqual([false]);
    calls[0].settle();
  });

  it("toggle_while_write_in_flight_keeps_the_last_click", async () => {
    const { write, calls } = controllableWrite();
    const queue = createPreferenceWriteQueue(write);

    const first = queue.request(false);
    // Two more clicks while the first PATCH is on the wire: only the *last*
    // one survives, and nothing is sent before the in-flight request settles.
    const superseded = queue.request(true);
    const last = queue.request(false);
    expect(calls).toHaveLength(1);

    // The superseded click is settled as fulfilled — its value never reaches
    // the wire and is not an error the UI could report.
    await expect(superseded).resolves.toBeUndefined();

    calls[0].settle();
    await first;
    // The successor is started from a `finally` chain, i.e. one microtask after
    // the caller's promise settles.
    await Promise.resolve();
    await Promise.resolve();
    // The successor starts only now, in order, carrying the newest value.
    expect(calls.map((call) => call.value)).toEqual([false, false]);

    calls[1].settle();
    await expect(last).resolves.toBeUndefined();
  });

  it("keeps two in-flight writes from overlapping", async () => {
    const { write, calls } = controllableWrite();
    const queue = createPreferenceWriteQueue(write);

    void queue.request(false);
    void queue.request(true);
    calls[0].settle();

    await Promise.resolve();
    await Promise.resolve();
    // Exactly one request existed at any moment: the second one appears only
    // after the first settled, so it cannot be overtaken on the wire.
    expect(calls.map((call) => call.value)).toEqual([false, true]);
    calls[1].settle();
  });

  it("drains a queued click even when the in-flight write fails", async () => {
    const { write, calls } = controllableWrite();
    const queue = createPreferenceWriteQueue(write);
    const failure = new Error("preference store unavailable");

    const failed = queue.request(false);
    void queue.request(true);
    calls[0].fail(failure);

    await expect(failed).rejects.toBe(failure);
    await Promise.resolve();
    await Promise.resolve();
    // The user's last click is still written; a failed predecessor must not
    // strand the queue.
    expect(calls.map((call) => call.value)).toEqual([false, true]);
    calls[1].settle();
  });

  it("accepts a new request after everything settled", async () => {
    const { write, calls } = controllableWrite();
    const queue = createPreferenceWriteQueue(write);

    void queue.request(false);
    calls[0].settle();
    await Promise.resolve();
    await Promise.resolve();

    void queue.request(true);
    expect(calls.map((call) => call.value)).toEqual([false, true]);
    calls[1].settle();
  });
});
