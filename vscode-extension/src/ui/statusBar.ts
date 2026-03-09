import * as vscode from 'vscode';

type StatusState = 'idle' | 'syncing' | 'success' | 'error';

export class StatusBarManager {
  private item: vscode.StatusBarItem;
  private resetTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(context: vscode.ExtensionContext) {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      100
    );
    this.item.command = 'claudeContextSync.push';
    context.subscriptions.push(this.item);
    this.setState('idle');
    this.item.show();
  }

  setState(state: StatusState, detail?: string): void {
    if (this.resetTimer) {
      clearTimeout(this.resetTimer);
      this.resetTimer = undefined;
    }

    switch (state) {
      case 'idle':
        this.item.text = '$(sync) Claude Sync';
        this.item.tooltip = 'Click to push current session';
        this.item.command = 'claudeContextSync.push';
        this.item.backgroundColor = undefined;
        break;

      case 'syncing':
        this.item.text = `$(sync~spin) ${detail ?? 'Syncing...'}`;
        this.item.tooltip = 'Sync in progress...';
        this.item.command = 'claudeContextSync.showOutput';
        this.item.backgroundColor = undefined;
        break;

      case 'success':
        this.item.text = '$(check) Synced';
        this.item.tooltip = detail ?? 'Sync completed successfully';
        this.item.command = 'claudeContextSync.showOutput';
        this.item.backgroundColor = undefined;
        this.resetTimer = setTimeout(() => this.setState('idle'), 4000);
        break;

      case 'error':
        this.item.text = '$(error) Sync failed';
        this.item.tooltip = detail ?? 'Sync failed — click to see output';
        this.item.command = 'claudeContextSync.showOutput';
        this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
        break;
    }
  }
}
