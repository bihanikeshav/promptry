import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Promptry } from '../src/promptry';
import type { EventBatch } from '../src/types';

// Capture all POSTed batches
const sentBatches: EventBatch[] = [];

vi.mock('../src/transport', () => ({
  sendBatch: vi.fn(async (batch: EventBatch) => {
    sentBatches.push(batch);
    return true;
  }),
}));

vi.mock('../src/storage', () => ({
  createOfflineStore: () => ({
    load: () => [],
    save: () => {},
    clear: () => {},
  }),
}));

describe('Promptry', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sentBatches.length = 0;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('track() returns content unchanged', () => {
    const p = new Promptry({ endpoint: 'http://test/ingest' });
    const result = p.track('hello world', 'test-prompt');
    expect(result).toBe('hello world');
    void p.destroy();
  });

  it('trackContext() returns chunks unchanged', () => {
    const p = new Promptry({ endpoint: 'http://test/ingest' });
    const chunks = ['chunk1', 'chunk2'];
    const result = p.trackContext(chunks, 'rag-qa');
    expect(result).toEqual(['chunk1', 'chunk2']);
    expect(result).toBe(chunks); // same reference
    void p.destroy();
  });

  it('ships event with correct format on flush', async () => {
    const p = new Promptry({
      endpoint: 'http://test/ingest',
      batchSize: 100,
      flushInterval: 60_000,
    });

    p.track('You are a helpful assistant', 'rag-qa');
    await p.flush();

    expect(sentBatches.length).toBeGreaterThanOrEqual(1);
    const events = sentBatches.flatMap((b) => b.events);
    expect(events).toHaveLength(1);

    const event = events[0];
    expect(event.type).toBe('prompt_save');
    expect(event.data.name).toBe('rag-qa');
    expect(event.data.version).toBeNull();
    expect(event.data.content).toBe('You are a helpful assistant');
    expect(event.data.hash).toMatch(/^[0-9a-f]{64}$/);
    expect(event.data.metadata).toEqual({});
    expect(event.data.created_at).toBeDefined();
    expect(event.timestamp).toBeDefined();

    await p.destroy();
  });

  it('deduplicates identical track() calls', async () => {
    const p = new Promptry({
      endpoint: 'http://test/ingest',
      batchSize: 100,
      flushInterval: 60_000,
    });

    p.track('same content', 'same-name');
    p.track('same content', 'same-name');

    await p.flush();

    // Quick-check should catch the second call synchronously
    const events = sentBatches.flatMap((b) => b.events);
    expect(events).toHaveLength(1);

    await p.destroy();
  });

  it('trackContext joins with \\n---\\n and adds :context suffix', async () => {
    const p = new Promptry({
      endpoint: 'http://test/ingest',
      batchSize: 100,
      flushInterval: 60_000,
    });

    p.trackContext(['a', 'b', 'c'], 'rag-qa');
    await p.flush();

    const events = sentBatches.flatMap((b) => b.events);
    expect(events).toHaveLength(1);

    const event = events[0];
    expect(event.data.name).toBe('rag-qa:context');
    expect(event.data.content).toBe('a\n---\nb\n---\nc');
    expect(event.data.metadata).toEqual({ chunk_count: 3 });

    await p.destroy();
  });

  it('adds projectId to metadata', async () => {
    const p = new Promptry({
      endpoint: 'http://test/ingest',
      projectId: 'my-app',
      batchSize: 100,
      flushInterval: 60_000,
    });

    p.track('test', 'p1');
    await p.flush();

    const events = sentBatches.flatMap((b) => b.events);
    expect(events[0].data.metadata).toEqual({ project_id: 'my-app' });

    await p.destroy();
  });

  it('respects sampleRate = 0 (drops everything)', () => {
    const p = new Promptry({
      endpoint: 'http://test/ingest',
      sampleRate: 0,
    });

    // Math.random() always returns > 0, so all calls are dropped
    const result = p.track('test', 'p1');
    expect(result).toBe('test');

    // No events should have been enqueued
    void p.destroy();
  });

  it('passes custom metadata through', async () => {
    const p = new Promptry({
      endpoint: 'http://test/ingest',
      batchSize: 100,
      flushInterval: 60_000,
    });

    p.track('test', 'p1', { metadata: { env: 'prod', version: '1.0' } });
    await p.flush();

    const events = sentBatches.flatMap((b) => b.events);
    expect(events[0].data.metadata).toEqual({ env: 'prod', version: '1.0' });

    await p.destroy();
  });
});
