# promptry-js

Lightweight JS/TS client for [promptry](../README.md) telemetry. Ships prompt tracking events to your ingest endpoint using the exact same event format as the Python `RemoteStorage` backend.

Zero runtime dependencies. ~5KB minified. Works in browsers and Node 18+.

## Install

```bash
npm install promptry-js
```

## Usage

### Class API

```typescript
import { Promptry } from 'promptry-js';

const p = new Promptry({
  endpoint: 'https://your-server.com/ingest',
  apiKey: 'pk_...',        // optional
  projectId: 'my-app',     // optional
  batchSize: 10,            // default 10
  flushInterval: 5000,      // default 5000ms
  sampleRate: 1.0,          // default 1.0
});

// Returns content unchanged, ships event in background
const prompt = p.track('You are a helpful assistant...', 'rag-qa');

// Returns chunks unchanged, joins internally, name gets ":context" suffix
const chunks = p.trackContext(retrievedChunks, 'rag-qa');

await p.flush();    // manual flush
await p.destroy();  // flush + teardown
```

### Singleton API

```typescript
import { init, track, trackContext, flush } from 'promptry-js';

init({ endpoint: 'https://your-server.com/ingest' });

const prompt = track(systemPrompt, 'rag-qa');
const chunks = trackContext(retrievedChunks, 'rag-qa');

await flush();
```

## Event Format

Events match the Python `RemoteStorage._ship_batch` format exactly:

```json
{
  "events": [
    {
      "type": "prompt_save",
      "data": {
        "name": "rag-qa",
        "version": null,
        "content": "You are...",
        "hash": "e3b0c44...",
        "metadata": {},
        "created_at": "2026-03-09T14:23:45.123Z"
      },
      "timestamp": "2026-03-09T14:23:45.123Z"
    }
  ]
}
```

## Development

```bash
npm install
npm run build
npm test
```
