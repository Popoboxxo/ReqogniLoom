/**
 * ARCH-L1-001 ReactFrontend — Diagrams API.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L0-016 (Interaktive Diagramme und Grafiken),
 *          REQ-L2-DS-001 (DiagramService REST API)
 *
 * Wraps /api/v1/diagrams/ endpoints and the cross-tenant
 * /api/v1/trace-links/ lookup used by the traceability sidebar.
 */

import { apiClient, getList } from "./client";
import { tracelinksApi } from "./tracelinks";
import type {
  Diagram,
  DiagramDetail,
  DiagramTraceLink,
  DiagramType,
  PaginatedResponse,
  PayloadFormat,
  TraceLink,
  UUID,
} from "../types";

export interface CreateDiagramPayload {
  workspace_id: UUID;
  name: string;
  diagram_type: DiagramType;
  payload_format: PayloadFormat;
  content: string;
  description?: string;
}

export interface UpdateDiagramPayload {
  payload_format: PayloadFormat;
  content: string;
}

export const diagramsApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Diagram>> {
    return getList<Diagram>("/diagrams/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<DiagramDetail> {
    return apiClient.get<DiagramDetail>(`/diagrams/${id}/`);
  },

  create(data: CreateDiagramPayload): Promise<Diagram> {
    return apiClient.post<Diagram>("/diagrams/", data);
  },

  update(id: UUID, data: UpdateDiagramPayload): Promise<{
    version_number: number;
    payload_format: PayloadFormat;
    content: string;
  }> {
    return apiClient.patch(`/diagrams/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/diagrams/${id}/`);
  },

  /**
   * Resolve all trace links where this diagram is the source side.
   * Uses the generic tracelinks endpoint and keeps only "documents" links
   * (the only link type the DiagramService creates per IF-L1-034).
   */
  async getTraceability(
    workspaceId: UUID,
    diagramId: UUID,
    requirementsLookup: (id: UUID) => string | undefined,
    architectureLookup: (id: UUID) => string | undefined,
  ): Promise<DiagramTraceLink[]> {
    const resp = await tracelinksApi.listForArtifact(workspaceId, diagramId);
    const links: TraceLink[] = resp.results ?? [];
    return links
      .filter((link) => link.source_id === diagramId && link.link_type === "documents")
      .map((link) => {
        const title =
          requirementsLookup(link.target_id) ??
          architectureLookup(link.target_id) ??
          link.target_id;
        return {
          id: link.id,
          source_id: link.source_id,
          target_id: link.target_id,
          link_type: link.link_type,
          target_type: "Artifact",
          target_title: title,
        };
      });
  },
};
