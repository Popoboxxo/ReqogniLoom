/**
 * ARCH-L1-001 ReactFrontend — BannerStack (System & Workspace Banners).
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L1-081-THEME sibling feature — System & Workspace Banners
 *
 * Renders 0-2 stacked rows: the tenant's global banner (if enabled) above
 * the active workspace's banner (if enabled). Each dismissible row's
 * closed state lives in sessionStorage, keyed by
 * `banner-dismissed-<scope>-<id>-<updated_at>` — session-scoped so it
 * resets on next login, and an admin edit (new updated_at) always
 * invalidates a prior dismissal.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import { bannersApi, type Banner } from "../../api/banners";
import { useWorkspace } from "../../context/WorkspaceContext";
import styles from "./BannerStack.module.css";

function dismissKey(scope: string, banner: Banner): string {
  return `banner-dismissed-${scope}-${banner.id}-${banner.updated_at ?? ""}`;
}

function isDismissed(scope: string, banner: Banner): boolean {
  return window.sessionStorage.getItem(dismissKey(scope, banner)) === "1";
}

function BannerRow({
  scope,
  banner,
  onDismiss,
}: {
  scope: "global" | "workspace";
  banner: Banner;
  onDismiss: () => void;
}): JSX.Element {
  const { t } = useTranslation();

  const handleDismiss = (): void => {
    window.sessionStorage.setItem(dismissKey(scope, banner), "1");
    onDismiss();
  };

  return (
    <div
      className={styles.row}
      data-level={banner.level}
      data-testid={`banner-${scope}`}
      role="status"
    >
      <div className={styles.body}>
        <ReactMarkdown>{banner.message}</ReactMarkdown>
      </div>
      {banner.dismissible && (
        <button
          type="button"
          className={styles.dismissButton}
          data-testid={`banner-${scope}-dismiss`}
          aria-label={t("banners.dismiss", "Dismiss")}
          onClick={handleDismiss}
        >
          ×
        </button>
      )}
    </div>
  );
}

export function BannerStack(): JSX.Element | null {
  const { activeWorkspace } = useWorkspace();
  const [globalBanner, setGlobalBanner] = useState<Banner | null>(null);
  const [workspaceBanner, setWorkspaceBanner] = useState<Banner | null>(null);
  const [globalDismissed, setGlobalDismissed] = useState(false);
  const [workspaceDismissed, setWorkspaceDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void bannersApi
      .getGlobal()
      .then((banner) => {
        if (cancelled) return;
        setGlobalBanner(banner);
        setGlobalDismissed(banner ? isDismissed("global", banner) : false);
      })
      .catch(() => {
        // A failed fetch must never block the app shell from rendering.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!activeWorkspace?.id) {
      setWorkspaceBanner(null);
      return undefined;
    }
    void bannersApi
      .getWorkspace(activeWorkspace.id)
      .then((banner) => {
        if (cancelled) return;
        setWorkspaceBanner(banner);
        setWorkspaceDismissed(banner ? isDismissed("workspace", banner) : false);
      })
      .catch(() => {
        // Same non-blocking contract as the global fetch above.
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace?.id]);

  const showGlobal = globalBanner?.enabled && !globalDismissed;
  const showWorkspace = workspaceBanner?.enabled && !workspaceDismissed;

  if (!showGlobal && !showWorkspace) return null;

  return (
    <div data-testid="banner-stack">
      {showGlobal && globalBanner && (
        <BannerRow
          scope="global"
          banner={globalBanner}
          onDismiss={() => setGlobalDismissed(true)}
        />
      )}
      {showWorkspace && workspaceBanner && (
        <BannerRow
          scope="workspace"
          banner={workspaceBanner}
          onDismiss={() => setWorkspaceDismissed(true)}
        />
      )}
    </div>
  );
}
