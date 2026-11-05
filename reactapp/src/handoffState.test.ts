import { describe, it, expect } from 'vitest';
import { parseHandoff } from './handoffState';

const ID = '3f2a9c1e-5b7d-4e8f-9a0b-1c2d3e4f5a6b';

describe('parseHandoff', () => {
  it('returns null when the page was not opened from FIMbench', () => {
    expect(parseHandoff('')).toBeNull();
    expect(parseHandoff(`?upload_id=${ID}`)).toBeNull();
  });

  it('yields the staged upload and its display name', () => {
    expect(parseHandoff(`?upload_id=${ID}&from=fimbench&benchmark_name=site+42`)).toEqual({
      uploadId: ID, name: 'site 42', error: null,
    });
  });

  it('falls back to a generic name when none was sent', () => {
    expect(parseHandoff(`?from=fimbench&upload_id=${ID}`)?.name).toBe('benchmark from FIMbench');
  });

  it('maps each backend error code to a message', () => {
    for (const code of ['bad_url', 'not_allowed_host', 'too_large', 'not_a_tiff', 'unreachable', 'storage']) {
      const s = parseHandoff(`?from=fimbench&error=${code}`);
      expect(s?.uploadId).toBeNull();
      expect(s?.error).toMatch(/\S/);
    }
    expect(parseHandoff('?from=fimbench&error=not_a_tiff')?.error).toMatch(/GeoTIFF/);
  });

  it('still names an unknown error code', () => {
    expect(parseHandoff('?from=fimbench&error=weird')?.error).toContain('weird');
  });

  it('treats a missing or malformed upload id as an error', () => {
    expect(parseHandoff('?from=fimbench')?.error).toMatch(/valid upload/);
    expect(parseHandoff('?from=fimbench&upload_id=../etc')?.error).toMatch(/valid upload/);
  });
});
