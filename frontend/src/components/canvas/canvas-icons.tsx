/**
 * ARCH-L1-001 ReactFrontend — CanvasEditor toolbar icons (Presenter).
 *
 * leaf_id: COMP-RF-005 (CanvasEditor)
 * req_id:  REQ-L2-DS-006 (CanvasEditor), REQ-050 (Container/Presenter decomposition)
 *
 * Pure 16px stroke icons (stroke = currentColor) used by the CanvasEditor
 * toolbar. Extracted verbatim from the former monolithic CanvasEditor.
 */

export interface IconProps {
  children: React.ReactNode;
}

export function Icon({ children }: IconProps): JSX.Element {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const ICONS = {
  select: (
    <Icon>
      <path d="M3 2l4.5 11 1.6-4.4L13.5 7 3 2z" fill="currentColor" stroke="none" />
    </Icon>
  ),
  pen: (
    <Icon>
      <path d="M2.5 13.5l.9-3.2 7.4-7.4a1.3 1.3 0 011.8 0l.5.5a1.3 1.3 0 010 1.8l-7.4 7.4-3.2.9z" />
    </Icon>
  ),
  eraser: (
    <Icon>
      <path d="M5.5 13h8" />
      <path d="M2.7 10.3l6-6a1.2 1.2 0 011.7 0l2.3 2.3a1.2 1.2 0 010 1.7L8.5 12.5H5.9l-3.2-2.2z" />
    </Icon>
  ),
  rect: (
    <Icon>
      <rect x="2.5" y="4" width="11" height="8" rx="1.5" />
    </Icon>
  ),
  ellipse: (
    <Icon>
      <ellipse cx="8" cy="8" rx="5.5" ry="4" />
    </Icon>
  ),
  text: (
    <Icon>
      <path d="M3.5 4.5V3h9v1.5M8 3v10M6 13h4" />
    </Icon>
  ),
  connector: (
    <Icon>
      <rect x="1.5" y="1.5" width="5" height="4" rx="1" />
      <rect x="9.5" y="10.5" width="5" height="4" rx="1" />
      <path d="M6.5 5.5L10 10m0 0v-2.6M10 10H7.4" />
    </Icon>
  ),
  dashed: (
    <Icon>
      <path d="M2 8h2.5M6.5 8H9M11 8h3" />
    </Icon>
  ),
  solid: (
    <Icon>
      <path d="M2 8h12" />
    </Icon>
  ),
  grid: (
    <Icon>
      <circle cx="4" cy="4" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8" cy="4" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="4" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="4" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="8" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="4" cy="12" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="8" cy="12" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="0.8" fill="currentColor" stroke="none" />
    </Icon>
  ),
  zoomIn: (
    <Icon>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14M7 5v4M5 7h4" />
    </Icon>
  ),
  zoomOut: (
    <Icon>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14M5 7h4" />
    </Icon>
  ),
  fit: (
    <Icon>
      <path d="M2 5.5V2h3.5M14 5.5V2h-3.5M2 10.5V14h3.5M14 10.5V14h-3.5" />
    </Icon>
  ),
  undo: (
    <Icon>
      <path d="M6 3.5L2.5 7 6 10.5" />
      <path d="M2.5 7h7a4 4 0 010 8H8" />
    </Icon>
  ),
  redo: (
    <Icon>
      <path d="M10 3.5L13.5 7 10 10.5" />
      <path d="M13.5 7h-7a4 4 0 000 8H8" />
    </Icon>
  ),
};
