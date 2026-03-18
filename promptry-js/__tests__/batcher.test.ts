import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Batcher } from '../src/batcher';
import type { TelemetryEvent } from '../src/types';

// Mock transport
vi.mock('../src/transport', () => ({
  sendBatch: vi.fn().mockResolvedValue(true),
}));

// Mock storage to use MemoryStore always (no localStorage in Node tests)
vi.mock('../src/storage', () => {
  const events: TelemetryEvent[] = [];
  return {
    createOfflineStore: () => ({
      load: () => [...events],
      save: (e: TelemetryEvent[]) => events.push(...e),
      clear: () => events.length = 0,
    }),
  };
});

import { sendBatch } from '../src/transport';

const mockedSendBatch = vi.mocked(sendBatch);

function makeEvent(name: string): TelemetryEvent {
  return {
    type: 'prompt_save',
    data: {
      name,
      version: null,
      content: 'test',
      hash: 'abc',
      metadata: {},
      created_at: '2026-01-01T00:00:00.000Z',
    },
    timestamp: '2026-01-01T00:00:00.000Z',
  };
}

describe('Batcher', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedSendBatch.mockClear();
    mockedSendBatch.mockResolvedValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('flushes when batch size reached', async () => {
    const batcher = new Batcher({
      transport: { endpoint: 'http://test/ingest' },
      batchSize: 3,
      flushInterval: 60_000, // won't trigger
    });

    batcher.enqueue(makeEvent('a'));
    batcher.enqueue(makeEvent('b'));
    batcher.enqueue(makeEvent('c'));

    // Let the flush promise resolve
    await vi.advanceTimersByTimeAsync(0);

    expect(mockedSendBatch).toHaveBeenCalledTimes(1);
    const batch = mockedSendBatch.mock.calls[0][0];
    expect(batch.events).toHaveLength(3);

    await batcher.destroy();
  });

  it('flushes on timer interval', async () => {
    const batcher = new Batcher({
      transport: { endpoint: 'http://test/ingest' },
      batchSize: 100,
      flushInterval: 5000,
    });

    batcher.enqueue(makeEvent('a'));
    expect(mockedSendBatch).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(5000);

    expect(mockedSendBatch).toHaveBeenCalledTimes(1);

    await batcher.destroy();
  });

  it('manual flush sends all pending', async () => {
    const batcher = new Batcher({
      transport: { endpoint: 'http://test/ingest' },
      batchSize: 100,
      flushInterval: 60_000,
    });

    batcher.enqueue(makeEvent('a'));
    batcher.enqueue(makeEvent('b'));
    await batcher.flush();

    expect(mockedSendBatch).toHaveBeenCalledTimes(1);
    expect(mockedSendBatch.mock.calls[0][0].events).toHaveLength(2);

    await batcher.destroy();
  });

  it('tracks pending count', async () => {
    const batcher = new Batcher({
      transport: { endpoint: 'http://test/ingest' },
      batchSize: 100,
      flushInterval: 60_000,
    });

    expect(batcher.pending).toBe(0);
    batcher.enqueue(makeEvent('a'));
    expect(batcher.pending).toBe(1);

    await batcher.flush();
    expect(batcher.pending).toBe(0);

    await batcher.destroy();
  });

  it('does not send if queue is empty', async () => {
    const batcher = new Batcher({
      transport: { endpoint: 'http://test/ingest' },
      batchSize: 10,
      flushInterval: 60_000,
    });

    await batcher.flush();
    expect(mockedSendBatch).not.toHaveBeenCalled();

    await batcher.destroy();
  });

  it('destroy flushes remaining events', async () => {
    const batcher = new Batcher({
      transport: { endpoint: 'http://test/ingest' },
      batchSize: 100,
      flushInterval: 60_000,
    });

    batcher.enqueue(makeEvent('a'));
    await batcher.destroy();

    expect(mockedSendBatch).toHaveBeenCalledTimes(1);
  });
});
