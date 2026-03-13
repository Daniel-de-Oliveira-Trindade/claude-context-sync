import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { parseListOutput } from '../cli/outputParser';
import { readLocalBackups, LocalBackup } from '../cli/bundleReader';
import { SessionEntry } from '../types';
import { ProjectNode, SessionNode, BackupProjectNode, BackupNode, TreeNode } from './treeNodes';

export class SessionTreeProvider implements vscode.TreeDataProvider<TreeNode> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeNode | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private sessions: SessionEntry[] = [];
  // Map: sessionPrefix -> backups sorted newest-first
  private backupsByPrefix = new Map<string, LocalBackup[]>();
  private loading = false;

  constructor(private runner: CliRunner) {}

  refresh(): void {
    this.loading = true;
    this._onDidChangeTreeData.fire();
    this.loadSessions();
  }

  private async loadSessions(): Promise<void> {
    const result = await this.runner.run(['list', '--limit', '200']);
    this.loading = false;
    if (result.exitCode === 0) {
      this.sessions = parseListOutput(result.stdout);
    } else {
      this.sessions = [];
      // Don't show error on first load if there are genuinely no sessions yet
      const errText = (result.stderr || result.stdout).trim();
      if (errText && !errText.includes('No sessions found') && !errText.includes('No projects found')) {
        vscode.window.showWarningMessage(`Claude Sync: Could not load local sessions. Check the Output panel for details.`);
      }
    }

    // Load local backups from filesystem (no CLI needed)
    this.backupsByPrefix.clear();
    const backups = readLocalBackups();
    for (const b of backups) {
      if (!this.backupsByPrefix.has(b.sessionPrefix)) {
        this.backupsByPrefix.set(b.sessionPrefix, []);
      }
      this.backupsByPrefix.get(b.sessionPrefix)!.push(b);
    }
    // Sort each group newest-first
    for (const list of this.backupsByPrefix.values()) {
      list.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
    }

    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TreeNode): vscode.TreeItem {
    return element;
  }

  getChildren(element?: TreeNode): vscode.ProviderResult<TreeNode[]> {
    if (this.loading) {
      return [new LoadingNode()];
    }

    if (!element) {
      return this.buildProjectNodes();
    }

    if (element instanceof ProjectNode) {
      return element.sessions.map(s => {
        const prefix = s.sessionId.slice(0, 8);
        const hasBackups = (this.backupsByPrefix.get(prefix) ?? []).length > 0;
        return new SessionNode(s, hasBackups);
      });
    }

    // Session node → show backup project folder as child if backups exist
    if (element instanceof SessionNode) {
      const prefix = element.sessionId.slice(0, 8);
      const backups = this.backupsByPrefix.get(prefix) ?? [];
      if (backups.length === 0) { return []; }
      // Group by project folder
      const byProject = new Map<string, LocalBackup[]>();
      for (const b of backups) {
        const key = b.projectFolder || '(root)';
        if (!byProject.has(key)) { byProject.set(key, []); }
        byProject.get(key)!.push(b);
      }
      return [...byProject.entries()].map(
        ([proj, list]) => new BackupProjectNode(proj, list)
      );
    }

    if (element instanceof BackupProjectNode) {
      const backups = element.backups;
      // The most recent backup = "em uso" (active), rest are older
      return backups.map((b, i) => new BackupNode(b, i === 0));
    }

    return [];
  }

  private buildProjectNodes(): ProjectNode[] {
    const map = new Map<string, SessionEntry[]>();
    for (const s of this.sessions) {
      const dir = s.projectDir || 'unknown';
      if (!map.has(dir)) { map.set(dir, []); }
      map.get(dir)!.push(s);
    }

    const nodes: ProjectNode[] = [];
    for (const [dir, sessions] of map) {
      nodes.push(new ProjectNode(dir, sessions));
    }

    nodes.sort((a, b) => a.label!.toString().localeCompare(b.label!.toString()));
    return nodes;
  }
}

class LoadingNode extends vscode.TreeItem {
  constructor() {
    super('Loading...', vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon('loading~spin');
  }
}
