/**
 * LinkTypeListbox — dialog-local, accessible single-select dropdown.
 *
 * leaf_id: COMP-RF-CTL-001 (sub-part of the CreateTraceLinkDialog)
 * req_id:  REQ-005 (unified trace-link creation dialog) / issue #318
 *
 * Why this exists
 * ---------------
 * Issue #318: the create-trace-link dialog's remaining native `<select>`
 * (the link-type control) behaves badly under automation and is hard to
 * drive: a programmatic `element.value = …` never reaches React state
 * (verified by a reproduction test), so the surface the user sees and the
 * value React would submit silently diverge. The dialog is asked to use the
 * same non-native dropdown pattern as its other pickers.
 *
 * Pattern (a11y review round 1, findings #1/#2)
 * ---------------------------------------------
 * APG "Select-Only Combobox" (ARIA 1.2), without moving DOM focus into the
 * popup. The trigger is a real `<button>` that carries `role="combobox"`
 * (ARIA in HTML explicitly permits the combobox role on a button):
 *   - `role="combobox"` + `aria-haspopup="listbox"` + `aria-expanded` +
 *     `aria-controls` (always pointing at the popup element, which is kept
 *     in the DOM and `hidden` while collapsed, so the ID reference is never
 *     dangling);
 *   - `aria-activedescendant` is only valid on application/combobox/
 *     composite/group/textbox, which is exactly why the role moved from the
 *     implicit `button` onto `combobox` — on a plain button the attribute
 *     was ignored and arrow-key navigation stayed silent for screen readers;
 *   - the accessible name is `aria-labelledby="{caption} {value}"`, and the
 *     selected value is also the trigger's text content, so both the name
 *     and the value are exposed (the native `<select>` exposed the value
 *     too — this restores that);
 *   - the popup is a `role="listbox"` whose children are `role="option"`
 *     with `aria-selected`; the selected row additionally carries a
 *     decorative, `aria-hidden` check mark so selection is visible, not
 *     only conveyed through `activeIndex` highlighting;
 *   - focus stays on the trigger; the visually active row is conveyed via
 *     `aria-activedescendant` (options carry `tabIndex={-1}` and suppress
 *     the mousedown focus shift, so keyboard focus is never moved into the
 *     popup and the enclosing <Dialog> focus trap stays intact).
 *
 * Keyboard contract (all required by #318):
 *   ArrowDown / ArrowUp — open when closed, then move the active row,
 *                         skipping nothing and not wrapping out of range;
 *   Home / End          — jump to first / last row while open;
 *   Enter / Space       — open when closed, commit the active row when open;
 *   printable character — typeahead: prefix-match a row (cycling on repeats)
 *                         and open the popup (natives `<select>` had this);
 *   Escape              — close and return focus to the trigger;
 *   Tab                 — close and let the browser move focus onward.
 *
 * Empty state (a11y review round 1, finding #4)
 * ---------------------------------------------
 * With zero options the popup never opens (no empty listbox is announced)
 * and the trigger points `aria-describedby` at the visible "no link type
 * connects these artifacts" hint rendered by the parent (WCAG 3.3.2).
 *
 * Escape handling is deliberately registered as a *window* capture listener
 * while the popup is open. The enclosing <Dialog>'s focus trap owns Escape
 * via a `document` capture listener (see use-focus-trap.ts); a listener on
 * `window` runs earlier in the capture path and can therefore dismiss the
 * popup without closing the whole dialog. A React `onKeyDown` cannot do
 * this, because the trap's `stopPropagation()` prevents the event from ever
 * reaching React's delegated root listener.
 *
 * Selection is reported through `onSelect`, i.e. through a React event
 * handler — never by writing to a DOM value — which is what makes the
 * submit button's enabled state deterministic (#318).
 */

import React, { useEffect, useId, useRef } from 'react';

export interface ListboxOption {
  /** Stable value submitted to the API. */
  key: string;
  /** Human-readable label rendered in the trigger and the popup. */
  label: string;
}

export interface LinkTypeListboxProps {
  options: ListboxOption[];
  value: string;
  onSelect: (key: string) => void;
  /** Reflects whether the popup is open. */
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** id of the visible label element, wired through `aria-labelledby`. */
  labelledBy: string;
  /** Trigger's data-testid (E2E contract). */
  testId: string;
  /** Prefix for the popup + option data-testids. */
  optionTestIdPrefix: string;
  /**
   * id of a visible hint explaining an empty option list. Referenced via
   * `aria-describedby` so the reason is programmatically associated
   * (WCAG 3.3.2) instead of only being visible next to the control.
   */
  describedBy?: string;
  disabled?: boolean;
}

// Named consts, not inline object literals directly in a style attribute:
// the frozen baseline in src/test/ui-ratchet.test.ts counts every literal
// object-notation style attribute occurrence in components/, comments
// included, so writing the pattern out here would itself raise the count.

const triggerStyle: React.CSSProperties = {
  width: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 'var(--space-2)',
  padding: 'var(--space-2) var(--space-3)',
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--color-border)',
  fontSize: 'var(--font-size-sm)',
  background: 'var(--color-surface)',
  color: 'var(--color-text)',
  boxSizing: 'border-box',
  fontFamily: 'var(--font-sans)',
  textAlign: 'left',
  cursor: 'pointer',
};

const triggerLabelStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const chevronStyle: React.CSSProperties = {
  flexShrink: 0,
  color: 'var(--color-text-muted)',
};

const listboxStyle: React.CSSProperties = {
  margin: 'var(--space-1) 0 0',
  padding: 0,
  maxHeight: '200px',
  overflowY: 'auto',
  listStyle: 'none',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--color-surface)',
};

const optionStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 'var(--space-2)',
  padding: 'var(--space-2) var(--space-3)',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text)',
  cursor: 'pointer',
};

const optionActiveStyle: React.CSSProperties = {
  ...optionStyle,
  background: 'var(--color-primary)',
  color: 'var(--color-on-primary)',
};

const optionLabelStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const optionCheckStyle: React.CSSProperties = {
  flexShrink: 0,
  fontWeight: 700,
};

/** How long a typeahead buffer survives without another keystroke. */
const TYPEAHEAD_TIMEOUT_MS = 500;

export function LinkTypeListbox({
  options,
  value,
  onSelect,
  isOpen,
  onOpenChange,
  labelledBy,
  testId,
  optionTestIdPrefix,
  describedBy,
  disabled = false,
}: LinkTypeListboxProps): JSX.Element {
  const listboxId = useId();
  const valueId = `${listboxId}-value`;
  const optionId = (index: number): string => `${listboxId}-option-${index}`;
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const [activeIndex, setActiveIndex] = React.useState<number>(() => {
    const selected = options.findIndex((o) => o.key === value);
    return selected >= 0 ? selected : 0;
  });

  // `options` is a fresh array on every parent render (it is a `filter`
  // result there), so the effects below read it through a ref instead of
  // declaring it as a dependency — otherwise reopening/arrow-navigation
  // would be reset on every keystroke of the surrounding form.
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const valueRef = useRef(value);
  valueRef.current = value;

  /** Index of the currently selected option, clamped to a valid row. */
  const selectedIndex = (): number => {
    const index = optionsRef.current.findIndex((o) => o.key === valueRef.current);
    return index >= 0 ? index : 0;
  };

  // Opening always positions the active row explicitly. This used to be an
  // `isOpen` effect, but that ran *after* a typeahead keystroke had already
  // moved the active row and snapped it back to the selected option.
  const openAt = (index: number): void => {
    setActiveIndex(index);
    onOpenChange(true);
  };

  const optionCount = options.length;
  // Finding #4: never announce an empty listbox — the trigger stays
  // focusable (and described by the hint), it just cannot be opened.
  const canOpen = !disabled && optionCount > 0;

  // Keep the active row in range when the option list shrinks under it.
  useEffect(() => {
    setActiveIndex((previous) => {
      if (optionCount === 0) return 0;
      return Math.min(previous, optionCount - 1);
    });
  }, [optionCount]);

  // Scroll the active row into view while navigating by keyboard.
  useEffect(() => {
    if (!isOpen) return;
    const active = document.getElementById(optionId(activeIndex));
    active?.scrollIntoView?.({ block: 'nearest' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, isOpen]);

  /**
   * Escape must dismiss the popup, not the dialog. Registered on `window`
   * in the capture phase so it runs before the Dialog's focus trap on
   * `document` (see the file header). Only Escape is touched; every other
   * key keeps the trap's normal behaviour.
   */
  useEffect(() => {
    if (!isOpen) return;
    const handleWindowKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      onOpenChange(false);
      triggerRef.current?.focus();
    };
    window.addEventListener('keydown', handleWindowKeyDown, true);
    return () => window.removeEventListener('keydown', handleWindowKeyDown, true);
  }, [isOpen, onOpenChange]);

  // Pointer outside the widget closes the popup without closing the dialog.
  const rootRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!isOpen) return;
    const handleDocumentMouseDown = (event: MouseEvent): void => {
      const target = event.target as Node | null;
      if (target && rootRef.current?.contains(target)) return;
      onOpenChange(false);
    };
    document.addEventListener('mousedown', handleDocumentMouseDown);
    return () => document.removeEventListener('mousedown', handleDocumentMouseDown);
  }, [isOpen, onOpenChange]);

  // Typeahead buffer (finding #3): a native <select> matched typed prefixes;
  // this restores that for the non-native control.
  const typeaheadRef = useRef('');
  const typeaheadTimerRef = useRef<number | null>(null);
  useEffect(() => {
    return () => {
      if (typeaheadTimerRef.current !== null) {
        window.clearTimeout(typeaheadTimerRef.current);
      }
    };
  }, []);

  const runTypeahead = (char: string): void => {
    // Finding #4: an empty option list must not be opened either.
    if (!canOpen) return;

    const charKey = char.toLowerCase();
    const buffer = `${typeaheadRef.current}${charKey}`;
    typeaheadRef.current = buffer;
    if (typeaheadTimerRef.current !== null) {
      window.clearTimeout(typeaheadTimerRef.current);
    }
    typeaheadTimerRef.current = window.setTimeout(() => {
      typeaheadRef.current = '';
    }, TYPEAHEAD_TIMEOUT_MS);

    const list = optionsRef.current;
    const count = list.length;

    // APG select-only combobox (N1): a buffer consisting solely of one
    // repeated character ("zz") is matched as that *single* character and
    // advances cyclically to the next option starting with it, so repeated
    // identical keystrokes walk through all such options instead of getting
    // stuck. Any other buffer is a plain prefix match; if the whole buffer
    // matches nothing, fall back to the single typed character.
    const repeated = /^(.)\1+$/.exec(buffer);
    const matchKey = repeated ? repeated[1] : buffer;

    // Functional updater: it always sees the latest active row, so two
    // keystrokes processed in the same React batch still advance twice.
    setActiveIndex((previous) => {
      const findFrom = (key: string): number => {
        for (let offset = 1; offset <= count; offset += 1) {
          const index = (previous + offset) % count;
          if (list[index].label.toLowerCase().startsWith(key)) return index;
        }
        return -1;
      };
      let match = findFrom(matchKey);
      if (match < 0 && matchKey !== charKey) {
        match = findFrom(charKey);
      }
      return match >= 0 ? match : previous;
    });

    // Typing is an explicit open gesture, matching the native control.
    if (!isOpen) onOpenChange(true);
  };

  const commit = (index: number): void => {
    const option = optionsRef.current[index];
    if (option) onSelect(option.key);
    onOpenChange(false);
  };

  const handleTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>): void => {
    if (disabled) return;
    const count = optionsRef.current.length;

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!canOpen) return;
        if (!isOpen) openAt(selectedIndex());
        else if (count > 0) setActiveIndex((i) => Math.min(count - 1, i + 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (!canOpen) return;
        if (!isOpen) openAt(selectedIndex());
        else if (count > 0) setActiveIndex((i) => Math.max(0, i - 1));
        break;
      case 'Home':
        if (isOpen) {
          event.preventDefault();
          setActiveIndex(0);
        }
        break;
      case 'End':
        if (isOpen) {
          event.preventDefault();
          setActiveIndex(Math.max(0, count - 1));
        }
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        if (!canOpen) return;
        if (!isOpen) openAt(selectedIndex());
        else commit(activeIndex);
        break;
      case 'Tab':
        // Let the browser move focus onward; only the popup is dismissed.
        if (isOpen) onOpenChange(false);
        break;
      default:
        // Printable character -> typeahead. Modifier chords (Ctrl/Cmd/Alt)
        // are shortcuts, not text input.
        if (
          event.key.length === 1 &&
          !event.ctrlKey &&
          !event.metaKey &&
          !event.altKey
        ) {
          runTypeahead(event.key);
        }
        break;
    }
  };

  const selectedLabel = options.find((o) => o.key === value)?.label ?? '';

  return (
    <div ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        data-testid={testId}
        data-value={value}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-labelledby={`${labelledBy} ${valueId}`}
        aria-describedby={describedBy}
        aria-activedescendant={isOpen && options.length > 0 ? optionId(activeIndex) : undefined}
        disabled={disabled}
        onClick={() => {
          if (!canOpen) return;
          if (isOpen) onOpenChange(false);
          else openAt(selectedIndex());
        }}
        onKeyDown={handleTriggerKeyDown}
        style={triggerStyle}
      >
        <span id={valueId} data-testid={`${optionTestIdPrefix}-value`} style={triggerLabelStyle}>
          {selectedLabel}
        </span>
        <span aria-hidden="true" style={chevronStyle}>
          ▾
        </span>
      </button>

      {/* Kept in the DOM and merely hidden while collapsed so the trigger's
          `aria-controls` always references an existing element (finding #1). */}
      <ul
        role="listbox"
        id={listboxId}
        aria-labelledby={labelledBy}
        hidden={!isOpen}
        tabIndex={-1}
        data-testid={`${optionTestIdPrefix}-listbox`}
        style={listboxStyle}
      >
        {options.map((option, index) => {
          const isSelected = option.key === value;
          return (
            // eslint-disable-next-line jsx-a11y/click-events-have-key-events
            <li
              key={option.key}
              id={optionId(index)}
              role="option"
              aria-selected={isSelected}
              data-testid={`${optionTestIdPrefix}-option-${option.key}`}
              data-value={option.key}
              tabIndex={-1}
              // Keep focus on the trigger: without this the browser would
              // move focus to <body> on mousedown, and the Dialog focus
              // trap's `focusin` safety net would yank it back to the
              // dialog's first control mid-interaction.
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => commit(index)}
              style={index === activeIndex ? optionActiveStyle : optionStyle}
            >
              <span style={optionLabelStyle}>{option.label}</span>
              {/* Finding #5: selection is visible, not only conveyed by the
                  active-row highlight. Decorative for AT — `aria-selected`
                  already carries the semantics. */}
              {isSelected && (
                <span aria-hidden="true" style={optionCheckStyle}>
                  ✓
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

LinkTypeListbox.displayName = 'LinkTypeListbox';
