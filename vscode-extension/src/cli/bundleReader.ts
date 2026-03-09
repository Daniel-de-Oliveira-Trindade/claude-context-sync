/**
 * bundleReader.ts
 *
 * Reads bundles directly from the local git-sync directory (~/.claude-sync-git/)
 * without invoking the CLI exe. This avoids the Windows subprocess stderr leak
 * that causes `sync-list` to fail when called via Node.js child_process.
 *
 * Compatible with CLI v0.5.0 bundle layout:
 *   ~/.claude-sync-git/<project-folder>/<sessionId>_<YYYYMMDD-HHmmss>.bundle.gz[.enc]
 *   ~/.claude-sync-git/<sessionId>_<timestamp>.bundle.gz   (legacy flat root)
 */

import * as fs from 'fs';
import * as nodePath from 'path';
import * as os from 'os';
import { BundleGroup, BundleVersion } from '../types';

const BUNDLE_EXTS = ['.bundle', '.bundle.gz', '.bundle.gz.enc'];
const TIMESTAMP_RE = /_(\d{8}-\d{6})/;
const SESSION_RE = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;

export interface LocalBundle {
  filename: string;
  sessionId: string;
  sessionPrefix: string;
  projectFolder: string;
  timestamp: string;       // "YYYYMMDD-HHmmss" or ""
  timestampDisplay: string; // "2026-03-08 18:43" or ""
  fullPath: string;
}

function isBundleFile(name: string): boolean {
  return BUNDLE_EXTS.some(ext => name.endsWith(ext));
}

function parseTimestamp(ts: string): string {
  // "20260308-184320" → "08/03/2026 18:43"
  if (ts.length < 13) { return ts; }
  return `${ts.slice(6, 8)}/${ts.slice(4, 6)}/${ts.slice(0, 4)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}`;
}

function parseBundle(filename: string, fullPath: string, projectFolder: string): LocalBundle | null {
  const sessionMatch = filename.match(SESSION_RE);
  if (!sessionMatch) { return null; }

  const sessionId = sessionMatch[1];
  const tsMatch = filename.match(TIMESTAMP_RE);
  const timestamp = tsMatch ? tsMatch[1] : '';

  return {
    filename,
    sessionId,
    sessionPrefix: sessionId.slice(0, 8),
    projectFolder,
    timestamp,
    timestampDisplay: timestamp ? parseTimestamp(timestamp) : '(no date)',
    fullPath
  };
}

export function readLocalBundles(): LocalBundle[] {
  const syncDir = nodePath.join(os.homedir(), '.claude-sync-git');
  const bundles: LocalBundle[] = [];

  if (!fs.existsSync(syncDir)) { return bundles; }

  let entries: string[];
  try {
    entries = fs.readdirSync(syncDir);
  } catch {
    return bundles;
  }

  for (const entry of entries) {
    if (entry === 'backups' || entry === '.git') { continue; }

    const entryPath = nodePath.join(syncDir, entry);
    let stat: fs.Stats;
    try { stat = fs.statSync(entryPath); } catch { continue; }

    if (stat.isDirectory()) {
      let subEntries: string[];
      try { subEntries = fs.readdirSync(entryPath); } catch { continue; }
      for (const sub of subEntries) {
        if (!isBundleFile(sub)) { continue; }
        const b = parseBundle(sub, nodePath.join(entryPath, sub), entry);
        if (b) { bundles.push(b); }
      }
    } else if (isBundleFile(entry)) {
      const b = parseBundle(entry, entryPath, '');
      if (b) { bundles.push(b); }
    }
  }

  return bundles;
}

export interface LocalBackup {
  filename: string;
  sessionPrefix: string;
  projectFolder: string;
  timestamp: string;        // raw "YYYYMMDD-HHmmss"
  timestampDisplay: string; // "DD/MM/YYYY HH:MM"
  fullPath: string;
}

/** Read local backups from ~/.claude-sync-git/backups/<project>/<file> */
export function readLocalBackups(): LocalBackup[] {
  const backupsDir = nodePath.join(os.homedir(), '.claude-sync-git', 'backups');
  const backups: LocalBackup[] = [];

  if (!fs.existsSync(backupsDir)) { return backups; }

  let projects: string[];
  try { projects = fs.readdirSync(backupsDir); } catch { return backups; }

  for (const project of projects) {
    const projectPath = nodePath.join(backupsDir, project);
    let stat: fs.Stats;
    try { stat = fs.statSync(projectPath); } catch { continue; }
    if (!stat.isDirectory()) { continue; }

    let files: string[];
    try { files = fs.readdirSync(projectPath); } catch { continue; }

    for (const file of files) {
      if (!isBundleFile(file)) { continue; }
      const tsMatch = file.match(TIMESTAMP_RE);
      const prefixMatch = file.match(/^([0-9a-f]{8})/i);
      if (!prefixMatch) { continue; }

      const timestamp = tsMatch ? tsMatch[1] : '';
      backups.push({
        filename: file,
        sessionPrefix: prefixMatch[1],
        projectFolder: project,
        timestamp,
        timestampDisplay: timestamp ? parseTimestamp(timestamp) : '(no date)',
        fullPath: nodePath.join(projectPath, file)
      });
    }
  }

  return backups;
}

export function groupBundles(bundles: LocalBundle[]): BundleGroup[] {
  // Group by sessionPrefix
  const map = new Map<string, LocalBundle[]>();
  for (const b of bundles) {
    if (!map.has(b.sessionPrefix)) { map.set(b.sessionPrefix, []); }
    map.get(b.sessionPrefix)!.push(b);
  }

  const groups: BundleGroup[] = [];
  let index = 1;

  for (const [prefix, items] of map) {
    // Sort by timestamp descending (latest first)
    items.sort((a, b) => b.timestamp.localeCompare(a.timestamp));

    const versions: BundleVersion[] = items.map((b, i) => ({
      letter: String.fromCharCode(97 + i), // a, b, c...
      timestamp: b.timestampDisplay,
      filename: b.filename,
      isLatest: i === 0
    }));

    const projectFolder = items.find(b => b.projectFolder)?.projectFolder ?? '';

    groups.push({
      index: index++,
      sessionPrefix: prefix,
      projectFolder,
      firstPrompt: '',  // not available from filesystem — would need to read bundle JSON
      versions
    });
  }

  // Sort by latest timestamp descending
  groups.sort((a, b) => {
    const ta = a.versions[0]?.timestamp ?? '';
    const tb = b.versions[0]?.timestamp ?? '';
    return tb.localeCompare(ta);
  });

  return groups;
}
