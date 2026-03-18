import { describe, it, expect } from 'vitest';
import { sha256 } from '../src/hash';

describe('sha256', () => {
  // Pre-computed with Python: hashlib.sha256(s.encode("utf-8")).hexdigest()
  it('matches Python hashlib.sha256 for empty string', async () => {
    expect(await sha256('')).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );
  });

  it('matches Python hashlib.sha256 for "hello"', async () => {
    expect(await sha256('hello')).toBe(
      '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
    );
  });

  it('matches Python hashlib.sha256 for a prompt string', async () => {
    expect(await sha256('You are a helpful assistant')).toBe(
      '11ec99cfa6e6f58a352f4aee9cdb6d96e2eca86d437158f18efc6d4fe5909b07',
    );
  });

  it('handles unicode (CJK)', async () => {
    expect(await sha256('\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8')).toBe(
      '4b09dffafb42f5b069c66a0283523c0e85c9af2a5530a8fbd541b3e5f9a9c7cd',
    );
  });

  it('returns 64-char hex string', async () => {
    const h = await sha256('test');
    expect(h).toMatch(/^[0-9a-f]{64}$/);
  });

  it('is deterministic', async () => {
    const a = await sha256('deterministic');
    const b = await sha256('deterministic');
    expect(a).toBe(b);
  });
});
