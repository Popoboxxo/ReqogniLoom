import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArtifactVectorSettingsSection } from "./ArtifactVectorSettingsSection";
import { artifactVectorSettingsApi } from "../../api/system-artifact-vector-settings";
import "../../i18n/index";

vi.mock("../../api/system-artifact-vector-settings", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../api/system-artifact-vector-settings")>();
  return {
    ...actual,
    artifactVectorSettingsApi: {
      get: vi.fn(),
      update: vi.fn(),
      reset: vi.fn(),
    },
  };
});

const SETTINGS = {
  vector_backend: "qdrant",
  vector_backend_is_override: true,
  effective_vector_backend: "qdrant",
  available_backends: ["pgvector", "qdrant"],
  backends: {
    pgvector: {
      schema: [],
      values: {},
      is_override: {},
      secrets_set: {},
      capabilities: { search: true, external_store: false },
    },
    qdrant: {
      schema: [
        {
          name: "base_url",
          type: "str" as const,
          env_var: "QDRANT_BASE_URL",
          label_key: "",
          choices: [],
          min_value: null,
          max_length: null,
          default: "",
        },
      ],
      values: { base_url: "http://qdrant:6333" },
      is_override: { base_url: true },
      secrets_set: { api_key: false },
      capabilities: { search: true, external_store: true },
    },
  },
  diagnostic: { requested: "qdrant", active: "qdrant", reason: "" },
};

describe("ArtifactVectorSettingsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(artifactVectorSettingsApi.get).mockResolvedValue({ ...SETTINGS });
    vi.mocked(artifactVectorSettingsApi.update).mockResolvedValue({ ...SETTINGS });
    vi.mocked(artifactVectorSettingsApi.reset).mockResolvedValue({
      ...SETTINGS,
      vector_backend: null,
      vector_backend_is_override: false,
      effective_vector_backend: "pgvector",
    });
  });

  it("renders the selector, the schema-driven fields and the diagnostic", async () => {
    render(<ArtifactVectorSettingsSection />);

    expect(
      await screen.findByTestId("artifact-vector-settings-section")
    ).toBeInTheDocument();
    expect(screen.getByTestId("artifact-vector-settings-backend")).toHaveValue(
      "qdrant"
    );
    expect(
      screen.getByTestId("artifact-vector-settings-qdrant-base-url")
    ).toHaveValue("http://qdrant:6333");
    expect(screen.getByTestId("artifact-vector-settings-diagnostic")).toHaveTextContent(
      "qdrant"
    );
  });

  it("saves the selected backend and the staged options", async () => {
    const user = userEvent.setup();
    render(<ArtifactVectorSettingsSection />);

    const input = await screen.findByTestId(
      "artifact-vector-settings-qdrant-base-url"
    );
    await user.clear(input);
    await user.type(input, "http://other:6333");
    await user.click(screen.getByTestId("artifact-vector-settings-save"));

    await waitFor(() => {
      expect(artifactVectorSettingsApi.update).toHaveBeenCalledWith({
        vector_backend: "qdrant",
        backend_options: { qdrant: { base_url: "http://other:6333" } },
        backend_secrets: {},
      });
    });
  });

  it("clears the selector override when the env default is chosen", async () => {
    const user = userEvent.setup();
    render(<ArtifactVectorSettingsSection />);

    await screen.findByTestId("artifact-vector-settings-section");
    await user.selectOptions(
      screen.getByTestId("artifact-vector-settings-backend"),
      ""
    );
    await user.click(screen.getByTestId("artifact-vector-settings-save"));

    await waitFor(() => {
      expect(artifactVectorSettingsApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ vector_backend: null })
      );
    });
  });

  it("confirms a reset before clearing the overrides", async () => {
    const user = userEvent.setup();
    render(<ArtifactVectorSettingsSection />);

    await screen.findByTestId("artifact-vector-settings-section");
    await user.click(screen.getByTestId("artifact-vector-settings-reset"));
    expect(artifactVectorSettingsApi.reset).not.toHaveBeenCalled();

    await user.click(
      await screen.findByTestId("artifact-vector-settings-reset-confirm-confirm")
    );
    await waitFor(() => {
      expect(artifactVectorSettingsApi.reset).toHaveBeenCalled();
    });
  });

  it("offers a retry when loading fails", async () => {
    vi.mocked(artifactVectorSettingsApi.get).mockRejectedValueOnce(
      new Error("boom")
    );
    render(<ArtifactVectorSettingsSection />);

    expect(
      await screen.findByTestId("artifact-vector-settings-error")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("artifact-vector-settings-retry")
    ).toBeInTheDocument();
  });
});
