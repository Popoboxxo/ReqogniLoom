/**
 * REQ-L1-084: Generic SplitView Container Component
 *
 * Provides a reusable two-column layout (List | Divider | Detail) with:
 * - Resizable divider via drag-and-drop
 * - localStorage persistence of left panel width
 * - Responsive collapse on mobile (<768px)
 * - Full type safety and accessibility
 *
 * Usage:
 * ```tsx
 * <SplitView
 *   leftPanel={<RequirementsList />}
 *   rightPanel={<RequirementForm />}
 *   onDividerMove={(widthPercent) => console.log(widthPercent)}
 * />
 * ```
 *
 * leaf_id: COMP-RF-005-SplitView
 * interfaces: none (internal UI container)
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';

/**
 * Props for the generic SplitView component.
 */
export interface SplitViewProps {
  /** Left panel content (typically a list/tree component) */
  leftPanel: React.ReactNode;

  /** Right panel content (typically a form/detail component) */
  rightPanel: React.ReactNode;

  /** Minimum width for left panel in pixels (default: 200) */
  leftMinWidth?: number;

  /** Maximum width for left panel as percentage of total (default: 70) */
  leftMaxWidthPercent?: number;

  /** Initial left panel width in pixels (optional; uses localStorage or default if not provided) */
  initialLeftWidth?: number;

  /** Module identifier for localStorage key (e.g., "requirements", "architecture") */
  moduleType?: string;

  /** Custom CSS class for the divider */
  dividerClassName?: string;

  /** Callback when divider is moved; receives pixel width of left panel */
  onDividerMove?: (widthPixels: number) => void;

  /** Enable responsive collapse on mobile (<768px) */
  responsiveMode?: boolean;

  /** Classname for root container */
  containerClassName?: string;
}

/**
 * Generic SplitView Component — implements REQ-L1-084
 *
 * Manages:
 * - Two-column flex layout with draggable divider
 * - localStorage persistence under key: `reqflow_splitview_${moduleType}`
 * - Mouse-drag resize with smooth transitions
 * - Responsive collapse on mobile devices
 * - Visual feedback (cursor, hover, active states)
 *
 * @param props - SplitViewProps configuration
 * @returns JSX.Element rendering the split-view container
 */
export const SplitView = React.forwardRef<
  HTMLDivElement,
  SplitViewProps
