import * as vscode from 'vscode';
import { detectCli } from './cli/cliLocator';
import { CliRunner } from './cli/cliRunner';
import { SessionTreeProvider } from './tree/sessionTreeProvider';
import { RemoteTreeProvider } from './tree/remoteTreeProvider';
import { StatusBarManager } from './ui/statusBar';
import { registerPushCommand } from './commands/pushCommand';
import { registerPullCommand } from './commands/pullCommand';
import { registerConfigCommands } from './commands/configCommands';
import { registerHooksCommands } from './commands/hooksCommands';
import { registerRestoreBackupCommand } from './commands/restoreBackupCommand';
import { getCliPath, isSetupCompleted } from './config/settings';

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const outputChannel = vscode.window.createOutputChannel('Claude Sync');
  context.subscriptions.push(outputChannel);

  // Detect CLI
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const cliLocation = await detectCli(getCliPath(), workspace);

  if (!cliLocation) {
    vscode.window.showWarningMessage(
      'Claude Sync: claude-sync CLI not found. ' +
      'Install it with "pip install -e ." or set the path in settings.',
      'Open Settings'
    ).then(action => {
      if (action === 'Open Settings') {
        vscode.commands.executeCommand(
          'workbench.action.openSettings',
          'claudeContextSync.cliPath'
        );
      }
    });
  }

  const cliPath = cliLocation?.path ?? 'claude-sync';
  outputChannel.appendLine(`Claude Sync activated. CLI: ${cliPath} ${cliLocation?.version ?? '(not found)'}`);

  const runner = new CliRunner(cliPath, outputChannel);

  // Tree providers
  const localTree = new SessionTreeProvider(runner);
  const remoteTree = new RemoteTreeProvider(runner);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('claudeSyncLocal', localTree),
    vscode.window.registerTreeDataProvider('claudeSyncRemote', remoteTree)
  );

  // Status bar
  const statusBar = new StatusBarManager(context);

  // Register all commands
  registerPushCommand(context, runner, localTree, statusBar, outputChannel);
  registerPullCommand(context, runner, remoteTree, statusBar, outputChannel);
  registerConfigCommands(context, runner);
  registerHooksCommands(context, runner);
  registerRestoreBackupCommand(context, runner, localTree, statusBar, outputChannel);

  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.refreshLocal', () => localTree.refresh()),
    vscode.commands.registerCommand('claudeContextSync.refreshRemote', () => remoteTree.refresh()),
    vscode.commands.registerCommand('claudeContextSync.showOutput', () => outputChannel.show()),
    vscode.commands.registerCommand('claudeContextSync.openSetupWizard', () => {
      vscode.window.showInformationMessage(
        'Claude Sync: Setup Wizard coming in Phase 2. Use Command Palette to configure settings.',
        'Open Settings'
      ).then(action => {
        if (action === 'Open Settings') {
          vscode.commands.executeCommand('workbench.action.openSettings', 'claudeContextSync');
        }
      });
    })
  );

  // Auto-refresh local sessions on activation
  localTree.refresh();
  // Always show remote bundles from local filesystem immediately (no git pull)
  remoteTree.loadLocal();

  // Auto-refresh on window focus if enabled
  context.subscriptions.push(
    vscode.window.onDidChangeWindowState(state => {
      if (state.focused) {
        const cfg = vscode.workspace.getConfiguration('claudeContextSync');
        if (cfg.get<boolean>('autoRefreshOnFocus', true)) {
          localTree.refresh();
        }
        if (cfg.get<boolean>('autoFetchRemoteOnFocus', false)) {
          remoteTree.refresh();
        } else {
          remoteTree.loadLocal();
        }
      }
    })
  );

  // Prompt wizard if first time
  if (!isSetupCompleted()) {
    vscode.window.showInformationMessage(
      'Claude Sync: Welcome! Run the Setup Wizard to configure your sync settings.',
      'Open Settings',
      'Dismiss'
    ).then(action => {
      if (action === 'Open Settings') {
        vscode.commands.executeCommand('workbench.action.openSettings', 'claudeContextSync');
      }
    });
  }
}

export function deactivate(): void {
  // nothing to clean up beyond subscriptions
}
