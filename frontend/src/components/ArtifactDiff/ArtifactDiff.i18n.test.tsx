/**
 * ArtifactDiff i18n regression guard (Plan C T-C3-2, C-L9).
 *
 * The panel used to hardcode English chrome — `ENTITY_LABELS`, the
 * `STATUS_LABELS` badge map, the `<entity> Diff` title and the
 * `Close`/`From:`/`To:` labels — so a German workspace showed a mixed
 * language panel. The backend keeps emitting the English field values (the
 * diff payload is an API contract); the *client* translates its own chrome.
 *
 * This test uses a real i18next instance loaded with the actual locale
 * resources (the `language-mix-settings.test.ts` pattern, as in
 * `IcdView.i18n.test.tsx`). A fallback-only `react-i18next` mock would render
 * the very defaults this test guards against and pass regardless.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import de from "../../i18n/locales/de.json";
import en from "../../i18n/locales/en.json";
import type { ArtifactDiffResult, ArtifactVersion } from "../../types";
import { ArtifactDiff } from "./ArtifactDiff";

const i18n = i18next.createInstance();
void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    de: { translation: de },
  },
  lng: "de",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

const ENTITY_ID = "req-nav-001";

const VERSIONS: ArtifactVersion[] = [
  { version: 1, label: "v1", modified_at: "2026-01-10T09:00:00Z" },
  { version: 2, label: "v2", modified_at: "2026-01-20T14:00:00Z" },
];

const DIFF: ArtifactDiffResult = {
  from_version: 1,
  to_version: 2,
  entity_type: "requirement",
  fields: [
    { name: "addedField", status: "added", to: "Brand new value" },
    { name: "removedField", status: "removed", from: "Old value" },
    { name: "modifiedField", status: "modified", from: "a", to: "b" },
    { name: "unchangedField", status: "unchanged", from: "same" },
  ],
};

function renderDiff(): ReturnType<typeof render> {
  return render(
    <I18nextProvider i18n={i18n}>
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="requirement"
        currentVersion={2}
        diffFetcher={vi.fn().mockResolvedValue(DIFF)}
        versionsFetcher={vi.fn().mockResolvedValue(VERSIONS)}
        onClose={vi.fn()}
      />
    </I18nextProvider>,
  );
}

/**
 * English chrome the panel must never render in a German workspace. `" Diff"`
 * (leading space) is the shape the old hardcoded `<entity> Diff` title had.
 */
const ENGLISH_CHROME = [
  "Added",
  "Removed",
  "Modified",
  "Unchanged",
  "Close",
  "From:",
  "To:",
  " Diff",
] as const;

describe("ArtifactDiff i18n (C-L9)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("de");
  });

  it("renders no English chrome text in the German UI", async () => {
    renderDiff();

    // Wait until the field list (and therefore every status badge) is on
    // screen — asserting before that would pass on an empty panel.
    await waitFor(() => {
      expect(screen.getByTestId("diff-fields")).toBeInTheDocument();
    });
    expect(screen.getAllByTestId(/^diff-field-/).length).toBe(4);

    const text = document.body.textContent ?? "";
    const leaked = ENGLISH_CHROME.filter((needle) => text.includes(needle));
    expect(leaked, `English chrome leaked into the German UI: ${leaked.join(", ")}`).toEqual(
      [],
    );
  });

  it("renders the German title, status labels and version labels", async () => {
    renderDiff();

    await waitFor(() => {
      expect(screen.getByTestId("diff-fields")).toBeInTheDocument();
    });

    // Read expectations from the locale files, not from duplicated literals:
    // the regression is "key missing → English default leaks", and the DE
    // values must differ from the EN ones for these assertions to mean
    // anything.
    expect(de.diff.status.added).not.toBe(en.diff.status.added);
    expect(de.diff.title).not.toBe(en.diff.title);

    expect(screen.getByText(de.diff.status.added)).toBeInTheDocument();
    expect(screen.getByText(de.diff.status.removed)).toBeInTheDocument();
    expect(screen.getByText(de.diff.status.modified)).toBeInTheDocument();
    expect(screen.getByText(de.diff.status.unchanged)).toBeInTheDocument();

    const title = de.diff.title.replace(
      "{{entity}}",
      de.diff.entity.requirement,
    );
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(title);
    expect(screen.getByText(de.diff.close)).toBeInTheDocument();
    expect(screen.getByTestId("diff-from-version").closest("label")).toHaveTextContent(
      de.diff.from,
    );
    expect(screen.getByTestId("diff-to-version").closest("label")).toHaveTextContent(
      de.diff.to,
    );
  });

  it("still renders the English labels when the language is en", async () => {
    await i18n.changeLanguage("en");
    renderDiff();

    await waitFor(() => {
      expect(screen.getByTestId("diff-fields")).toBeInTheDocument();
    });

    expect(screen.getByText(en.diff.status.added)).toBeInTheDocument();
    expect(screen.getByText(en.diff.close)).toBeInTheDocument();
  });
});
