import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { SessionTreeProvider } from '../tree/sessionTreeProvider';
import { StatusBarManager } from '../ui/statusBar';
import { BackupNode } from '../tree/treeNodes';
import { withCliProgress } from '../ui/progressReporter';

export function registerRestoreBackupCommand(
  context: vscode.ExtensionContext,
  runner: CliRunner,
  localTree: SessionTreeProvider,
  statusBar: StatusBarManager,
  outputChannel: vscode.OutputChannel
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.restoreBackup', async (node?: BackupNode) => {
      if (!node) { return; }

      const label = node.backup.timestampDisplay;
      const project = node.backup.projectFolder || '(root)';
      const confirm = await vscode.window.showWarningMessage(
        `Restore backup from ${label} (project: ${project})?\n\nThe session will be restored to its original project folder. Open that folder in Claude Code afterwards to resume it.`,
        { modal: true },
        'Restore'
      );
      if (confirm !== 'Restore') { return; }

      // No --project-path override: importer uses the path stored in the bundle metadata,
      // which means the session goes back to its original project folder.
      const args = ['import', node.backup.fullPath, '--force'];
      statusBar.setState('syncing', 'Restoring backup...');

      try {
        const result = await withCliProgress('Claude Sync: Restoring backup...', async (progress) => {
          return runner.run(args, {
            onLine: (line) => {
              if (line.includes('Importing') || line.includes('imported')) {
                progress.report({ message: 'Importing session...' });
              } else if (line.includes('[SUCCESS]') || line.includes('[OK]')) {
                progress.report({ message: 'Done!' });
              }
            }
          });
        });

        const success = result.exitCode === 0 ||
          result.stdout.includes('[SUCCESS]') ||
          result.stdout.includes('imported successfully') ||
          result.stdout.includes('Session imported');

        if (success) {
          statusBar.setState('success', 'Backup restored');
          vscode.window.showInformationMessage(
            `Claude Sync: Backup from ${label} restored to project "${project}". Open that folder in Claude Code to resume the session.`
          );
          localTree.refresh();
        } else {
          const errMsg = result.stdout.split('\n').filter(l => l.includes('[ERROR]')).pop()
            || result.stderr.split('\n').filter(Boolean).pop()
            || 'Unknown error';
          statusBar.setState('error', errMsg);
          const action = await vscode.window.showErrorMessage(
            `Claude Sync: Restore failed — ${errMsg}`,
            'Show Output'
          );
          if (action === 'Show Output') { outputChannel.show(); }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setState('error', msg);
        vscode.window.showErrorMessage(`Claude Sync: Restore error — ${msg}`);
      }
    })
  );
}
