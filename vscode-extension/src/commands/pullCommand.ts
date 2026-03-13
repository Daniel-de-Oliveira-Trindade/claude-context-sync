import * as path from 'path';
import * as vscode from 'vscode';
import { CliRunner } from '../cli/cliRunner';
import { StatusBarManager } from '../ui/statusBar';
import { RemoteTreeProvider } from '../tree/remoteTreeProvider';
import { RemoteSessionNode, RemoteVersionNode } from '../tree/treeNodes';
import { withCliProgress } from '../ui/progressReporter';
import { BundleGroup } from '../types';

function getWorkspacePath(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

/**
 * Return the last folder name of a path.
 * "/Users/alice/projetos/my-app" → "my-app"
 * "C:\\Users\\fsf\\Documents\\projetos\\cadeeu" → "cadeeu"
 */
function lastSegment(p: string): string {
  return path.basename(p);
}

/**
 * Check whether the bundle's projectFolder (e.g. "cadeeu") looks like it
 * belongs to the currently open workspace folder (e.g. "C:\\…\\projetos\\cadeeu").
 *
 * We compare the last path segment of the workspace path against the bundle's
 * project folder name (which is already just the folder name in the git repo).
 */
function bundleMatchesWorkspace(bundleProjectFolder: string, workspacePath: string): boolean {
  if (!bundleProjectFolder || !workspacePath) { return true; } // can't tell → assume OK
  const wsFolder = lastSegment(workspacePath).toLowerCase();
  const bundleFolder = bundleProjectFolder.toLowerCase();
  // The bundle folder might be "plataforma-cadeeu" (nested) or just "cadeeu"
  return wsFolder === bundleFolder || bundleFolder.endsWith('-' + wsFolder) || bundleFolder.endsWith('/' + wsFolder);
}

/**
 * Ask the user to choose a project path when the bundle doesn't match the
 * current workspace. Returns the path to use, or undefined to cancel.
 */
async function askProjectPath(
  bundleProjectFolder: string,
  currentWorkspace: string | undefined
): Promise<string | undefined> {
  const items: vscode.QuickPickItem[] = [];

  if (currentWorkspace) {
    items.push({
      label: `$(folder-active) Use current folder`,
      description: currentWorkspace,
      detail: `Import into the currently open workspace (may not match the original project)`
    });
  }

  items.push({
    label: `$(folder-opened) Choose a folder…`,
    description: '',
    detail: `Browse to the correct project folder for "${bundleProjectFolder}"`
  });

  items.push({
    label: `$(warning) Import anyway (current folder)`,
    description: currentWorkspace ?? '(no workspace open)',
    detail: `Force import into the current workspace without validation`
  });

  const picked = await vscode.window.showQuickPick(items, {
    title: `Claude Sync: Project mismatch`,
    placeHolder: `Bundle is from "${bundleProjectFolder}" but current folder is different. Where to import?`
  });

  if (!picked) { return undefined; }

  if (picked.label.includes('Choose a folder')) {
    const uris = await vscode.window.showOpenDialog({
      canSelectFiles: false,
      canSelectFolders: true,
      canSelectMany: false,
      title: `Select project folder for "${bundleProjectFolder}"`
    });
    return uris?.[0]?.fsPath;
  }

  // "Use current folder" or "Import anyway"
  return currentWorkspace;
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
      let bundleProjectFolder: string | undefined;
      let exactBundleFile: string | undefined;

      if (node instanceof RemoteVersionNode) {
        sessionPrefix = node.sessionPrefix;
        exactBundleFile = node.version.filename;
        // find the group to get projectFolder
        const group = remoteTree.getGroups().find(g => g.sessionPrefix === sessionPrefix);
        bundleProjectFolder = group?.projectFolder;
      } else if (node instanceof RemoteSessionNode) {
        sessionPrefix = node.group.sessionPrefix;
        bundleProjectFolder = node.group.projectFolder;
        // Always pull the latest version when clicking the session node
        exactBundleFile = node.group.versions[0]?.filename;
      } else {
        // Command Palette: show QuickPick from remote tree data
        const groups = remoteTree.getGroups();
        if (groups.length > 0) {
          // Flatten all versions into a single list for easy picking
          const items: (vscode.QuickPickItem & { prefix: string; projectFolder: string })[] = [];
          for (const g of groups) {
            for (const v of g.versions) {
              items.push({
                label: `$(history) ${g.sessionPrefix}  [${v.letter}]  ${v.timestamp}${v.isLatest ? '  ← latest' : ''}`,
                description: g.projectFolder,
                detail: g.firstPrompt?.slice(0, 80),
                prefix: g.sessionPrefix,
                projectFolder: g.projectFolder
              });
            }
          }
          const picked = await vscode.window.showQuickPick(items, {
            title: 'Claude Sync: Pull Session',
            placeHolder: 'Select a session to pull (load remote first if empty)'
          });
          sessionPrefix = picked?.prefix;
          bundleProjectFolder = picked?.projectFolder;
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

      // Determine target project path, with mismatch detection
      const workspacePath = getWorkspacePath();
      let targetProjectPath = workspacePath;

      if (bundleProjectFolder && workspacePath) {
        const matches = bundleMatchesWorkspace(bundleProjectFolder, workspacePath);
        if (!matches) {
          const chosen = await askProjectPath(bundleProjectFolder, workspacePath);
          if (chosen === undefined) { return; } // user cancelled
          targetProjectPath = chosen;
        }
      } else if (!workspacePath) {
        // No workspace open at all — ask the user to pick a folder
        const uris = await vscode.window.showOpenDialog({
          canSelectFiles: false,
          canSelectFolders: true,
          canSelectMany: false,
          title: 'Claude Sync: Select the project folder to import the session into'
        });
        if (!uris?.[0]) {
          vscode.window.showWarningMessage('Claude Sync: No folder selected. Pull cancelled.');
          return;
        }
        targetProjectPath = uris[0].fsPath;
      }

      const args = ['sync-pull', sessionPrefix, '--force'];
      if (exactBundleFile) {
        args.push('--bundle-file', exactBundleFile);
      }
      if (targetProjectPath) {
        args.push('--project-path', targetProjectPath);
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

        const success = result.exitCode === 0 ||
          result.stdout.includes('[SUCCESS]') ||
          result.stdout.includes('imported successfully') ||
          result.stdout.includes('Session imported');

        if (success) {
          statusBar.setState('success', 'Session pulled successfully');
          const whereMsg = targetProjectPath
            ? ` into "${lastSegment(targetProjectPath)}"`
            : '';
          vscode.window.showInformationMessage(
            `Claude Sync: Session pulled${whereMsg}. Open that project folder in Claude Code to resume it.`
          );
        } else {
          const errMsg = result.stdout.split('\n').filter(l => l.includes('[ERROR]')).pop()
            || result.stderr.split('\n').filter(Boolean).pop()
            || lastLine
            || 'Unknown error';
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
