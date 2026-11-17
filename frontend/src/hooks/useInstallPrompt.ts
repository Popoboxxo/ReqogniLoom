/**
 * Install-PWA prompt state (plan M3, REQ-213).
 *
 * Chromium exposes `beforeinstallprompt` once the manifest criteria are met;
 * iOS never does, so `platform` drives a share-menu instruction sheet instead
 * of a dead button. `userChoice` is authoritative: a dismissal is respected
 * for the session and persisted by the caller as a user preference.
 */
import { useCallback, useEffect, useState } from "react";

type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

export type InstallPlatform = "android" | "ios" | "other";

function detectPlatform(): InstallPlatform {
  if (typeof navigator === "undefined") return "other";
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua)) return "ios";
  if (/Android/.test(ua)) return "android";
  return "other";
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches === true ||
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export interface InstallPromptState {
  canInstall: boolean;
  platform: InstallPlatform;
  standalone: boolean;
  promptInstall: () => Promise<"accepted" | "dismissed" | "unavailable">;
}

export function useInstallPrompt(): InstallPromptState {
  const [event, setEvent] = useState<InstallEvent | null>(null);
  const [standalone, setStandalone] = useState(isStandalone);

  useEffect(() => {
    const capture = (raw: Event): void => {
      raw.preventDefault();
      setEvent(raw as InstallEvent);
    };
    const onDisplayChange = (): void => setStandalone(isStandalone());
    const displayQuery = window.matchMedia?.("(display-mode: standalone)");
    window.addEventListener("beforeinstallprompt", capture);
    displayQuery?.addEventListener?.("change", onDisplayChange);
    return () => {
      window.removeEventListener("beforeinstallprompt", capture);
      displayQuery?.removeEventListener?.("change", onDisplayChange);
    };
  }, []);

  const promptInstall = useCallback(async (): Promise<"accepted" | "dismissed" | "unavailable"> => {
    if (!event) return "unavailable";
    try {
      await event.prompt();
      const { outcome } = await event.userChoice;
      return outcome;
    } catch {
      // Chromium can reject prompt() (insecure context, another prompt
      // already open, user cancelled). Treat it like "no install available"
      // instead of leaking an unhandled rejection into the click handler.
      return "unavailable";
    } finally {
      // Clear the captured event on every path — success, rejection or
      // dismissal. A stale event would offer a dead install action forever.
      setEvent(null);
    }
  }, [event]);

  return {
    canInstall: event !== null && !standalone,
    platform: detectPlatform(),
    standalone,
    promptInstall,
  };
}
