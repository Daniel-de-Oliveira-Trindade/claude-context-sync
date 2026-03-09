import * as vscode from 'vscode';
import { SessionEntry, BundleGroup, BundleVersion } from '../types';
import { LocalBackup } from '../cli/bundleReader';
import { decodeProjectDir, formatDate } from '../cli/outputParser';

// ─────────────────────────────────────────────
// Local tree nodes
// ─────────────────────────────────────────────

export class ProjectNode extends vscode.TreeItem {
  readonly sessions: SessionEntry[];
  readonly projectDir: string;

  constructor(projectDir: string, sessions: SessionEntry[]) {
    const label = decodeProjectDir(projectDir);
    super(label, vscode.TreeItemCollapsibleState.Expanded);
    this.projectDir = projectDir;
    this.sessions = sessions;
    this.description = `${sessions.length} session${sessions.length !== 1 ? 's' : ''}`;
    this.iconPath = new vscode.ThemeIcon('folder');
    this.contextValue = 'project';
    this.tooltip = projectDir;
  }
}

export class SessionNode extends vscode.TreeItem {
  readonly sessionId: string;
  readonly entry: SessionEntry;

  constructor(entry: SessionEntry, hasBackups: boolean = false) {
    const shortId = entry.sessionId.slice(0, 8);
    const collapsible = hasBackups
      ? vscode.TreeItemCollapsibleState.Collapsed
      : vscode.TreeItemCollapsibleState.None;
    super(shortId, collapsible);
    this.sessionId = entry.sessionId;
    this.entry = entry;
    this.description = formatDate(entry.modified);
    this.tooltip = entry.firstPrompt || entry.sessionId;
    this.iconPath = new vscode.ThemeIcon('comment-discussion');
    this.contextValue = 'session';

    if (entry.firstPrompt) {
      const prompt = entry.firstPrompt.length > 60
        ? entry.firstPrompt.slice(0, 60) + '…'
        : entry.firstPrompt;
      this.label = `${shortId}  — ${prompt}`;
    }
  }
}

// ─────────────────────────────────────────────
// Remote tree nodes
// ─────────────────────────────────────────────

export class RemoteProjectNode extends vscode.TreeItem {
  readonly groups: BundleGroup[];
  readonly projectFolder: string;

  constructor(projectFolder: string, groups: BundleGroup[]) {
    super(projectFolder, vscode.TreeItemCollapsibleState.Expanded);
    this.projectFolder = projectFolder;
    this.groups = groups;
    this.description = `${groups.length} session${groups.length !== 1 ? 's' : ''}`;
    this.iconPath = new vscode.ThemeIcon('repo');
    this.contextValue = 'remoteProject';
  }
}

export class RemoteSessionNode extends vscode.TreeItem {
  readonly group: BundleGroup;

  constructor(group: BundleGroup) {
    const label = group.firstPrompt
      ? `${group.sessionPrefix} — ${group.firstPrompt.slice(0, 50)}${group.firstPrompt.length > 50 ? '…' : ''}`
      : group.sessionPrefix;
    const state = group.versions.length > 1
      ? vscode.TreeItemCollapsibleState.Collapsed
      : vscode.TreeItemCollapsibleState.None;
    super(label, state);
    this.group = group;
    this.description = group.versions[0]?.timestamp ?? '';
    this.tooltip = `${group.sessionPrefix} — ${group.projectFolder}\n${group.firstPrompt}`;
    this.iconPath = new vscode.ThemeIcon('cloud');
    this.contextValue = 'remoteSession';
  }
}

export class RemoteVersionNode extends vscode.TreeItem {
  readonly version: BundleVersion;
  readonly sessionPrefix: string;

  constructor(version: BundleVersion, sessionPrefix: string) {
    const label = `[${version.letter}] ${version.timestamp}${version.isLatest ? '  ← latest' : ''}`;
    super(label, vscode.TreeItemCollapsibleState.None);
    this.version = version;
    this.sessionPrefix = sessionPrefix;
    this.description = version.filename;
    this.tooltip = version.filename;
    this.iconPath = new vscode.ThemeIcon('history');
    this.contextValue = 'remoteVersion';
  }
}

// ─────────────────────────────────────────────
// Backup tree nodes (local backups)
// ─────────────────────────────────────────────

export class BackupProjectNode extends vscode.TreeItem {
  readonly backups: LocalBackup[];
  readonly projectFolder: string;

  constructor(projectFolder: string, backups: LocalBackup[]) {
    super(projectFolder, vscode.TreeItemCollapsibleState.Collapsed);
    this.projectFolder = projectFolder;
    this.backups = backups;
    this.description = `${backups.length} backup${backups.length !== 1 ? 's' : ''}`;
    this.iconPath = new vscode.ThemeIcon('folder');
    this.contextValue = 'backupProject';
  }
}

export class BackupNode extends vscode.TreeItem {
  readonly backup: LocalBackup;
  readonly isActive: boolean;

  constructor(backup: LocalBackup, isActive: boolean) {
    const label = backup.timestampDisplay;
    super(label, vscode.TreeItemCollapsibleState.None);
    this.backup = backup;
    this.isActive = isActive;
    this.description = isActive ? '← em uso' : backup.sessionPrefix;
    this.tooltip = `${backup.filename}\n${backup.fullPath}`;
    this.iconPath = new vscode.ThemeIcon(isActive ? 'check' : 'archive');
    this.contextValue = isActive ? 'backupActive' : 'backup';
  }
}

export type TreeNode = ProjectNode | SessionNode | RemoteProjectNode | RemoteSessionNode | RemoteVersionNode | BackupProjectNode | BackupNode | vscode.TreeItem;
