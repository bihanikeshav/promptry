/** Event queue, flush timer, batch splitting, offline fallback. */

import { isBrowser, isNode } from './env';
import { sendBatch, type TransportOptions } from './transport';
import { createOfflineStore } from './storage';
import type { OfflineStore, TelemetryEvent } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */
const _g = globalThis as any;

export interface BatcherOptions {
  transport: TransportOptions;
  batchSize: number;
  flushInterval: number;
}

export class Batcher {
  private _queue: TelemetryEvent[] = [];
  private _timer: ReturnType<typeof setInterval> | null = null;
  private _store: OfflineStore;
  private _transport: TransportOptions;
  private _batchSize: number;
  private _unloadBound: (() => void) | null = null;
  private _beforeExitBound: (() => void) | null = null;

  constructor(opts: BatcherOptions) {
    this._transport = opts.transport;
    this._batchSize = opts.batchSize;
    this._store = createOfflineStore();

    // Restore any offline events from last session
    const offline = this._store.load();
    if (offline.length > 0) {
      this._queue.push(...offline);
      this._store.clear();
    }

    this._timer = setInterval(() => {
      void this.flush();
    }, opts.flushInterval);

    // Unref timer in Node so it doesn't keep the process alive
    if (isNode() && this._timer && typeof (this._timer as any).unref === 'function') {
      (this._timer as any).unref();
    }

    this._registerUnload();
  }

  enqueue(event: TelemetryEvent): void {
    this._queue.push(event);
    if (this._queue.length >= this._batchSize) {
      void this.flush();
    }
  }

  async flush(): Promise<void> {
    if (this._queue.length === 0) return;

    const events = this._queue.splice(0);
    const ok = await sendBatch({ events }, this._transport);

    if (!ok) {
      this._store.save(events);
    }
  }

  async destroy(): Promise<void> {
    if (this._timer !== null) {
      clearInterval(this._timer);
      this._timer = null;
    }
    await this.flush();
    this._unregisterUnload();
  }

  get pending(): number {
    return this._queue.length;
  }

  private _registerUnload(): void {
    if (isBrowser() && typeof _g.addEventListener === 'function') {
      this._unloadBound = () => this._sendBeacon();
      _g.addEventListener('pagehide', this._unloadBound);
    }

    if (isNode() && typeof _g.process?.on === 'function') {
      this._beforeExitBound = () => {
        void this.flush();
      };
      _g.process.on('beforeExit', this._beforeExitBound);
    }
  }

  private _unregisterUnload(): void {
    if (this._unloadBound && typeof _g.removeEventListener === 'function') {
      _g.removeEventListener('pagehide', this._unloadBound);
      this._unloadBound = null;
    }
    if (this._beforeExitBound && typeof _g.process?.removeListener === 'function') {
      _g.process.removeListener('beforeExit', this._beforeExitBound);
      this._beforeExitBound = null;
    }
  }

  private _sendBeacon(): void {
    if (this._queue.length === 0) return;

    const events = this._queue.splice(0);
    const body = JSON.stringify({ events });

    if (typeof navigator?.sendBeacon === 'function') {
      const blob = new Blob([body], { type: 'application/json' });
      const sent = navigator.sendBeacon(this._transport.endpoint, blob);
      if (!sent) {
        this._store.save(events);
      }
    } else {
      this._store.save(events);
    }
  }
}
