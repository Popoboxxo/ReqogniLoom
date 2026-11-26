import { describe, expect, it } from "vitest";
import de from "../../i18n/locales/de.json";
import en from "../../i18n/locales/en.json";
import {
  DEFAULT_ENTITY_TYPE,
  WORKFLOW_ENTITY_TYPES,
  WORKFLOW_PRESETS,
  defaultWorkflowPreset,
  entityTypeFromSlug,
  entityTypeLabel,
  isWorkflowPresetForEntity,
  workflowPresetTier,
  workflowPresetsForEntity,
} from "./constants";

describe("workflow entity roster", () => {
  it("includes Document and WorkItem without dropping the existing types", () => {
    expect(WORKFLOW_ENTITY_TYPES.map((entry) => entry.type)).toEqual([
      "Requirement",
      "StakeholderNeed",
      "ArchitectureElement",
      "Adr",
      "Risk",
      "TestCase",
      "Issue",
      "Goal",
      "MainGoal",
      "Document",
      "WorkItem",
    ]);
    expect(DEFAULT_ENTITY_TYPE).toBe("Requirement");
  });

  it("resolves canonical slugs case-insensitively and rejects unknown slugs", () => {
    expect(entityTypeFromSlug("document")).toBe("Document");
    expect(entityTypeFromSlug("WORKITEM")).toBe("WorkItem");
    expect(entityTypeFromSlug("requirement")).toBe("Requirement");
    expect(entityTypeFromSlug("not-a-workflow-type")).toBeNull();
    expect(entityTypeFromSlug(undefined)).toBeNull();
  });

  it("provides labels for every roster entry in both locales", () => {
    for (const { type } of WORKFLOW_ENTITY_TYPES) {
      expect(entityTypeLabel(type).length).toBeGreaterThan(0);
      expect(de.workflow.entityTypes).toHaveProperty(type);
      expect(en.workflow.entityTypes).toHaveProperty(type);
    }
    expect(entityTypeLabel("Document")).toBe("Document");
    expect(entityTypeLabel("WorkItem")).toBe("Work Item");
  });
});

describe("entity-dependent global workflow presets", () => {
  it("offers only document_default for Document", () => {
    expect(workflowPresetsForEntity("Document")).toEqual(["document_default"]);
    expect(defaultWorkflowPreset("Document", "extended")).toBe("document_default");
    expect(isWorkflowPresetForEntity("Document", "document_default")).toBe(true);
    for (const preset of WORKFLOW_PRESETS) {
      expect(isWorkflowPresetForEntity("Document", preset)).toBe(false);
    }
  });

  it("maps Requirement one-to-one to the rigor tiers", () => {
    expect(workflowPresetsForEntity("Requirement")).toEqual(WORKFLOW_PRESETS);
    expect(defaultWorkflowPreset("Requirement", "minimal")).toBe("minimal");
    expect(defaultWorkflowPreset("Requirement", "extended")).toBe("extended");
  });

  it("prefixes every WorkItem preset with work_item_", () => {
    expect(workflowPresetsForEntity("WorkItem")).toEqual([
      "work_item_minimal",
      "work_item_standard",
      "work_item_extended",
    ]);
    expect(defaultWorkflowPreset("WorkItem", "standard")).toBe(
      "work_item_standard"
    );
    expect(isWorkflowPresetForEntity("WorkItem", "standard")).toBe(false);
    expect(isWorkflowPresetForEntity("WorkItem", "work_item_extended")).toBe(true);
  });

  it.each([
    ["StakeholderNeed", "need_default"],
    ["ArchitectureElement", "architecture_default"],
    ["Adr", "adr_default"],
    ["Risk", "risk_default"],
    ["TestCase", "testcase_default"],
    ["Issue", "issue_default"],
    ["Goal", "goal_default"],
    ["MainGoal", "main_goal_default"],
  ] as const)("keeps the canonical fixed preset for %s", (type, preset) => {
    expect(workflowPresetsForEntity(type)).toEqual([preset]);
    expect(defaultWorkflowPreset(type)).toBe(preset);
  });

  it("recovers the rigor tier from Requirement and WorkItem preset keys", () => {
    expect(workflowPresetTier("minimal")).toBe("minimal");
    expect(workflowPresetTier("work_item_extended")).toBe("extended");
    expect(workflowPresetTier("document_default")).toBeNull();
    expect(workflowPresetTier("need_default")).toBeNull();
  });
});
