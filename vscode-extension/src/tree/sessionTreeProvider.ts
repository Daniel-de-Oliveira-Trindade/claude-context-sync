import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { parseListOutput } from '../cli/outputParser';
import { SessionEntry } from '../types';
import { ProjectNode, SessionNode, TreeNode } from './treeNodes';

export class SessionTreeProvider implements vscode.TreeDataProvider<TreeNode> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeNode | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private sessions: SessionEntry[] = [];
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
      return element.sessions.map(s => new SessionNode(s));
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
