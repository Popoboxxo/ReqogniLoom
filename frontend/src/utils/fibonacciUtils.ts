/**
 * Fibonacci utility functions for complexity slider.
 * Standard Fibonacci sequence: 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233
 */

/**
 * Fibonacci sequence values used in complexity slider.
 */
export const FIBONACCI_SEQUENCE = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233];

/**
 * Get Fibonacci index for a given value.
 * Returns the position in the sequence (0-based).
 * Returns -1 if value is not in the sequence.
 *
 * @param value - Fibonacci value
 * @returns Index in sequence or -1 if not found
 */
export const fibIndex = (value: number): number => {
  return FIBONACCI_SEQUENCE.indexOf(value);
};

/**
 * Get Fibonacci value by index.
 * Returns the value at the given position (0-based).
 * Returns -1 if index is out of bounds.
 *
 * @param index - Position in sequence
 * @returns Fibonacci value or -1 if not found
 */
export const fibValue = (index: number): number => {
  return index >= 0 && index < FIBONACCI_SEQUENCE.length ? FIBONACCI_SEQUENCE[index] : -1;
};

/**
 * Format Fibonacci display label (e.g., "Fib(5) = 5").
 *
 * @param value - Fibonacci value
 * @returns Formatted label
 */
export const fibLabel = (value: number): string => {
  const idx = fibIndex(value);
  return idx >= 0 ? `Fib(${idx}) = ${value}` : String(value);
};

/**
 * Get next Fibonacci value in sequence.
 * Returns -1 if at the end.
 *
 * @param value - Current value
 * @returns Next value or -1 if at end
 */
export const fibNext = (value: number): number => {
  const idx = fibIndex(value);
  return fibValue(idx + 1);
};

/**
 * Get previous Fibonacci value in sequence.
 * Returns -1 if at the start.
 *
 * @param value - Current value
 * @returns Previous value or -1 if at start
 */
export const fibPrev = (value: number): number => {
  const idx = fibIndex(value);
  return fibValue(idx - 1);
};
