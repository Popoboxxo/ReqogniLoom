/**
 * RFC 6238 TOTP helper for the MFA E2E flow (Plan E / WP E3.8, #1308).
 *
 * Deliberately dependency-free: Node's built-in `crypto` implements the
 * HMAC-SHA-1 primitive RFC 6238 asks for, so the browser test suite does not
 * need an authenticator library in `e2e/package.json`.
 */

import { createHmac } from "node:crypto";

const BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/** Decode an RFC 4648 base32 secret (the form `pyotp.random_base32` emits). */
export function base32Decode(input: string): Buffer {
  const normalized = input.replace(/=+$/u, "").replace(/\s+/gu, "").toUpperCase();
  let bits = 0;
  let value = 0;
  const bytes: number[] = [];

  for (const char of normalized) {
    const index = BASE32_ALPHABET.indexOf(char);
    if (index === -1) {
      throw new Error(`Invalid base32 character: ${char}`);
    }
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }

  return Buffer.from(bytes);
}

/** The 30-second TOTP counter for a timestamp (defaults to now). */
export function currentTotpStep(timestamp: number = Date.now(), period = 30): number {
  return Math.floor(timestamp / 1000 / period);
}

/** Generate the 6-digit RFC 6238 code for `secret` at `timestamp`. */
export function generateTotp(
  secret: string,
  timestamp: number = Date.now(),
  digits = 6,
  period = 30
): string {
  const counter = currentTotpStep(timestamp, period);
  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeBigUInt64BE(BigInt(counter));

  const hmac = createHmac("sha1", base32Decode(secret))
    .update(counterBuffer)
    .digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const binary =
    ((hmac[offset] & 0x7f) << 24) |
    (hmac[offset + 1] << 16) |
    (hmac[offset + 2] << 8) |
    hmac[offset + 3];

  return (binary % 10 ** digits).toString().padStart(digits, "0");
}

/**
 * Wait until the TOTP counter has moved past `step`.
 *
 * `MfaService.verify` rejects a code whose step is `<=` the device's
 * `last_used_step` (the replay guard). The E2E flow proves the same account
 * twice in a row, so it must not present the code from the step it just spent.
 * Bounded by the 30 s period.
 */
export async function waitForStepAfter(step: number, period = 30): Promise<number> {
  let current = currentTotpStep(Date.now(), period);
  while (current <= step) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    current = currentTotpStep(Date.now(), period);
  }
  return current;
}
