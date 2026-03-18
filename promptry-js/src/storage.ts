/** Offline event persistence: localStorage (browser) / in-memory (Node). */

import { isBrowser } from './env';
import type { OfflineStore, TelemetryEvent } from './types';

const STORAGE_KEY = 'promptry:offline_queue';
const MAX_EVENTS = 100;

class LocalStorageStore implements OfflineStore {
  load(): TelemetryEvent[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  save(events: TelemetryEvent[]): void {
    try {
      const existing = this.load();
      const merged = existing.concat(events).slice(-MAX_EVENTS);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
    } catch {
      // localStorage may be disabled (incognito, iframes, quota)
    }
  }

  clear(): void {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }
}

class MemoryStore implements OfflineStore {
  private _events: TelemetryEvent[] = [];

  load(): TelemetryEvent[] {
    return [...this._events];
  }

  save(events: TelemetryEvent[]): void {
    this._events = this._events.concat(events).slice(-MAX_EVENTS);
  }

  clear(): void {
    this._events = [];
  }
}

export function createOfflineStore(): OfflineStore {
  return isBrowser() ? new LocalStorageStore() : new MemoryStore();
}

export { MemoryStore, LocalStorageStore };
