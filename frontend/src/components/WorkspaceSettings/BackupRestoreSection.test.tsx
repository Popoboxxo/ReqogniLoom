/**
 * BackupRestoreSection — a11y regression test (WCAG 4.1.2/3.3.2).
 *
 * GESAMTTEST_BERICHT_2026-08-21.md §5 finding 3: the backup-type <select>
 * had no accessible name (no <label htmlFor>, aria-label or
 * aria-labelledby). Verifies the field is now queryable via its accessible
 * name — a passing getByLabelText query is direct proof the label
 * association works.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BackupRestoreSection } from "./BackupRestoreSection";
import { adminOpsApi } from "../../api/admin-ops";

vi.mock("react-i18next", () => {
  const t = (_key: string, fallback?: string): string => fallback ?? _key;
  return { useTranslation: () => ({ t }) };
});

vi.mock("../../api/admin-ops", () => ({
  adminOpsApi: {
    listBackups: vi.fn(),
    createBackup: vi.fn(),
    restoreBackup: vi.fn(),
  },
  RESTORE_CONFIRMATION_TEXT: "RESTORE",
}));

describe("BackupRestoreSection — a11y (WCAG 4.1.2/3.3.2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(adminOpsApi.listBackups).mockResolvedValue([]);
  });

  it("exposes the backup-type select via its accessible name", async () => {
    render(<BackupRestoreSection />);

    const select = await screen.findByTestId("backup-type-select");
    expect(screen.getByLabelText("Backup type")).toBe(select);
  });

  it("labels the backups table and scopes every header cell (#1406 R2-08)", async () => {
    vi.mocked(adminOpsApi.listBackups).mockResolvedValue([
      {
        id: "11111111-1111-1111-1111-111111111111",
        backup_type: "full",
        status: "completed",
        file_size_bytes: 1024,
        created_at: "2026-01-01T00:00:00Z",
        is_restorable: true,
      } as never,
    ]);

    render(<BackupRestoreSection />);

    const table = await screen.findByTestId("backups-table");

    // A <caption> is the table's accessible name — an empty one would leave
    // the table unnamed, so assert real text rather than mere presence.
    const caption = table.querySelector("caption");
    expect(caption).not.toBeNull();
    expect(caption?.textContent?.trim()).not.toBe("");

    // axe `empty-table-header`: every column header must be scoped and carry
    // an accessible name (the action column's name is visually hidden).
    const headers = Array.from(table.querySelectorAll("thead th"));
    expect(headers).toHaveLength(6);
    for (const header of headers) {
      expect(header.getAttribute("scope")).toBe("col");
      expect(header.textContent?.trim()).not.toBe("");
    }
  });
});
