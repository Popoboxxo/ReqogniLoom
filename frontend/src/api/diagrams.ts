/**
 * ARCH-L1-001 ReactFrontend — Diagrams API.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L0-016 (Interaktive Diagramme und Grafiken),
 *          REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-L1-056 (Canvas), REQ-L1-057 (Mermaid)
 *
 * Wraps /api/v1/diagrams/ endpoints including Canvas strokes (IF-L1-058/060)
 * and Mermaid source/preview (IF-L1-059/061).
 */

import { apiClient, getAllPages } from "./client";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  CanvasStrokeData,
  CanvasStrokeResponse,
  Diagram,
  DiagramDetail,
  DiagramType,
  MermaidPreviewResponse,
  MermaidSourceResponse,
  PaginatedResponse,
  PayloadFormat,
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
  /**
   * Fetch all diagrams for a workspace, following pagination links until
   * exhaustion (issue #177 — this only returned the first page, capped at
   * PAGE_SIZE=25, silently hiding the rest of the diagram list). The
   * PaginatedResponse shape is preserved so existing callers reading
   * `.results` keep working unchanged.
   */
  async list(workspaceId: UUID): Promise<PaginatedResponse<Diagram>> {
    const results = await getAllPages<Diagram>("/diagrams/", {
      workspace_id: workspaceId,
    });
    return { count: results.length, next: null, previous: null, results };
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

  // -----------------------------------------------------------------------
  // Canvas Strokes — IF-L1-058 / IF-L1-060 (REQ-L1-056)
  // -----------------------------------------------------------------------

  /** GET /api/v1/diagrams/{id}/canvas-strokes/ — retrieve stroke data + SVG */
  fetchCanvasStrokes(id: UUID): Promise<CanvasStrokeResponse> {
    return apiClient.get<CanvasStrokeResponse>(
      `/diagrams/${id}/canvas-strokes/`
    );
  },

  /** POST /api/v1/diagrams/{id}/canvas-strokes/ — append strokes (auto-save) */
  appendCanvasStrokes(
    id: UUID,
    data: CanvasStrokeData
  ): Promise<CanvasStrokeResponse> {
    return apiClient.post<CanvasStrokeResponse>(
      `/diagrams/${id}/canvas-strokes/`,
      data
    );
  },

  /** PUT /api/v1/diagrams/{id}/canvas-strokes/ — replace all strokes */
  saveCanvasStrokes(
    id: UUID,
    data: CanvasStrokeData
  ): Promise<CanvasStrokeResponse> {
    return apiClient.put<CanvasStrokeResponse>(
      `/diagrams/${id}/canvas-strokes/`,
      data
    );
  },

  // -----------------------------------------------------------------------
  // Mermaid Source/Preview — IF-L1-059 / IF-L1-061 (REQ-L1-057)
  // -----------------------------------------------------------------------

  /** GET /api/v1/diagrams/{id}/mermaid-source/ — get Mermaid source code */
  fetchMermaidSource(id: UUID): Promise<MermaidSourceResponse> {
    return apiClient.get<MermaidSourceResponse>(
      `/diagrams/${id}/mermaid-source/`
    );
  },

  /** PUT /api/v1/diagrams/{id}/mermaid-source/ — update Mermaid source */
  saveMermaidSource(
    id: UUID,
    source: string
  ): Promise<MermaidSourceResponse> {
    return apiClient.put<MermaidSourceResponse>(
      `/diagrams/${id}/mermaid-source/`,
      { source }
    );
  },

  /** GET /api/v1/diagrams/{id}/mermaid-preview/ — rendered preview data */
  fetchMermaidPreview(id: UUID): Promise<MermaidPreviewResponse> {
    return apiClient.get<MermaidPreviewResponse>(
      `/diagrams/${id}/mermaid-preview/`
    );
  },

  // `getTraceability` lived here until the link-type catalog migration: it
  // filtered on a retired link-type literal that no longer exists in
  // any workspace catalog, so it could only ever have returned an empty list.
  // It had no callers in `frontend/src` — deleted rather than repaired.

  // -----------------------------------------------------------------------
  // Diff / Versions (REQ-142)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two diagram versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/diagrams/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /**
   * Version list for a diagram, backed by the immutable DiagramVersion
   * history table (REQ-142).
   */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/diagrams/${id}/versions/`);
  },
};
