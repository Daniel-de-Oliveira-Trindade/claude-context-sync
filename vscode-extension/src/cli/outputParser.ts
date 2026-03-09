// outputParser.ts — Pure parsing functions for claude-sync CLI text output
// Compatible with CLI v0.5.0 output format
// NOTE: If the CLI output format changes, update the parsers here.

import { SessionEntry, BundleGroup, BundleVersion, DeviceEntry } from '../types';

// ---------------------------------------------------------------------------
// claude-sync list  (local sessions)
// ---------------------------------------------------------------------------
// Output format:
//   Session ID: <uuid>
//     First prompt: <text>
//     Messages: <n>
//     Created: <iso>
//     Modified: <iso>
//     Project: <encoded-dir-name>

export function parseListOutput(text: string): SessionEntry[] {
  const entries: SessionEntry[] = [];
  let current: Partial<SessionEntry> | null = null;

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trimEnd();

    if (line.startsWith('Session ID:')) {
      if (current?.sessionId) {
        entries.push(current as SessionEntry);
      }
      current = {
        sessionId: line.replace('Session ID:', '').trim(),
        firstPrompt: '',
        messageCount: 0,
        created: '',
        modified: '',
        projectDir: ''
      };
      continue;
    }

    if (!current) { continue; }

    const trimmed = line.trim();
    if (trimmed.startsWith('First prompt:')) {
      current.firstPrompt = trimmed.replace('First prompt:', '').trim();
    } else if (trimmed.startsWith('Messages:')) {
      current.messageCount = parseInt(trimmed.replace('Messages:', '').trim(), 10) || 0;
    } else if (trimmed.startsWith('Created:')) {
      current.created = trimmed.replace('Created:', '').trim();
    } else if (trimmed.startsWith('Modified:')) {
      current.modified = trimmed.replace('Modified:', '').trim();
    } else if (trimmed.startsWith('Project:')) {
      current.projectDir = trimmed.replace('Project:', '').trim();
    }
  }

  if (current?.sessionId) {
    entries.push(current as SessionEntry);
  }

  return entries;
}

// ---------------------------------------------------------------------------
// claude-sync sync-list  (remote bundles)
// ---------------------------------------------------------------------------
// Output format:
//   [N] <prefix8> — <project-folder>  |  <first-prompt>
//       [a] YYYY-MM-DD HH:MM  <filename>  <- latest
//       [b] YYYY-MM-DD HH:MM  <filename>

const GROUP_RE = /^\[(\d+)\]\s+([0-9a-f]{8})\s+[—\-]+\s+(.+?)(?:\s{2,}\|\s{2,}(.*))?$/;
const VERSION_RE = /^\s+\[([a-z])\]\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(\S+)/;

export function parseSyncListOutput(text: string): BundleGroup[] {
  const groups: BundleGroup[] = [];
  let current: BundleGroup | null = null;

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trimEnd();

    const groupMatch = line.match(GROUP_RE);
    if (groupMatch) {
      if (current) { groups.push(current); }
      current = {
        index: parseInt(groupMatch[1], 10),
        sessionPrefix: groupMatch[2],
        projectFolder: groupMatch[3].trim(),
        firstPrompt: groupMatch[4]?.trim() ?? '',
        versions: []
      };
      continue;
    }

    if (!current) { continue; }

    const versionMatch = line.match(VERSION_RE);
    if (versionMatch) {
      const isLatest = line.includes('<- latest');
      current.versions.push({
        letter: versionMatch[1],
        timestamp: versionMatch[2],
        filename: versionMatch[3],
        isLatest
      });
    }
  }

  if (current) { groups.push(current); }

  return groups;
}

// ---------------------------------------------------------------------------
// claude-sync devices
// ---------------------------------------------------------------------------
// Output format:
//   <device-id> * CURRENT   (or just <device-id>)
//     User: <name>
//     Home: <path>
//     Projects: <path>
//     Claude Dir: <path>

export function parseDevicesOutput(text: string): DeviceEntry[] {
  const entries: DeviceEntry[] = [];
  let current: Partial<DeviceEntry> | null = null;

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trimEnd();
    if (!line.trim()) { continue; }

    if (!line.startsWith(' ') && !line.startsWith('\t')) {
      if (current?.deviceId) { entries.push(current as DeviceEntry); }
      const isCurrent = line.includes('CURRENT');
      current = {
        deviceId: line.replace(/\*?\s*CURRENT/, '').trim(),
        user: '',
        home: '',
        projects: '',
        claudeDir: '',
        isCurrent
      };
      continue;
    }

    if (!current) { continue; }
    const trimmed = line.trim();
    if (trimmed.startsWith('User:')) {
      current.user = trimmed.replace('User:', '').trim();
    } else if (trimmed.startsWith('Home:')) {
      current.home = trimmed.replace('Home:', '').trim();
    } else if (trimmed.startsWith('Projects:')) {
      current.projects = trimmed.replace('Projects:', '').trim();
    } else if (trimmed.startsWith('Claude Dir:')) {
      current.claudeDir = trimmed.replace('Claude Dir:', '').trim();
    }
  }

  if (current?.deviceId) { entries.push(current as DeviceEntry); }

  return entries;
}

// ---------------------------------------------------------------------------
// claude-sync repo  (no args — shows current repo)
// ---------------------------------------------------------------------------
// Output: "[OK] Default repository: <url>"  or  "[--] No default repository configured."

export function parseRepoOutput(text: string): string | null {
  for (const line of text.split('\n')) {
    const match = line.match(/Default repository:\s*(.+)/);
    if (match) { return match[1].trim(); }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract human-readable project name from encoded dir name.
 *  "c--Users-Daniel-Documents-projetos-my-app" → "my-app"
 */
export function decodeProjectDir(encodedDir: string): string {
  // The encoding replaces path separators with '-', so we try to recover
  // the last meaningful segment. Common pattern: ends with the project folder name.
  // e.g. "c--users-daniel-documents-projetos-my-project" → "my-project"
  const parts = encodedDir.split('-');
  // Drop leading single chars (drive letter artifacts like "c", "users", etc.)
  // and join from "projetos" onward, or just return the last meaningful chunk.
  const projectosIdx = parts.findIndex(p => p === 'projetos' || p === 'projects' || p === 'documents');
  if (projectosIdx >= 0 && projectosIdx < parts.length - 1) {
    return parts.slice(projectosIdx + 1).join('-');
  }
  // Fallback: return last non-empty segment after splitting on '--'
  const doubleDash = encodedDir.split('--');
  return doubleDash[doubleDash.length - 1] || encodedDir;
}

/** Format ISO date string to a short readable form: "2026-03-07" */
export function formatDate(iso: string): string {
  if (!iso) { return ''; }
  return iso.slice(0, 10);
}
