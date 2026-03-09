import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { parseListOutput } from '../cli/outputParser';
import { BundleGroup } from '../types';
import { RemoteProjectNode, RemoteSessionNode, RemoteVersionNode, TreeNode } from './treeNodes';

export class RemoteTreeProvider implements vscode.TreeDataProvider<TreeNode> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeNode | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private groups: BundleGroup[] = [];
  private loading = false;
  private loaded = false;

  constructor(private runner: CliRunner) {}

  getGroups(): BundleGroup[] {
    return this.groups;
  }

  refresh(): void {
    this.loading = true;
    this.loaded = false;
    this._onDidChangeTreeData.fire();
    this.loadRemote();
  }

  private async loadRemote(): Promise<void> {
    // sync-list output goes to stdout (exit 0); progress lines go to stderr
    const result = await this.runner.run(['sync-list'], { timeoutMs: 60_000 });
    this.loading = false;
    this.loaded = true;

    // Use stdout if available, fall back to combined output for parsing
    const textToParse = result.stdout || (result.stdout + result.stderr);

    if (result.exitCode === 0 && result.stdout.includes('Session ID:')) {
      const sessions = parseListOutput(textToParse);
      this.groups = sessions.map((s, i) => ({
        index: i + 1,
        sessionPrefix: s.sessionId.slice(0, 8),
        projectFolder: s.projectDir,
        firstPrompt: s.firstPrompt,
        versions: [{
          letter: 'a',
          timestamp: s.modified?.slice(0, 16).replace('T', ' ') ?? '',
          filename: `${s.sessionId}.bundle`,
          isLatest: true
        }]
      }));
    } else if (result.exitCode !== 0) {
      this.groups = [];
      vscode.window.showErrorMessage(
        `Claude Sync: Failed to fetch remote bundles (exit ${result.exitCode}). See "Claude Sync" output channel.`
      );
    } else {
      // exit 0 but no sessions found
      this.groups = [];
    }
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TreeNode): vscode.TreeItem {
    return element;
  }

  getChildren(element?: TreeNode): vscode.ProviderResult<TreeNode[]> {
    if (!this.loaded && !this.loading) {
      return [new NotLoadedNode()];
    }

    if (this.loading) {
      return [new LoadingNode()];
    }

    if (!element) {
      return this.buildProjectNodes();
    }

    if (element instanceof RemoteProjectNode) {
      return element.groups.map(g => new RemoteSessionNode(g));
    }

    if (element instanceof RemoteSessionNode) {
      return element.group.versions.map(v => new RemoteVersionNode(v, element.group.sessionPrefix));
    }

    return [];
  }

  private buildProjectNodes(): RemoteProjectNode[] {
    const map = new Map<string, BundleGroup[]>();
    for (const g of this.groups) {
      const key = g.projectFolder || 'unknown';
      if (!map.has(key)) { map.set(key, []); }
      map.get(key)!.push(g);
    }

    const nodes: RemoteProjectNode[] = [];
    for (const [folder, groups] of map) {
      nodes.push(new RemoteProjectNode(folder, groups));
    }
    return nodes;
  }
}

class LoadingNode extends vscode.TreeItem {
  constructor() {
    super('Fetching from remote...', vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon('loading~spin');
  }
}

class NotLoadedNode extends vscode.TreeItem {
  constructor() {
    super('Click refresh to load remote bundles', vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon('info');
    this.command = {
      command: 'claudeContextSync.refreshRemote',
      title: 'Refresh Remote'
    };
  }
}
