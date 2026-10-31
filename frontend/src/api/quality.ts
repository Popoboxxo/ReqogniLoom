/**
 * ARCH-L1-001 ReactFrontend — advisory quality assessment API (Plan B / B5-T3).
 * ADVISORY ONLY: no consumer may gate a transition on `score`.
 */
import { apiClient } from "./client";
import type { ISODateTime, UUID } from "../types";

export type QualityEntityType = "Requirement" | "Adr" | "TestCase" | "Risk";

export interface QualityAssessment {
  assessment_id: UUID;
  entity_type: QualityEntityType;
  entity_id: UUID;
  /** 0..1 — rendered as a percentage. */
  score: number;
  /** LLM output; plain text only (never HTML/Markdown). */
  reasoning: string;
  /** LLM output; plain text only. */
  suggestions: string[];
  criteria: Record<string, number>;
  prompt_slot: string;
  prompt_scope: string;
  provider: string;
  model: string;
  trigger: string;
  status: "ok" | "failed";
  cached: boolean;
  assessed_at: ISODateTime;
  /** Absent on today's wire payload; absence must never be read as stale. */
  entity_version?: number | null;
}

/** `GET .../quality/<entity_type>/<entity_id>/` body. */
export interface QualityHistory {
  assessments: QualityAssessment[];
  count: number;
  latest: QualityAssessment | null;
}

const HISTORY_LIMIT = 20;

const base = (workspaceId: UUID): string => `/workspaces/${workspaceId}/quality`;

/** Run (201) or re-use (200) an assessment. */
export function assessQuality(
  workspaceId: UUID,
  entityType: QualityEntityType,
  entityId: UUID,
  force = false
): Promise<QualityAssessment> {
  return apiClient.post<QualityAssessment>(`${base(workspaceId)}/assess/`, {
    entity_type: entityType, entity_id: entityId, force,
  });
}

/** Newest-first history for one entity (default 20 rows). */
export function getQualityHistory(
  workspaceId: UUID,
  entityType: QualityEntityType,
  entityId: UUID,
  limit = HISTORY_LIMIT
): Promise<QualityHistory> {
  return apiClient.get<QualityHistory>(
    `${base(workspaceId)}/${entityType}/${entityId}/?limit=${limit}`
  );
}

/** True for 502/503/504 (invalid output / unavailable / timeout). */
export function isLlmUnavailableError(err: unknown): boolean {
  const code = (err as { error?: { code?: string } } | null)?.error?.code;
  if (typeof code === "string") {
    return ["LLM_UNAVAILABLE", "LLM_TIMEOUT", "LLM_OUTPUT_INVALID", "SERVICE_UNAVAILABLE"].includes(code);
  }
  const status = (err as { status?: number } | null)?.status;
  return status === 502 || status === 503 || status === 504;
}
