import * as cp from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { CliLocation } from '../types';

const EXE_NAME = process.platform === 'win32' ? 'claude-sync.exe' : 'claude-sync';

function probe(candidate: string): CliLocation | null {
  try {
    const result = cp.spawnSync(candidate, ['--version'], {
      timeout: 5000,
      encoding: 'utf8',
      windowsHide: true
    });
    if (result.status === 0 && result.stdout) {
      const version = result.stdout.trim().split('\n')[0] ?? 'unknown';
      return { path: candidate, version };
    }
  } catch {
    // not found or not executable
  }
  return null;
}

function globPythonScripts(): string[] {
  const candidates: string[] = [];
  const localAppData = process.env['LOCALAPPDATA'] ?? '';
  const appData = process.env['APPDATA'] ?? '';
  const home = os.homedir();

  const bases = [
    path.join(localAppData, 'Programs', 'Python'),
    path.join(localAppData, 'Programs'),
    path.join(appData, 'Python'),
    path.join(home, 'AppData', 'Local', 'Programs', 'Python'),
    path.join(home, 'AppData', 'Roaming', 'Python'),
  ];

  for (const base of bases) {
    if (!fs.existsSync(base)) { continue; }
    try {
      const entries = fs.readdirSync(base);
      for (const entry of entries) {
        if (entry.toLowerCase().startsWith('python')) {
          const scripts = path.join(base, entry, 'Scripts', EXE_NAME);
          if (fs.existsSync(scripts)) {
            candidates.push(scripts);
          }
        }
      }
    } catch {
      // skip unreadable dirs
    }
  }

  // pip --user install path (no version subfolder)
  const userScripts = path.join(appData, 'Python', 'Scripts', EXE_NAME);
  if (fs.existsSync(userScripts)) {
    candidates.push(userScripts);
  }

  return candidates;
}

function searchPath(): string[] {
  const pathEnv = process.env['PATH'] ?? '';
  const sep = process.platform === 'win32' ? ';' : ':';
  const candidates: string[] = [];
  for (const dir of pathEnv.split(sep)) {
    const full = path.join(dir.trim(), EXE_NAME);
    if (fs.existsSync(full)) {
      candidates.push(full);
    }
  }
  return candidates;
}

function searchVenv(workspacePath?: string): string[] {
  if (!workspacePath) { return []; }
  const candidates = [
    path.join(workspacePath, '.venv', 'Scripts', EXE_NAME),
    path.join(workspacePath, 'venv', 'Scripts', EXE_NAME),
    path.join(workspacePath, '.venv', 'bin', EXE_NAME),
    path.join(workspacePath, 'venv', 'bin', EXE_NAME),
  ];
  return candidates.filter(c => fs.existsSync(c));
}

export async function detectCli(
  settingOverride?: string,
  workspacePath?: string
): Promise<CliLocation | null> {
  // 1. Explicit setting
  if (settingOverride && settingOverride.trim()) {
    const loc = probe(settingOverride.trim());
    if (loc) { return loc; }
  }

  // 2. PATH
  for (const candidate of searchPath()) {
    const loc = probe(candidate);
    if (loc) { return loc; }
  }

  // 3. Python Scripts directories (Windows)
  if (process.platform === 'win32') {
    for (const candidate of globPythonScripts()) {
      const loc = probe(candidate);
      if (loc) { return loc; }
    }
  }

  // 4. Virtual env in workspace
  for (const candidate of searchVenv(workspacePath)) {
    const loc = probe(candidate);
    if (loc) { return loc; }
  }

  return null;
}
