import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { CliRunner } from '../cli/cliRunner';
import { StatusBarManager } from '../ui/statusBar';
import { SessionTreeProvider } from '../tree/sessionTreeProvider';
import { SessionNode } from '../tree/treeNodes';
import { withCliProgress } from '../ui/progressReporter';
import { isEncryptionEnabled } from '../config/settings';
import { SessionIndexEntry } from '../types';

function getWorkspacePath(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

/** Encode workspace path the same way Claude Code does for project dirs.
 *  e.g. "C:\Users\Daniel\Documents\projetos\my-app" → "c--users-daniel-documents-projetos-my-app"
 */
function encodeProjectPath(p: string): string {
  return p.toLowerCase().replace(/[\\/:]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
}

interface SessionCandidate {
  sessionId: string;
  firstPrompt: string;
  modified: string;
}

async function detectCurrentSessions(workspacePath: string): Promise<SessionCandidate[]> {
  const claudeDir = path.join(os.homedir(), '.claude');
  const projectsDir = path.join(claudeDir, 'projects');
  const encoded = encodeProjectPath(workspacePath);

  // Try to find the project dir
  let projectDir: string | undefined;
  try {
    const entries = fs.readdirSync(projectsDir);
    projectDir = entries
      .map(e => path.join(projectsDir, e))
      .find(e => path.basename(e).toLowerCase() === encoded);
  } catch {
    return [];
  }

  if (!projectDir) { return []; }

  // Read sessions-index.json
  const indexPath = path.join(projectDir, 'sessions-index.json');
  try {
    const raw = fs.readFileSync(indexPath, 'utf8');
    const index = JSON.parse(raw) as { sessions?: SessionIndexEntry[] };
    const sessions = index.sessions ?? [];
    return sessions
      .sort((a, b) => (b.modified ?? '').localeCompare(a.modified ?? ''))
      .map(s => ({
        sessionId: s.sessionId,
        firstPrompt: s.firstPrompt ?? '',
        modified: s.modified ?? ''
      }));
  } catch {
    return [];
  }
}

export function registerPushCommand(
  context: vscode.ExtensionContext,
  runner: CliRunner,
  localTree: SessionTreeProvider,
  statusBar: StatusBarManager,
  outputChannel: vscode.OutputChannel
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.push', async (node?: SessionNode) => {
      let sessionId: string | undefined;

      if (node instanceof SessionNode) {
        sessionId = node.sessionId;
      } else {
        const workspacePath = getWorkspacePath();
        if (workspacePath) {
          const candidates = await detectCurrentSessions(workspacePath);
          if (candidates.length > 0) {
            const items = candidates.map(c => ({
              label: c.sessionId.slice(0, 8),
              description: c.modified.slice(0, 10),
              detail: c.firstPrompt?.slice(0, 80),
              sessionId: c.sessionId
            }));
            const picked = await vscode.window.showQuickPick(items, {
              title: 'Claude Sync: Select session to push',
              placeHolder: 'Choose a session'
            });
            sessionId = picked?.sessionId;
          }
        }

        if (!sessionId) {
          sessionId = await vscode.window.showInputBox({
            title: 'Claude Sync: Push Session',
            prompt: 'Enter session UUID (or prefix)',
            placeHolder: '097f3474-8974-4405-98c0-b70d4bf920d5'
          });
        }
      }

      if (!sessionId) { return; }

      const args = ['sync-push', '--session', sessionId, '--compress'];
      if (isEncryptionEnabled()) { args.push('--encrypt'); }

      statusBar.setState('syncing', 'Pushing...');
      let lastLine = '';

      try {
        const result = await withCliProgress('Claude Sync: Pushing session...', async (progress) => {
          return runner.run(args, {
            cwd: getWorkspacePath(),
            onLine: (line) => {
              lastLine = line;
              if (line.includes('Exporting')) {
                progress.report({ message: 'Exporting session...' });
              } else if (line.includes('Pushing') || line.includes('push')) {
                progress.report({ message: 'Pushing to git...' });
              } else if (line.includes('[SUCCESS]') || line.includes('[OK]')) {
                progress.report({ message: 'Done!' });
              }
            }
          });
        });

        if (result.exitCode === 0) {
          statusBar.setState('success', 'Session pushed successfully');
          vscode.window.showInformationMessage('Claude Sync: Session pushed successfully.');
          localTree.refresh();
        } else {
          const errMsg = lastLine || result.stderr.split('\n').filter(Boolean).pop() || 'Unknown error';
          statusBar.setState('error', errMsg);
          const action = await vscode.window.showErrorMessage(
            `Claude Sync: Push failed — ${errMsg}`,
            'Show Output'
          );
          if (action === 'Show Output') { outputChannel.show(); }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        statusBar.setState('error', msg);
        vscode.window.showErrorMessage(`Claude Sync: Push error — ${msg}`);
      }
    })
  );
}
