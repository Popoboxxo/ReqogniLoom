import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BannerStack } from "./BannerStack";
import { bannersApi } from "../../api/banners";
import { useWorkspace } from "../../context/WorkspaceContext";

vi.mock("../../api/banners", () => ({
  bannersApi: { getGlobal: vi.fn(), getWorkspace: vi.fn() },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback ?? _key }),
}));

const GLOBAL_BANNER = {
  id: "g1",
  scope: "global" as const,
  workspace_id: null,
  level: "critical" as const,
  message: "System-wide notice",
  enabled: true,
  dismissible: true,
  show_on_login_page: false,
  updated_at: "2026-08-23T00:00:00Z",
};

const WORKSPACE_BANNER = {
  id: "w1",
  scope: "workspace" as const,
  workspace_id: "ws-1",
  level: "info" as const,
  message: "Workspace notice",
  enabled: true,
  dismissible: false,
  show_on_login_page: false,
  updated_at: "2026-08-23T00:00:00Z",
};

describe("BannerStack", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    vi.mocked(useWorkspace).mockReturnValue({
      activeWorkspace: { id: "ws-1", name: "WS" },
    } as ReturnType<typeof useWorkspace>);
  });

  it("renders nothing when no banners are configured", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    render(<BannerStack />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalled());
    expect(screen.queryByTestId("banner-stack")).toBeNull();
  });

  it("renders both banners stacked, global first", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(GLOBAL_BANNER);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(WORKSPACE_BANNER);
    render(<BannerStack />);
    const stack = await screen.findByTestId("banner-stack");
    const rows = stack.querySelectorAll("[data-testid^='banner-']");
    expect(screen.getByTestId("banner-global")).toBeInTheDocument();
    expect(screen.getByTestId("banner-workspace")).toBeInTheDocument();
    expect(rows[0]).toHaveAttribute("data-testid", "banner-global");
  });

  it("does not render a dismiss button when dismissible=false", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(null);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(WORKSPACE_BANNER);
    render(<BannerStack />);
    await screen.findByTestId("banner-workspace");
    expect(screen.queryByTestId("banner-workspace-dismiss")).toBeNull();
  });

  it("dismissing a banner removes it and persists across re-render", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValue(GLOBAL_BANNER);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    // BannerStack fetches once per mount (empty-deps effect) — it is mounted
    // exactly once inside AppShell and is not remounted on route navigation.
    // RTL's `rerender()` reconciles the *same* component instance in place
    // and therefore does not re-run a mount-only effect (standard React
    // behavior, not a test-env quirk) — the real-world equivalent of "the
    // component fetches again" is a full remount (e.g. a browser reload),
    // simulated here via unmount()+render() rather than rerender().
    const { unmount } = render(<BannerStack />);
    await screen.findByTestId("banner-global");

    fireEvent.click(screen.getByTestId("banner-global-dismiss"));
    expect(screen.queryByTestId("banner-global")).toBeNull();

    unmount();
    render(<BannerStack />);
    await waitFor(() => expect(bannersApi.getGlobal).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("banner-global")).toBeNull();
  });

  it("an admin edit (new updated_at) resurfaces a previously dismissed banner", async () => {
    vi.mocked(bannersApi.getGlobal).mockResolvedValueOnce(GLOBAL_BANNER);
    vi.mocked(bannersApi.getWorkspace).mockResolvedValue(null);
    // See the unmount/remount rationale in the previous test.
    const { unmount } = render(<BannerStack />);
    await screen.findByTestId("banner-global");
    fireEvent.click(screen.getByTestId("banner-global-dismiss"));
    expect(screen.queryByTestId("banner-global")).toBeNull();

    const edited = { ...GLOBAL_BANNER, message: "Updated notice", updated_at: "2026-08-24T00:00:00Z" };
    vi.mocked(bannersApi.getGlobal).mockResolvedValueOnce(edited);
    unmount();
    render(<BannerStack />);
    await screen.findByTestId("banner-global");
    expect(screen.getByText("Updated notice")).toBeInTheDocument();
  });
});
