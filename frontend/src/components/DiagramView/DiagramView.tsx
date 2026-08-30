/**
 * ARCH-L1-001 ReactFrontend — DiagramView (COMP-RF-005) — Container.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L0-016 (Interaktive Diagramme und Grafiken),
 *          REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-002 (Split-View Layout),
 *          REQ-L1-095 (ArtifactInspector adoption),
 *          REQ-050 (Container/Presenter decomposition)
 *
 * Split-View container (list left, create form / detail right). Data-fetching
 * lives in useDiagramList (TanStack Query); the create form and detail view
 * are the DiagramCreateForm / DiagramDetailView presenters.
 */

import { useCallback, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { Dialog } from "../shared/Dialog";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { DiagramCreateForm } from "./DiagramCreateForm";
import { DiagramDetailView } from "./DiagramDetailView";
import { DiagramList } from "./DiagramList";
import { useDiagramList } from "./useDiagramData";
import { extractErrorMessage } from "../../api/client";

export default function DiagramView(): JSX.Element {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { items, isLoading, refresh, deleteDiagram } = useDiagramList();
  const [showCreate, setShowCreate] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // UI-20: unified on the shared ConfirmDialog instead of window.confirm.
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  // F-08 (Dialog migration): without this, Dialog's focus trap would default
  // to its own × close button on open — point it at the name field instead.
  const diagramNameInputRef = useRef<HTMLInputElement | null>(null);

  const handleDelete = useCallback(
    async (diagramId: string): Promise<void> => {
      try {
        setDeleteError(null);
        await deleteDiagram(diagramId);
        if (diagramId === id) navigate("/diagrams");
      } catch (err) {
        console.error("Failed to delete diagram", err);
        setDeleteError(extractErrorMessage(err) || t("diagrams.deleteFailed", "Failed to delete diagram."));
      }
    },
    [id, deleteDiagram, navigate, t],
  );

  const confirmDelete = useCallback((): void => {
    if (!pendingDeleteId) return;
    const diagramId = pendingDeleteId;
    setPendingDeleteId(null);
    void handleDelete(diagramId);
  }, [pendingDeleteId, handleDelete]);

  if (isLoading) {
    return <p role="status">{t("loading", "Loading...")}</p>;
  }

  const openCreateForm = (): void => setShowCreate(true);

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action
          — replaces the bare <h3>({count}) header that used to live inline
          in the left panel. */}
      <PageHeader
        title={t("diagrams.title", "Diagrams")}
        summary={t("diagrams.summary", { count: items.length })}
        primaryAction={{
          label: t("diagrams.create", "New Diagram"),
          prefixWithPlus: true,
          onClick: openCreateForm,
          testId: "create-diagram-btn",
        }}
      />

      {deleteError && (
        <p
          role="alert"
          data-testid="diagrams-delete-error"
          style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", margin: "0 0 var(--space-4)" }}
        >
          {deleteError}
        </p>
      )}

      <div style={{ flex: "1 1 auto", minHeight: 0 }}>
      <SplitView
        moduleType="diagrams"
        leftMinWidth={280}
        leftPanel={
          <DiagramList
            items={items}
            selectedId={!showCreate ? id : undefined}
            onSelect={(item) => {
              setShowCreate(false);
              navigate(`/diagrams/${item.id}`);
            }}
            onCreateNew={openCreateForm}
            onDelete={(diagramId) => setPendingDeleteId(diagramId)}
          />
        }
        rightPanel={
          showCreate ? (
          // F-08 (Dialog migration): wrapped in the shared Dialog primitive
          // (GESAMTTEST_BERICHT 2026-08-21 §5 finding 8); form markup unchanged.
          <Dialog
            title={t("diagrams.create", "New Diagram")}
            onClose={() => setShowCreate(false)}
            initialFocusRef={diagramNameInputRef}
            size="lg"
            testId="create-diagram-dialog"
          >
          <DiagramCreateForm
            onCreated={async (newId) => {
              setShowCreate(false);
              await refresh();
              navigate(`/diagrams/${newId}`);
            }}
            onCancel={() => setShowCreate(false)}
            nameInputRef={diagramNameInputRef}
          />
          </Dialog>
        ) : id ? (
          <DiagramDetailView
            diagramId={id}
            onBack={() => navigate("/diagrams")}
            onChanged={refresh}
          />
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            {t("diagrams.selectDiagram", "Select a diagram from the list to view details.")}
          </p>
          )
        }
      />
      </div>

      {pendingDeleteId && (
        <ConfirmDialog
          title={t("diagrams.deleteConfirmTitle", "Delete diagram?")}
          message={t("diagrams.deleteConfirm", "Really delete this diagram?")}
          confirmLabel={t("diagrams.delete", "Delete")}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDeleteId(null)}
          testId="diagram-list-delete-confirm"
        />
      )}
    </div>
  );
}
