/** All public interfaces for promptry. */

export interface PromptryOptions {
  /** Remote ingest endpoint URL. */
  endpoint: string;
  /** Optional API key (sent as Bearer token). */
  apiKey?: string;
  /** Optional project identifier, added to event metadata. */
  projectId?: string;
  /** Number of events before auto-flush. Default 10. */
  batchSize?: number;
  /** Milliseconds between timer flushes. Default 5000. */
  flushInterval?: number;
  /** Fraction of calls that actually ship (0–1). Default 1.0. */
  sampleRate?: number;
}

export interface TrackOptions {
  metadata?: Record<string, unknown>;
}

export interface TelemetryEvent {
  type: 'prompt_save';
  data: {
    name: string;
    version: null;
    content: string;
    hash: string;
    metadata: Record<string, unknown>;
    created_at: string;
  };
  timestamp: string;
}

export interface EventBatch {
  events: TelemetryEvent[];
}

export interface OfflineStore {
  load(): TelemetryEvent[];
  save(events: TelemetryEvent[]): void;
  clear(): void;
}
