/**
 * VersionPanel creation-baseline i18n (Plan C T-C3-2, issue #272).
 *
 * The synthetic version-0 row's `label` is an English API field
 * ("Creation baseline"). The panel must localise it from the additive
 * `is_creation_baseline` flag instead of rendering the backend string, so a
 * German workspace does not show one English row above an otherwise German
 * version list.
 *
 * Real i18next instance (same technique as `ArtifactDiff.i18n.test.tsx`) —
 * a fallback-only mock would resolve the key to its own default and hide a
 * missing locale entry.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import de from "../../../i18n/locales/de.json";
import en from "../../../i18n/locales/en.json";
import type { ArtifactVersion } from "../../../types";
import * as diagramsModule from "../../../api/diagrams";
import { VersionPanel } from "./VersionPanel";

vi.mock("../../../api/diagrams");

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

const ARTIFACT_ID = "33333333-3333-3333-3333-333333333333";

const VERSIONS: ArtifactVersion[] = [
  {
    version: 0,
    label: "Creation baseline",
    modified_at: null,
    content_available: false,
    is_creation_baseline: true,
  },
  { version: 7, label: "Current", modified_at: "2026-01-02T00:00:00Z" },
];

function renderPanel(): ReturnType<typeof render> {
  return render(
    <I18nextProvider i18n={i18n}>
      <VersionPanel
        kind="diagram"
        artifactId={ARTIFACT_ID}
        currentVersion={{ version: 7, label: "Current", createdAt: null, baselineIds: [] }}
        onSwitch={vi.fn()}
        onCompare={vi.fn()}
      />
    </I18nextProvider>,
  );
}

describe("VersionPanel creation baseline i18n (#272)", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    vi.mocked(diagramsModule.diagramsApi.versions).mockResolvedValue(VERSIONS);
    await i18n.changeLanguage("de");
  });

  it("localises the creation-baseline label from is_creation_baseline", async () => {
    expect(de.sidebar.version.creationBaseline).not.toBe(
      en.sidebar.version.creationBaseline,
    );

    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId("version-row-0")).toBeInTheDocument();
    });

    const row = screen.getByTestId("version-row-0");
    expect(row).toHaveTextContent(de.sidebar.version.creationBaseline);
    expect(row).not.toHaveTextContent("Creation baseline");
  });

  it("renders the English creation-baseline label when language is en", async () => {
    await i18n.changeLanguage("en");
    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId("version-row-0")).toBeInTheDocument();
    });

    expect(screen.getByTestId("version-row-0")).toHaveTextContent(
      en.sidebar.version.creationBaseline,
    );
  });
});
