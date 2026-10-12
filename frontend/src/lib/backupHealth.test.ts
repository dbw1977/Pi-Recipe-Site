import { describe, expect, it } from 'vitest';
import type { BackupEntry, BackupSettings, BackupStatus } from '../api';
import { backupHealth } from './backupHealth';
import { count, daysSince, fmtSize } from './format';

const NOW = Date.parse('2026-10-20T12:00:00Z');
const DAY = 86_400_000;
const at = (daysAgo: number) => new Date(NOW - daysAgo * DAY - 3600_000).toISOString().replace('Z', '').slice(0, 19);

const entry = (daysAgo: number, ok = 1, message = 'ok'): BackupEntry => ({
  kind: 'local', target: '', ok, message, size_bytes: 1000, created_at: at(daysAgo),
});

function status(over: Partial<BackupSettings> = {}, local: BackupEntry | null = null, drive: BackupEntry | null = null): BackupStatus {
  return {
    settings: { enabled: true, local_enabled: true, local_dir: '/x', drive_enabled: false, drive_folder_name: 'F',
      include_media: true, day: 6, hour: 3, ...over },
    day_names: [], local, drive, running: false, kind: null, step: '', restore_result: null, local_backup: null,
    next_run: null, media: null, local_same_disk: false, google: { configured: true, authorized: true },
  };
}

describe('backupHealth', () => {
  it('says so when nothing has ever been backed up', () => {
    expect(backupHealth(status(), NOW)).toEqual({ ok: false, text: 'No backup has been made yet' });
  });
  it('is fine after a recent success', () => {
    expect(backupHealth(status({}, entry(0)), NOW)).toEqual({ ok: true, text: 'Last backup today' });
    expect(backupHealth(status({}, entry(1)), NOW).text).toBe('Last backup yesterday');
    expect(backupHealth(status({}, entry(5)), NOW).text).toBe('Last backup 5 days ago');
  });
  it('flags a weekly backup that is overdue', () => {
    expect(backupHealth(status({}, entry(12)), NOW)).toEqual({ ok: false, text: 'Last backup 12 days ago — overdue' });
  });
  it('does not call an old backup overdue when weekly is off, but mentions it', () => {
    const h = backupHealth(status({ enabled: false }, entry(30)), NOW);
    expect(h.ok).toBe(true);
    expect(h.text).toContain('weekly backups are off');
  });
  it('reports a failed destination ahead of an older success', () => {
    const h = backupHealth(status({ drive_enabled: true }, entry(0), entry(0, 0, 'Google is not connected')), NOW);
    expect(h).toEqual({ ok: false, text: 'Google Drive backup failed: Google is not connected' });
  });
  it('ignores a failure on a destination that is switched off', () => {
    expect(backupHealth(status({ drive_enabled: false }, entry(0), entry(0, 0, 'old failure')), NOW).ok).toBe(true);
  });
  it('uses the freshest success across destinations', () => {
    expect(backupHealth(status({ drive_enabled: true }, entry(8), entry(1)), NOW).text).toBe('Last backup yesterday');
  });
});

describe('format helpers', () => {
  it('daysSince treats API timestamps as UTC and never goes negative', () => {
    expect(daysSince(at(3), NOW)).toBe(3);
    expect(daysSince('2999-01-01T00:00:00', NOW)).toBe(0);
    expect(daysSince(undefined, NOW)).toBeNull();
    expect(daysSince('garbage', NOW)).toBeNull();
  });
  it('fmtSize picks a sensible unit', () => {
    expect(fmtSize(null)).toBe('');
    expect(fmtSize(512)).toBe('512 B');
    expect(fmtSize(2048)).toBe('2 KB');
    expect(fmtSize(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(fmtSize(3 * 1024 ** 3)).toBe('3.00 GB');
  });
  it('count is singular for one', () => {
    expect(count(1, 'place')).toBe('1 place');
    expect(count(0, 'place')).toBe('0 places');
    expect(count(2, 'photo')).toBe('2 photos');
  });
});
