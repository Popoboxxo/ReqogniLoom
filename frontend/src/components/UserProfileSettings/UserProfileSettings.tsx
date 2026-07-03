/**
 * ARCH-L1-001 ReactFrontend — UserProfileSettings (COMP-RF-006).
 *
 * leaf_id: COMP-RF-006
 * req_id:  REQ-L2-RF-027 (User-Profile Dialog für PAT-Verwaltung),
 *          REQ-L3-RF006-001 (Token-Liste und UI-Controls)
 *
 * Standalone, workspace-independent page for managing the authenticated
 * user's Personal Access Tokens. Deliberately outside WorkspaceSettings —
 * tokens are bound to the user, not to a workspace, and must be generatable
 * without first selecting/activating a workspace.
 */

import { useTranslation } from "react-i18next";
import { ApiKeysSection } from "./ApiKeysSection";

export default function UserProfileSettings(): JSX.Element {
  const { t } = useTranslation();

  return (
    <div data-testid="user-profile-settings" style={{ maxWidth: "640px" }}>
      <h2
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          marginBottom: "var(--space-6)",
        }}
      >
        {t("nav.profile")}
      </h2>

      <ApiKeysSection />
    </div>
  );
}
