/** FE-008 regression guard: requestSubmit() must forward the submitter. */
import { describe, expect, it } from "vitest";

describe("HTMLFormElement.requestSubmit polyfill", () => {
  it("dispatches a cancelable submit event carrying the submitter", () => {
    const form = document.createElement("form");
    const button = document.createElement("button");
    button.type = "submit";
    button.setAttribute("data-testid", "submit-button");
    form.appendChild(button);
    document.body.appendChild(form);

    let received: SubmitEvent | null = null;
    form.addEventListener("submit", (event) => {
      received = event as SubmitEvent;
    });

    form.requestSubmit(button);

    expect(received).not.toBeNull();
    expect(received?.submitter).toBe(button);
    expect(received?.bubbles).toBe(true);
    expect(received?.cancelable).toBe(true);
    form.remove();
  });

  it("still dispatches submit when no submitter is passed", () => {
    const form = document.createElement("form");
    document.body.appendChild(form);
    let submitCount = 0;
    form.addEventListener("submit", () => {
      submitCount += 1;
    });

    form.requestSubmit();

    expect(submitCount).toBe(1);
    form.remove();
  });
});
