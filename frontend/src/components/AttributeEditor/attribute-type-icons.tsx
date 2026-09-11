/**
 * Task 12 (spec section 7): one lucide-react icon per ATTRIBUTE_TYPES value.
 * Shared by AttributeList and AttributeTable so both row renderers agree on
 * the same icon for a given type — no new icon dependency, reuses the
 * library already imported for this component group.
 */

import {
  AlignLeft,
  Calendar,
  Hash,
  Link as LinkIcon,
  List,
  ListChecks,
  Puzzle,
  ToggleLeft,
  Type as TypeIcon,
  User,
  type LucideIcon,
} from "lucide-react";

import type { AttributeType } from "../../api/attribute-definitions";

export const ATTRIBUTE_TYPE_ICONS: Record<AttributeType, LucideIcon> = {
  text: TypeIcon,
  textarea: AlignLeft,
  number: Hash,
  boolean: ToggleLeft,
  enum: List,
  "multi-enum": ListChecks,
  date: Calendar,
  reference: LinkIcon,
  user: User,
  widget: Puzzle,
};
