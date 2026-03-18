import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sendBatch } from '../src/transport';
import type { EventBatch } from '../src/types';

const endpoint = 'https://example.com/ingest';

function makeBatch(): EventBatch {
  return {
    events: [
      {
        type: 'prompt_save',
        data: {
          name: 'test',
          version: null,
          content: 'hello',
          hash: 'abc',
          metadata: {},
          created_at: '2026-01-01T00:00:00.000Z',
        },
        timestamp: '2026-01-01T00:00:00.000Z',
      },
    ],
  };
}

describe('sendBatch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('returns true on 200', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200 });
    vi.stubGlobal('fetch', fetchMock);

    const result = await sendBatch(makeBatch(), { endpoint });
    expect(result).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('sends correct headers without apiKey', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200 });
    vi.stubGlobal('fetch', fetchMock);

    await sendBatch(makeBatch(), { endpoint });

    const call = fetchMock.mock.calls[0];
    expect(call[0]).toBe(endpoint);
    expect(call[1].headers['Content-Type']).toBe('application/json');
    expect(call[1].headers['Authorization']).toBeUndefined();
  });

  it('sends Bearer token when apiKey is set', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200 });
    vi.stubGlobal('fetch', fetchMock);

    await sendBatch(makeBatch(), { endpoint, apiKey: 'pk_test' });

    const call = fetchMock.mock.calls[0];
    expect(call[1].headers['Authorization']).toBe('Bearer pk_test');
  });

  it('sends correct JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200 });
    vi.stubGlobal('fetch', fetchMock);

    const batch = makeBatch();
    await sendBatch(batch, { endpoint });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.events).toHaveLength(1);
    expect(body.events[0].type).toBe('prompt_save');
    expect(body.events[0].data.name).toBe('test');
    expect(body.events[0].data.version).toBeNull();
  });

  it('retries on network error and returns false after exhausted retries', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network'));
    vi.stubGlobal('fetch', fetchMock);

    const promise = sendBatch(makeBatch(), { endpoint });

    // Advance through the backoff delays (1s, 2s)
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(2000);

    const result = await promise;
    expect(result).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('returns false on repeated 500 responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 500 });
    vi.stubGlobal('fetch', fetchMock);

    const promise = sendBatch(makeBatch(), { endpoint });
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(2000);

    const result = await promise;
    expect(result).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('returns true on 2xx (e.g. 201)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 201 });
    vi.stubGlobal('fetch', fetchMock);

    const result = await sendBatch(makeBatch(), { endpoint });
    expect(result).toBe(true);
  });
});
