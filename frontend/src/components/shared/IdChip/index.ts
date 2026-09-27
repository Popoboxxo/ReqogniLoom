/**
 * ARCH-L1-001 ReactFrontend — <IdChip> barrel (issue #1094).
 *
 * One identifier chip for the whole app: shows the readable `uid` (default) or
 * the system id, and always copies the system id. See `IdChip.tsx` for the
 * full contract and for the note on how it relates to issue #92.
 */

export { IdChip } from "./IdChip";
export type {
  IdChipProps,
  IdChipDisplay,
  IdChipCopyResult,
  IdChipCopyStatus,
} from "./IdChip";
