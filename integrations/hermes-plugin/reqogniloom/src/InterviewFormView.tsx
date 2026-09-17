import * as React from "react";
import { useState } from "react";
import type { AppState } from "./state";
import { answerInterviewField, cancelInterview, closeInterview, formalizeInterview, setInterviewTarget } from "./state";
import type { InterviewField } from "./mcpClient";
import { buttonStyle, ErrorBanner } from "./uiKit";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "4px 6px",
  background: "var(--bg-2, transparent)",
  border: "1px solid var(--border, #444)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text-1)",
  fontSize: "var(--text-sm)",
};

function FieldInput({ field }: { field: InterviewField }): JSX.Element {
  const [value, setValue] = useState("");
  const commonProps = {
    "data-testid": `interview-field-${field.name}`,
    style: inputStyle,
    value,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setValue(e.target.value),
    onBlur: () => {
      if (value !== "") void answerInterviewField(field.name, field.type === "number" ? Number(value) : value);
    },
  };

  if (field.type === "textarea") return <textarea {...commonProps} />;
  if (field.type === "enum") {
    return (
      <select {...commonProps}>
        <option value="" disabled>
          Select…
        </option>
        {(field.choices ?? []).map((choice) => (
          <option key={choice} value={choice}>
            {choice}
          </option>
        ))}
      </select>
    );
  }
  return <input {...commonProps} type={field.type === "number" ? "number" : "text"} />;
}

export function InterviewFormView({ state }: { state: AppState }): JSX.Element | null {
  const [result, setResult] = useState<{ resulting_artifact_ids: string[] } | null>(null);
  const interview = state.activeInterview;
  if (!interview) return null;

  if (interview.status !== "in_progress") {
    return (
      <div>
        <ErrorBanner message={state.interviewError} />
        <p>Session is {interview.status}.</p>
        {result && <p>Created/updated: {result.resulting_artifact_ids.join(", ")}</p>}
        <button type="button" data-testid="interview-form-close-button" style={buttonStyle} onClick={closeInterview}>
          Close
        </button>
      </div>
    );
  }

  const candidates = interview.grounding_snapshot?.candidates ?? [];
  const answeredFields = Object.entries(interview.collected_fields);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <ErrorBanner message={state.interviewError} />

      <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>{interview.phase}</span>

      {answeredFields.length > 0 && (
        <div>
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Answered</span>
          <ul style={{ fontSize: "var(--text-xs)", listStyle: "none", padding: 0, margin: 0 }}>
            {answeredFields.map(([name, value]) => (
              <li key={name}>
                {name}: {String(value)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {candidates.length > 0 && (
        <ul style={{ fontSize: "var(--text-xs)", color: "var(--text-2)", listStyle: "none", padding: 0 }}>
          {candidates.map((c) => (
            <li key={c.artifact_id} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              Possibly related: {c.title}
              <button
                type="button"
                data-testid={`interview-target-${c.artifact_id}`}
                style={buttonStyle}
                disabled={state.interviewBusy}
                onClick={() => void setInterviewTarget(c.artifact_id)}
              >
                Use this
              </button>
            </li>
          ))}
        </ul>
      )}

      {interview.missing_fields.map((field) => (
        <label key={field.name} style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          {field.name}
          <FieldInput field={field} />
        </label>
      ))}

      <div style={{ display: "flex", gap: "8px" }}>
        <button
          type="button"
          data-testid="interview-formalize-button"
          style={buttonStyle}
          disabled={interview.missing_fields.length > 0}
          onClick={async () => {
            const r = await formalizeInterview();
            if (r) setResult(r);
          }}
        >
          Formalize
        </button>

        <button
          type="button"
          data-testid="interview-form-cancel-button"
          style={buttonStyle}
          onClick={() => void cancelInterview()}
        >
          Cancel
        </button>
      </div>

      {result && <p>Created/updated: {result.resulting_artifact_ids.join(", ")}</p>}
    </div>
  );
}
