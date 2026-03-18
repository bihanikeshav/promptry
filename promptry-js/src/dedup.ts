/** Bounded dedup cache keyed by "name:hash". */

const MAX_SIZE = 10_000;

export class DedupCache {
  private _map = new Map<string, true>();

  has(key: string): boolean {
    return this._map.has(key);
  }

  add(key: string): void {
    if (this._map.size >= MAX_SIZE) {
      // Evict oldest half (matches Python registry.py eviction)
      const keys = Array.from(this._map.keys());
      const half = keys.length >> 1;
      for (let i = 0; i < half; i++) {
        this._map.delete(keys[i]);
      }
    }
    this._map.set(key, true);
  }

  get size(): number {
    return this._map.size;
  }

  clear(): void {
    this._map.clear();
  }
}
