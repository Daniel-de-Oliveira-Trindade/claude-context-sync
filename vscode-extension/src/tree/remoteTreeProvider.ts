import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { readLocalBundles, groupBundles } from '../cli/bundleReader';
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

  /** Load bundles from local filesystem only (no git pull). Called on activation. */
  loadLocal(): void {
    try {
      const bundles = readLocalBundles();
      this.groups = groupBundles(bundles);
    } catch {
      this.groups = [];
    }
    this.loading = false;
    this.loaded = true;
    this._onDidChangeTreeData.fire();
  }

  /** Pull from remote then reload. Called when user clicks refresh. */
  refresh(): void {
    this.loading = true;
    this.loaded = false;
    this._onDidChangeTreeData.fire();
    this.loadRemote();
  }

  private async loadRemote(): Promise<void> {
    const syncDir = require('path').join(require('os').homedir(), '.claude-sync-git');
    const fs = require('fs') as typeof import('fs');

    if (fs.existsSync(require('path').join(syncDir, '.git'))) {
      // Pull latest from remote — ignore errors (offline, auth issues)
      await this.runner.run(['sync-list'], { timeoutMs: 30_000 }).catch(() => undefined);
    }

    // Read bundles directly from local filesystem (no exe needed)
    try {
      const bundles = readLocalBundles();
      this.groups = groupBundles(bundles);
    } catch (err) {
      this.groups = [];
      vscode.window.showErrorMessage(
        `Claude Sync: Could not read local bundle directory. ${err instanceof Error ? err.message : err}`
      );
    }

    this.loading = false;
    this.loaded = true;
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
      const key = g.projectFolder || '(root)';
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
    super('Fetching bundles...', vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon('loading~spin');
  }
}

class NotLoadedNode extends vscode.TreeItem {
  constructor() {
    super('Click ↺ to load remote bundles', vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon('info');
    this.command = {
      command: 'claudeContextSync.refreshRemote',
      title: 'Refresh Remote'
    };
  }
}
