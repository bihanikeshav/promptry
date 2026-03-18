/** HTTP POST with exponential-backoff retry (matches remote.py). */

import type { EventBatch } from './types';

const MAX_RETRIES = 3;
const TIMEOUT_MS = 10_000;

export interface TransportOptions {
  endpoint: string;
  apiKey?: string;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * POST a batch of events to the ingest endpoint.
 * Returns true on success, false if all retries exhausted.
 */
export async function sendBatch(
  batch: EventBatch,
  opts: TransportOptions,
): Promise<boolean> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (opts.apiKey) {
    headers['Authorization'] = `Bearer ${opts.apiKey}`;
  }

  const body = JSON.stringify(batch);

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

      const resp = await fetch(opts.endpoint, {
        method: 'POST',
        headers,
        body,
        signal: controller.signal,
      });

      clearTimeout(timer);

      if (resp.status < 300) {
        return true;
      }
    } catch {
      // Network error or timeout — retry with backoff
    }

    if (attempt < MAX_RETRIES - 1) {
      await delay(Math.min(2 ** attempt * 1000, 10_000));
    }
  }

  return false;
}
