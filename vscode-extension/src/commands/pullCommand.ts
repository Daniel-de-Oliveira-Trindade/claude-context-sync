import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { StatusBarManager } from '../ui/statusBar';
import { RemoteTreeProvider } from '../tree/remoteTreeProvider';
import { RemoteSessionNode, RemoteVersionNode } from '../tree/treeNodes';
import { withCliProgress } from '../ui/progressReporter';

function getWorkspacePath(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

export function registerPullCommand(
  context: vscode.ExtensionContext,
  runner: CliRunner,
  remoteTree: RemoteTreeProvider,
  statusBar: StatusBarManager,
  outputChannel: vscode.OutputChannel
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.pull', async (node?: RemoteSessionNode | RemoteVersionNode) => {
      let sessionPrefix: string | undefined;

      if (node instanceof RemoteVersionNode) {
        sessionPrefix = node.sessionPrefix;
      } else if (node instanceof RemoteSessionNode) {
        sessionPrefix = node.group.sessionPrefix;
      } else {
        // Command Palette: show QuickPick from remote tree data
        const groups = remoteTree.getGroups();
        if (groups.length > 0) {
          // Flatten all versions into a single list for easy picking
          const items: (vscode.QuickPickItem & { prefix: string })[] = [];
          for (const g of groups) {
            for (const v of g.versions) {
              items.push({
                label: `$(history) ${g.sessionPrefix}  [${v.letter}]  ${v.timestamp}${v.isLatest ? '  ← latest' : ''}`,
                description: g.projectFolder,
                detail: g.firstPrompt?.slice(0, 80),
                prefix: g.sessionPrefix
              });
            }
          }
          const picked = await vscode.window.showQuickPick(items, {
            title: 'Claude Sync: Pull Session',
            placeHolder: 'Select a session to pull (load remote first if empty)'
          });
          sessionPrefix = picked?.prefix;
        } else {
          // No remote data loaded yet — ask to refresh or type manually
          const action = await vscode.window.showWarningMessage(
            'Claude Sync: Remote bundles not loaded yet.',
            'Refresh Remote',
            'Enter ID manually'
          );
          if (action === 'Refresh Remote') {
            remoteTree.refresh();
            return;
          }
          sessionPrefix = await vscode.window.showInputBox({
            title: 'Claude Sync: Pull Session',
            prompt: 'Enter session ID prefix (first 8 chars)',
            placeHolder: '097f3474'
          });
        }
      }

      if (!sessionPrefix) { return; }

      const args = ['sync-pull', sessionPrefix, '--force'];
      const workspacePath = getWorkspacePath();
      if (workspacePath) {
        args.push('--project-path', workspacePath);
      }

      statusBar.setState('syncing', 'Pulling...');
      let lastLine = '';

      try {
        const result = await withCliProgress('Claude Sync: Pulling session...', async (progress) => {
          return runner.run(args, {
            onLine: (line) => {
              lastLine = line;
              if (line.includes('Fetching') || line.includes('Cloning')) {
                progress.report({ message: 'Fetching from git...' });
              } else if (line.includes('Importing')) {
                progress.report({ message: 'Importing session...' });
              } else if (line.includes('[SUCCESS]') || line.includes('[OK]')) {
                progress.report({ message: 'Done!' });
              }
            }
          });
        });

        if (result.exitCode === 0) {
          statusBar.setState('success', 'Session pulled successfully');
          vscode.window.showInformationMessage(
            'Claude Sync: Session pulled. You can now resume it in Claude Code.'
          );
        } else {
          const errMsg = lastLine || result.stderr.split('\n').filter(Boolean).pop() || 'Unknown error';
          statusBar.setState('error', errMsg);
          const action = await vscode.window.showErrorMessage(
            `Claude Sync: Pull failed — ${errMsg}`,
            'Show Output'
          );
          if (action === 'Show Output') { outputChannel.show(); }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setState('error', msg);
        vscode.window.showErrorMessage(`Claude Sync: Pull error — ${msg}`);
      }
    })
  );
}
