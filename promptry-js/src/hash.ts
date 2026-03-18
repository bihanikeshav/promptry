/** Cross-platform SHA-256 (Web Crypto / node:crypto). */

function hexFromBuffer(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let hex = '';
  for (let i = 0; i < bytes.length; i++) {
    hex += bytes[i].toString(16).padStart(2, '0');
  }
  return hex;
}

export async function sha256(input: string): Promise<string> {
  // Browser / Deno / Bun / Node 20+ with globalThis.crypto.subtle
  if (typeof globalThis.crypto?.subtle?.digest === 'function') {
    const data = new TextEncoder().encode(input);
    const buf = await globalThis.crypto.subtle.digest('SHA-256', data);
    return hexFromBuffer(buf);
  }

  // Node 18+ fallback
  const { createHash } = await import('node:crypto');
  return createHash('sha256').update(input, 'utf-8').digest('hex');
}
