/** Runtime environment detection. */

/* eslint-disable @typescript-eslint/no-explicit-any */
const _g = globalThis as any;

export function isBrowser(): boolean {
  return typeof _g.window !== 'undefined' && typeof _g.document !== 'undefined';
}

export function isNode(): boolean {
  return typeof _g.process?.versions?.node === 'string';
}
