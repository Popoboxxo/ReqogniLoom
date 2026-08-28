/**
 * Interview-management web widget — artifact panel pane (plan Task 7).
 *
 * Shows grounding candidates as "possibly related" hints while the
 * interview is in progress, and a "Formalize" button once no fields are
 * missing. `formalize`'s response only returns bare artifact ids -- v1
 * deliberately renders a plain, non-navigable id list rather than adding a
 * per-id lookup call to resolve a route/type, which would be speculative
 * scope beyond what the spec asks for (plan Task 7 interfaces note).
 */
import { useState } from "react";
import { interviewsApi, type InterviewState } from "../../api/interviews";
import styles from "./InterviewArtifactPane.module.css";

export function InterviewArtifactPane({
  interview,
  onFormalized,
}: {
  interview: InterviewState;
  onFormalized: (r: { resulting_artifact_ids: string[] }) => void;
}): JSX.Element {
  const [result, setResult] = useState<{ resulting_artifact_ids: string[] } | null>(null);

  const formalize = async () => {
    const r = await interviewsApi.formalize(interview.id);
    setResult(r);
    onFormalized({ resulting_artifact_ids: r.resulting_artifact_ids });
  };

  return (
    <div className={styles.pane}>
      {interview.status === "in_progress" && (interview.grounding_snapshot.candidates ?? []).length > 0 && (
        <ul className={styles.hints} aria-label="Possibly related artifacts">
          {interview.grounding_snapshot.candidates!.map((c) => (
            <li key={c.artifact_id}>Possibly related: {c.title}</li>
          ))}
        </ul>
      )}
      <button
        type="button"
        data-testid="interview-artifact-formalize"
        disabled={interview.missing_fields.length > 0}
        onClick={() => void formalize()}
      >
        Formalize
      </button>
      {result && (
        <p className={styles.result}>Created/updated: {result.resulting_artifact_ids.join(", ")}</p>
      )}
    </div>
  );
}
