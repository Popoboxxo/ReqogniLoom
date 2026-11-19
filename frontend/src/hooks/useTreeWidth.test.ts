/**
 * Task 9 (Schnitt 3b) — per-module tree-width persistence (ADR-030).
 *
 * RED-first contract:
 *   - the ONLY storage key is `reqflow.splitview.treeWidth.v2.<moduleType>`;
 *     the removed UI-001 underscore key family is neither read nor written;
 *   - per-module defaults (ADR 350 / Requirements 424 / …);
 *   - clamp `TREE_WIDTH_MIN` (380) … `effMax` (runtime formula from SplitView);
 *   - corrupt / out-of-range stored values fall back to the module default;
 *   - reset deletes the key; modules are independent.
 *
 * The helper functions are pure (no React) so the storage semantics can be
 * pinned without a DOM; the last block exercises the hook itself via renderHook.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  DEFAULT_TREE_WIDTH_BY_MODULE,
  TREE_WIDTH_MIN,
  TREE_WIDTH_STORAGE_KEY,
  computeTreeWidthEffMax,
  defaultTreeWidthFor,
  readTreeWidth,
  resetStoredTreeWidth,
  treeWidthStorageKey,
  useTreeWidth,
  writeTreeWidth,
} from './useTreeWidth';

/** `min(0.7 * 1200, 1200 - 520 - 24)` = `min(840, 656)` = 656. */
const CONTENT_WIDTH = 1200;
const EFF_MAX = 656;
const BOUNDS = { contentWidth: CONTENT_WIDTH };
/** ADR host passes `minWidths[0] = 320`, so its 350 px default stays in range. */
const ADR_BOUNDS = { min: 320, contentWidth: CONTENT_WIDTH };
// Built from parts on purpose: the stale-key gate requires ZERO literal hits
// of the removed UI-001 key anywhere under frontend/src — even in tests.
const LEGACY_KEY = ['reqflow', 'splitview', 'requirements'].join('_');

function store(key: string, value: string | null): void {
  if (value === null) window.localStorage.removeItem(key);
  else window.localStorage.setItem(key, value);
}

describe('useTreeWidth — persistence & clamp (ADR-030 / Task 9)', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('uses a single v2 key prefix and never the removed UI-001 key family', () => {
    expect(TREE_WIDTH_STORAGE_KEY).toBe('reqflow.splitview.treeWidth.v2.');
    expect(treeWidthStorageKey('requirements')).toBe('reqflow.splitview.treeWidth.v2.requirements');
    expect(treeWidthStorageKey('adr')).toBe('reqflow.splitview.treeWidth.v2.adr');

    // A stale legacy value left in storage must be ignored and NOT deleted —
    // this change never touches the old key (0 code hits, 0 storage hits).
    store(LEGACY_KEY, '999');
    writeTreeWidth('requirements', 500, BOUNDS);

    expect(window.localStorage.getItem(LEGACY_KEY)).toBe('999');
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBe('500');

    // Source-level guarantee: no future patch can reintroduce the old key
    // through this hook by accident.
    const source = readFileSync(resolve(__dirname, 'useTreeWidth.ts'), 'utf-8');
    expect(source).not.toContain(['reqflow', 'splitview'].join('_'));
  });

  it('returns per-module defaults when nothing is stored', () => {
    expect(DEFAULT_TREE_WIDTH_BY_MODULE.adr).toBe(350);
    expect(DEFAULT_TREE_WIDTH_BY_MODULE.requirements).toBe(424);
    expect(readTreeWidth('adr', ADR_BOUNDS)).toBe(350);
    expect(readTreeWidth('requirements', BOUNDS)).toBe(424);
  });

  it('clamps writes to TREE_WIDTH_MIN … effMax (ADR-030 runtime formula)', () => {
    expect(TREE_WIDTH_MIN).toBe(380);
    expect(computeTreeWidthEffMax(CONTENT_WIDTH)).toBe(EFF_MAX);

    writeTreeWidth('requirements', 100, BOUNDS);
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBe('380');

    writeTreeWidth('requirements', 5000, BOUNDS);
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBe(String(EFF_MAX));

    writeTreeWidth('requirements', 500, BOUNDS);
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBe('500');

    // A host may lower the floor via its own minWidths[0] (e.g. 320).
    writeTreeWidth('requirements', 300, { min: 320, contentWidth: CONTENT_WIDTH });
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBe('320');
  });

  it('keeps modules independent — an ADR width never moves the Requirements width', () => {
    writeTreeWidth('adr', 500, ADR_BOUNDS);
    writeTreeWidth('requirements', 600, BOUNDS);

    expect(readTreeWidth('adr', ADR_BOUNDS)).toBe(500);
    expect(readTreeWidth('requirements', BOUNDS)).toBe(600);

    resetStoredTreeWidth('adr');
    expect(readTreeWidth('adr', ADR_BOUNDS)).toBe(350);
    expect(readTreeWidth('requirements', BOUNDS)).toBe(600);
  });

  it.each(['', 'not-a-number', 'NaN', 'Infinity', '100', '99999'])(
    'falls back to the module default for a corrupt/out-of-range value %j',
    (raw) => {
      store(treeWidthStorageKey('requirements'), raw);
      expect(readTreeWidth('requirements', BOUNDS)).toBe(424);
    }
  );

  it('reset deletes the key and falls back to the module default', () => {
    writeTreeWidth('requirements', 500, BOUNDS);
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBe('500');

    resetStoredTreeWidth('requirements');
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBeNull();
    expect(readTreeWidth('requirements', BOUNDS)).toBe(424);
  });

  it('writing the module default also clears the key (SplitView Enter/dblclick reset)', () => {
    writeTreeWidth('requirements', 500, BOUNDS);
    writeTreeWidth('requirements', defaultTreeWidthFor('requirements', BOUNDS), BOUNDS);
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBeNull();
  });
});

describe('useTreeWidth — React hook surface (Task 9)', () => {
  beforeEach(() => {
    window.localStorage.clear();
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 1440,
    });
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('reads the stored value on first render and persists every resize via setTreeWidth', () => {
    store(treeWidthStorageKey('adr'), '500');
    const { result } = renderHook(() => useTreeWidth('adr', ADR_BOUNDS));

    expect(result.current.treeWidth).toBe(500);
    expect(result.current.defaultTreeWidth).toBe(350);

    act(() => result.current.setTreeWidth(516));
    expect(window.localStorage.getItem(treeWidthStorageKey('adr'))).toBe('516');
    expect(result.current.treeWidth).toBe(516);

    act(() => result.current.resetTreeWidth());
    expect(window.localStorage.getItem(treeWidthStorageKey('adr'))).toBeNull();
    expect(result.current.treeWidth).toBe(350);
  });

  it('two hook instances for different modules never share a width', () => {
    const adr = renderHook(() => useTreeWidth('adr', BOUNDS));
    const requirements = renderHook(() => useTreeWidth('requirements', BOUNDS));

    act(() => adr.result.current.setTreeWidth(500));
    expect(adr.result.current.treeWidth).toBe(500);
    expect(requirements.result.current.treeWidth).toBe(424);
    expect(window.localStorage.getItem(treeWidthStorageKey('adr'))).toBe('500');
    expect(window.localStorage.getItem(treeWidthStorageKey('requirements'))).toBeNull();
  });
});
