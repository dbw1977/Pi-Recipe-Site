import type { BackupStatus } from '../api';
import { daysSince } from './format';

export const OVERDUE_AFTER_DAYS = 9; // a weekly backup that's 2+ days late needs a look

export interface BackupHealth {
  ok: boolean;
  text: string;
}

/** One line answering "are my backups OK?" for the admin help panel. */
export function backupHealth(status: BackupStatus, now: number = Date.now()): BackupHealth {
  const s = status.settings;
  const entries = [
    { label: 'Folder', on: s.local_enabled, last: status.local },
    { label: 'Google Drive', on: s.drive_enabled, last: status.drive },
  ];

  // A destination whose latest try failed is the most important thing to say.
  for (const e of entries) {
    if (e.on && e.last && e.last.ok !== 1) {
      return { ok: false, text: `${e.label} backup failed: ${e.last.message}` };
    }
  }
  const okTimes = entries
    .map((e) => e.last)
    .filter((l) => l && l.ok === 1)
    .map((l) => daysSince(l!.created_at, now))
    .filter((d): d is number => d != null);
  if (okTimes.length === 0) return { ok: false, text: 'No backup has been made yet' };

  const age = Math.min(...okTimes);
  const when = age === 0 ? 'today' : age === 1 ? 'yesterday' : `${age} days ago`;
  if (s.enabled && age > OVERDUE_AFTER_DAYS) return { ok: false, text: `Last backup ${when} — overdue` };
  if (!s.enabled) return { ok: true, text: `Last backup ${when} (automatic weekly backups are off)` };
  return { ok: true, text: `Last backup ${when}` };
}
