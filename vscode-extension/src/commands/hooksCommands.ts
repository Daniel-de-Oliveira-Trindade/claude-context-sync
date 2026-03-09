import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';

export function registerHooksCommands(
  context: vscode.ExtensionContext,
  runner: CliRunner
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.hooksInstall', async () => {
      const confirm = await vscode.window.showWarningMessage(
        'Claude Sync: Auto-sync hooks are experimental and may not work reliably on Windows. Install anyway?',
        'Install',
        'Cancel'
      );
      if (confirm !== 'Install') { return; }

      const result = await runner.run(['hooks-install', '--force']);
      if (result.exitCode === 0) {
        vscode.window.showInformationMessage(
          'Claude Sync: Hooks installed. Sessions will sync automatically on open/close.'
        );
      } else {
        vscode.window.showErrorMessage('Claude Sync: Failed to install hooks. Check output log.');
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.hooksUninstall', async () => {
      const result = await runner.run(['hooks-uninstall']);
      if (result.exitCode === 0) {
        vscode.window.showInformationMessage('Claude Sync: Hooks removed.');
      } else {
        vscode.window.showErrorMessage('Claude Sync: Failed to remove hooks. Check output log.');
      }
    })
  );
}
