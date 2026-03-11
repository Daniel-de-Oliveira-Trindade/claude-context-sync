// Shared TypeScript interfaces for claude-context-sync VSCode extension
// Compatible with CLI v0.5.0 output format

export interface SessionEntry {
  sessionId: string;
  firstPrompt: string;
  messageCount: number;
  created: string;
  modified: string;
  projectDir: string;
}

export interface BundleVersion {
  letter: string;    // "a", "b", "c", ...
  timestamp: string; // "2026-03-07 09:15"
  filename: string;
  isLatest: boolean;
}

export interface BundleGroup {
  index: number;
  sessionPrefix: string;  // first 8 chars of session UUID
  projectFolder: string;
  firstPrompt: string;
  versions: BundleVersion[];
}

export interface DeviceEntry {
  deviceId: string;
  user: string;
  home: string;
  projects: string;
  claudeDir: string;
  isCurrent: boolean;
}

export interface CliResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  timedOut: boolean;
}

export interface CliLocation {
  path: string;
  version: string;
  bundled?: boolean;
}

export interface SessionsIndex {
  sessions: SessionIndexEntry[];
}

export interface SessionIndexEntry {
  sessionId: string;
  firstPrompt?: string;
  messageCount?: number;
  created?: string;
  modified?: string;
  projectPath?: string;
}
