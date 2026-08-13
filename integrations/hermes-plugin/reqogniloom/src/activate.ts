import type { HermesPluginAPI } from "./hermes-api-types";
import { ReqogniLoomPanel } from "./ReqogniLoomPanel";
import { initState } from "./state";

let hermesAPI: HermesPluginAPI | null = null;

export function getAPI(): HermesPluginAPI {
  if (!hermesAPI) throw new Error("ReqogniLoom plugin not activated");
  return hermesAPI;
}

export async function activate(api: HermesPluginAPI) {
  hermesAPI = api;

  api.ui.registerPanel("reqogniloom-panel", ReqogniLoomPanel);
  api.subscriptions.push(
    api.commands.register("reqogniloom.open", () => {
      api.ui.showPanel("reqogniloom-panel");
    })
  );

  try {
    await initState(api);
  } catch (err) {
    console.error("ReqogniLoom: initState failed, staying on connect view", err);
  }
}

export function deactivate() {
  hermesAPI = null;
}
