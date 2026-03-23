import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { isAutoSync, setAutoSync } from '../config/settings';

export function registerAutoSyncCommand(
  context: vscode.ExtensionContext,
  runner: CliRunner,
  autoSyncBar: AutoSyncStatusBar
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.toggleAutoSync', async () => {
      const current = isAutoSync();
      const next = !current;

      if (next) {
        const result = await runner.run(['watch', '--daemon']);
        if (result.exitCode !== 0) {
          vscode.window.showErrorMessage('Claude Sync: Failed to start file watcher. Check output for details.');
          return;
        }
        await setAutoSync(true);
        autoSyncBar.setState(true);
        vscode.window.showInformationMessage('Claude Sync: Auto Sync started — sessions will be pushed automatically.');
      } else {
        await runner.run(['watch', '--stop']);
        await setAutoSync(false);
        autoSyncBar.setState(false);
        vscode.window.showInformationMessage('Claude Sync: Auto Sync stopped.');
      }
    })
  );
}

export class AutoSyncStatusBar {
  private item: vscode.StatusBarItem;

  constructor(context: vscode.ExtensionContext) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
    this.item.command = 'claudeContextSync.toggleAutoSync';
    context.subscriptions.push(this.item);
    this.setState(isAutoSync());
    this.item.show();
  }

  setState(on: boolean): void {
    this.item.text = on ? '$(radio-tower) Auto Sync: ON' : '$(radio-tower) Auto Sync: OFF';
    this.item.tooltip = on ? 'Auto Sync is active — click to stop' : 'Auto Sync is off — click to start';
  }
}
