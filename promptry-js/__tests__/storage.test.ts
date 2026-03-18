import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryStore } from '../src/storage';
import type { TelemetryEvent } from '../src/types';

function makeEvent(name: string): TelemetryEvent {
  return {
    type: 'prompt_save',
    data: {
      name,
      version: null,
      content: 'test',
      hash: 'abc123',
      metadata: {},
      created_at: new Date().toISOString(),
    },
    timestamp: new Date().toISOString(),
  };
}

describe('MemoryStore', () => {
  let store: MemoryStore;

  beforeEach(() => {
    store = new MemoryStore();
  });

  it('starts empty', () => {
    expect(store.load()).toEqual([]);
  });

  it('saves and loads events', () => {
    const e = makeEvent('test');
    store.save([e]);
    const loaded = store.load();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].data.name).toBe('test');
  });

  it('accumulates events across saves', () => {
    store.save([makeEvent('a')]);
    store.save([makeEvent('b')]);
    expect(store.load()).toHaveLength(2);
  });

  it('caps at 100 events', () => {
    const batch = Array.from({ length: 120 }, (_, i) =>
      makeEvent(`e${i}`),
    );
    store.save(batch);
    const loaded = store.load();
    expect(loaded).toHaveLength(100);
    // Should keep the last 100 (slice(-100))
    expect(loaded[0].data.name).toBe('e20');
    expect(loaded[99].data.name).toBe('e119');
  });

  it('clear removes all', () => {
    store.save([makeEvent('a')]);
    store.clear();
    expect(store.load()).toEqual([]);
  });

  it('load returns a copy', () => {
    store.save([makeEvent('a')]);
    const a = store.load();
    const b = store.load();
    expect(a).not.toBe(b);
    expect(a).toEqual(b);
  });
});
