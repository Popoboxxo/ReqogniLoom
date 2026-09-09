/**
 * Task 27 — the legacy field-configuration surface must stay gone.
 *
 * The `AttributeVisibilityConfig` / `CustomFieldDefinition` mechanism and its
 * REST endpoints were retired in Task 9; every item type renders its fields
 * from a resolved `AttributeDefinition` through `ArtifactForm` (Tasks 19-25)
 * and admins edit those definitions in `AttributeEditorPage` (Task 26). This
 * guard fails if any module reintroduces a caller of the removed API wrappers
 * or re-imports one of the deleted components — the kind of dangling reference
 * `tsc --noEmit` catches but the frontend CI job never runs.
 *
 * NOTE: `CustomFieldsEditor` is deliberately NOT listed here. It edits the
 * artifact's own free-form `custom_fields` JSON map (a live column, saved
 * through the normal PATCH) and is a supported sibling of the Requirement /
 * StakeholderNeed / TestCase artifact forms. It has nothing to do with the
 * removed `CustomFieldDefinition` mechanism despite the similar name.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "..");
const SELF = resolve(__filename);

function collect(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...collect(full));
    else if (/\.tsx?$/.test(entry) && full !== SELF) out.push(full);
  }
  return out;
}

/** Files (relative to src/) whose source contains any of `needles`. */
function offenders(files: string[], needles: string[]): string[] {
  return files
    .filter((file) => {
      const source = readFileSync(file, "utf-8");
      return needles.some((needle) => source.includes(needle));
    })
    .map((file) => file.slice(SRC.length + 1).replace(/\\/g, "/"));
}

describe("legacy field-config surface is gone", () => {
  const files = collect(SRC);

  it("has no module referencing the removed API wrappers", () => {
    expect(
      offenders(files, [
        "attributeVisibilityApi",
        "customFieldsApi",
        "AttributeVisibilityConfig",
      ])
    ).toEqual([]);
  });

  it("has no module referencing the removed configuration components", () => {
    expect(
      offenders(files, [
        "AttributeVisibilityAdmin",
        "ArtifactCustomFields",
        "CustomFieldsSection",
        "CustomFieldsDisplay",
      ])
    ).toEqual([]);
  });

  it("has no module still importing a deleted artifact form", () => {
    const deleted = [
      "RiskForm",
      "IssueForm",
      "AdrForm",
      "TestCaseForm",
      "NeedForm",
      "ArchitectureForm",
      "RequirementForm",
    ];
    const hits = files.filter((file) => {
      const source = readFileSync(file, "utf-8");
      return deleted.some((name) =>
        new RegExp(`from ['"][^'"]*/${name}['"]`).test(source)
      );
    });
    expect(hits).toEqual([]);
  });
});
