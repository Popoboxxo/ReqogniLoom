/**
 * ARCH-L1-001 ReactFrontend — <Dialog> barrel (UI concept ch. 12.8).
 */

export { Dialog } from "./Dialog";
export type { DialogProps } from "./Dialog";
export { useFocusTrap, getFocusableElements } from "./use-focus-trap";
export type { FocusTrapOptions } from "./use-focus-trap";
export {
  useSheetViewport,
  useSwipeToDismiss,
  SWIPE_DISMISS_THRESHOLD,
} from "./use-sheet-gestures";
export type {
  SwipeToDismissHandlers,
  SwipeToDismissOptions,
} from "./use-sheet-gestures";
