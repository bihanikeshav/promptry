import { describe, it, expect } from 'vitest';
import { DedupCache } from '../src/dedup';

describe('DedupCache', () => {
  it('has/add works for basic keys', () => {
    const cache = new DedupCache();
    expect(cache.has('a:b')).toBe(false);
    cache.add('a:b');
    expect(cache.has('a:b')).toBe(true);
  });

  it('tracks size', () => {
    const cache = new DedupCache();
    expect(cache.size).toBe(0);
    cache.add('x:1');
    cache.add('x:2');
    expect(cache.size).toBe(2);
  });

  it('clear resets', () => {
    const cache = new DedupCache();
    cache.add('x:1');
    cache.clear();
    expect(cache.size).toBe(0);
    expect(cache.has('x:1')).toBe(false);
  });

  it('evicts oldest half at capacity (10,000)', () => {
    const cache = new DedupCache();

    // Fill to capacity
    for (let i = 0; i < 10_000; i++) {
      cache.add(`k:${i}`);
    }
    expect(cache.size).toBe(10_000);

    // Adding one more triggers eviction of first 5000
    cache.add('k:new');
    expect(cache.size).toBe(5_001); // 5000 kept + 1 new

    // First entries should be gone
    expect(cache.has('k:0')).toBe(false);
    expect(cache.has('k:4999')).toBe(false);

    // Later entries should remain
    expect(cache.has('k:5000')).toBe(true);
    expect(cache.has('k:9999')).toBe(true);
    expect(cache.has('k:new')).toBe(true);
  });

  it('does not duplicate existing keys', () => {
    const cache = new DedupCache();
    cache.add('x:1');
    cache.add('x:1');
    // Map.set overwrites but doesn't increase size for same key
    expect(cache.size).toBe(1);
  });
});
