import * as React from "react";
import { useEffect, useState } from "react";
import type { PluginPanelProps } from "./hermes-api-types";
import { getState, subscribe } from "./state";
import { ConnectScreen } from "./ConnectScreen";
import { ConnectedView } from "./ConnectedView";
import { InterviewFormView } from "./InterviewFormView";
import { InterviewListView } from "./InterviewListView";

export function ReqogniLoomPanel(_props: PluginPanelProps) {
  const [, forceRender] = useState(0);

  useEffect(() => {
    return subscribe(() => forceRender((n) => n + 1));
  }, []);

  const state = getState();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        padding: "16px",
        gap: "12px",
        minWidth: "260px",
        maxWidth: "400px",
        overflowY: "auto",
        background: "var(--bg-1)",
        color: "var(--text-1)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-sm)",
      }}
    >
      <h3
        style={{
          margin: 0,
          fontSize: "var(--text-xs)",
          fontWeight: 600,
          textTransform: "uppercase",
          color: "var(--text-2)",
          letterSpacing: "0.05em",
        }}
      >
        REQOGNILOOM
      </h3>

      {state.view === "connect" && <ConnectScreen state={state} />}
      {state.view === "connected" && <ConnectedView state={state} />}
      {state.view === "interviews" && state.activeInterview && <InterviewFormView state={state} />}
      {state.view === "interviews" && !state.activeInterview && <InterviewListView state={state} />}
    </div>
  );
}