>(
  (
    {
      leftPanel,
      rightPanel,
      leftMinWidth = 200,
      leftMaxWidthPercent = 70,
      initialLeftWidth,
      moduleType = 'default',
      dividerClassName,
      onDividerMove,
      responsiveMode = true,
      containerClassName,
    },
    ref
  ) => {
    // -----------------------------------------------------------------------
    // State: left panel width (pixels), drag state
    // -----------------------------------------------------------------------

    const storageKey = `reqflow_splitview_${moduleType}`;

    const getInitialWidth = useCallback((): number => {
      // 1. Explicit initialLeftWidth prop
      if (initialLeftWidth !== undefined) {
        return initialLeftWidth;
      }

      // 2. localStorage (persisted from previous session)
      const stored =
        typeof window !== "undefined" && window.localStorage
          ? window.localStorage.getItem(storageKey)
          : null;
      if (stored) {
        const parsed = parseInt(stored, 10);
        if (!isNaN(parsed) && parsed >= leftMinWidth) {
          return parsed;
        }
      }

      // 3. Default: 40% of viewport
      return Math.max(leftMinWidth, window.innerWidth * 0.4);
    }, [initialLeftWidth, moduleType, storageKey, leftMinWidth]);

    const [leftPanelWidth, setLeftPanelWidth] = useState(getInitialWidth());
    const [isResponsiveCollapsed, setIsResponsiveCollapsed] = useState(
      responsiveMode && window.innerWidth < 768
    );

    // Drag state
    const isDraggingRef = useRef(false);
    const dragStartXRef = useRef(0);
    const dragStartWidthRef = useRef(0);
    const dividerRef = useRef<HTMLDivElement>(null);

    // -----------------------------------------------------------------------
    // Handlers: divider mouse events, persistence
    // -----------------------------------------------------------------------

    const handleDividerMouseDown = useCallback(
      (e: React.MouseEvent<HTMLDivElement>): void => {
        isDraggingRef.current = true;
        dragStartXRef.current = e.clientX;
        dragStartWidthRef.current = leftPanelWidth;

        // Visual feedback
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';

        if (dividerRef.current) {
          dividerRef.current.classList.add('dragging');
        }

        e.preventDefault();
      },
      [leftPanelWidth]
    );

    const persistWidth = useCallback((width: number): void => {
      localStorage.setItem(storageKey, String(width));
      onDividerMove?.(width);
    }, [storageKey, onDividerMove]);

    // -----------------------------------------------------------------------
    // Global mouse events: move and up
    // -----------------------------------------------------------------------

    useEffect(() => {
      const handleMouseMove = (e: MouseEvent): void => {
        if (!isDraggingRef.current) return;

        const delta = e.clientX - dragStartXRef.current;
        const newWidth = Math.max(leftMinWidth, dragStartWidthRef.current + delta);

        // Respect max-width constraint (percentage-based)
        const containerWidth = dividerRef.current?.parentElement?.clientWidth ?? window.innerWidth;
        const maxWidth = (containerWidth * leftMaxWidthPercent) / 100;
        const constrainedWidth = Math.min(newWidth, maxWidth);

        setLeftPanelWidth(constrainedWidth);
      };

      const handleMouseUp = (): void => {
        if (!isDraggingRef.current) return;

        isDraggingRef.current = false;
        document.body.style.userSelect = '';
        document.body.style.cursor = '';

        if (dividerRef.current) {
          dividerRef.current.classList.remove('dragging');
        }

        // Persist the final width
        persistWidth(leftPanelWidth);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);

      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }, [leftPanelWidth, leftMinWidth, leftMaxWidthPercent, persistWidth]);

    // -----------------------------------------------------------------------
    // Responsive behavior: listen for window resize
    // -----------------------------------------------------------------------

    useEffect(() => {
      if (!responsiveMode) return;

      const handleResize = (): void => {
        const isNowResponsive = window.innerWidth < 768;
        setIsResponsiveCollapsed(isNowResponsive);
      };

      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }, [responsiveMode]);

    // -----------------------------------------------------------------------
    // Responsive render: stacked layout or toggle tabs on mobile
    // -----------------------------------------------------------------------

    if (isResponsiveCollapsed) {
      return (
        <div
          ref={ref}
          className={containerClassName}
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            overflow: 'hidden',
            background: 'var(--color-background)',
          }}
        >
          {/* Mobile: tab-like toggle between left and right panels */}
          <div
            style={{
              display: 'flex',
              gap: '1px',
              borderBottom: '1px solid var(--color-border)',
              background: 'var(--color-surface)',
              padding: 0,
            }}
          >
            <button
              onClick={() => setIsResponsiveCollapsed(true)}
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 'var(--font-size-sm)',
                fontWeight: 600,
                color: 'var(--color-text)',
                borderBottom: '2px solid var(--color-primary)',
              }}
            >
              List
            </button>
            <button
              onClick={() => setIsResponsiveCollapsed(false)}
              style={{
                flex: 1,
                padding: 'var(--space-3)',
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 'var(--font-size-sm)',
                fontWeight: 600,
                color: 'var(--color-text-muted)',
              }}
            >
              Detail
            </button>
          </div>

          {/* Show only left panel on mobile (collapsed state) */}
          <div
            style={{
              flex: 1,
              overflow: 'auto',
              padding: 'var(--space-4)',
            }}
          >
            {leftPanel}
          </div>
        </div>
      );
    }

    // -----------------------------------------------------------------------
    // Desktop render: side-by-side with resizable divider
    // -----------------------------------------------------------------------

    return (
      <div
        ref={ref}
        className={containerClassName}
        style={{
          display: 'flex',
          height: '100%',
          overflow: 'hidden',
          background: 'var(--color-background)',
          fontFamily: 'var(--font-sans)',
          color: 'var(--color-text)',
        }}
      >
        {/* Left Panel */}
        <div
          style={{
            flex: `0 0 ${leftPanelWidth}px`,
            minWidth: `${leftMinWidth}px`,
            maxWidth: `${leftMaxWidthPercent}%`,
            overflow: 'auto',
            borderRight: '1px solid var(--color-border)',
            background: 'var(--color-surface)',
            padding: 'var(--space-4)',
          }}
        >
          {leftPanel}
        </div>

        {/* Divider — REQ-007: 12px hitbox, 2px visual center line via gradient */}
        <div
          ref={dividerRef}
          data-testid="splitview-divider"
          className={`splitview-divider ${dividerClassName || ''}`}
          onMouseDown={handleDividerMouseDown}
          style={{
            flex: '0 0 12px',
            background: 'linear-gradient(90deg, transparent 5px, var(--color-border) 5px, var(--color-border) 7px, transparent 7px)',
            cursor: 'col-resize',
            transition: isDraggingRef.current ? 'none' : 'background 0.2s ease',
            userSelect: 'none',
          }}
          onMouseEnter={(e) => {
            if (!isDraggingRef.current) {
              e.currentTarget.style.background = 'linear-gradient(90deg, transparent 4px, var(--color-primary) 4px, var(--color-primary) 8px, transparent 8px)';
            }
          }}
          onMouseLeave={(e) => {
            if (!isDraggingRef.current) {
              e.currentTarget.style.background = 'linear-gradient(90deg, transparent 5px, var(--color-border) 5px, var(--color-border) 7px, transparent 7px)';
            }
          }}
        />

        {/* Right Panel */}
        <div
          style={{
            flex: '1 1 auto',
            overflow: 'auto',
            background: 'var(--color-background)',
            padding: 'var(--space-4)',
          }}
        >
          {rightPanel}
        </div>
      </div>
    );
  }
);

SplitView.displayName = 'SplitView';
