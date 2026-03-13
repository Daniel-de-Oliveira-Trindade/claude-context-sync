import * as cp from 'child_process';
import * as vscode from 'vscode';
import { CliResult } from '../types';
import { getDefaultRepo } from '../config/settings';

export class CliRunner {
  constructor(
    private cliPath: string,
    private outputChannel: vscode.OutputChannel
  ) {}

  updatePath(newPath: string): void {
    this.cliPath = newPath;
  }

  /** Inject --repo <url> after the subcommand when a defaultRepo is configured and not already present. */
  private injectRepo(args: string[]): string[] {
    const repo = getDefaultRepo();
    if (!repo || args.includes('--repo')) { return args; }
    // Only inject --repo for commands that accept it
    const REPO_COMMANDS = ['sync-push', 'sync-pull', 'sync-list', 'repo'];
    if (!REPO_COMMANDS.includes(args[0])) { return args; }
    // Insert after the subcommand (first arg)
    return [args[0], '--repo', repo, ...args.slice(1)];
  }

  async run(
    args: string[],
    options?: {
      cwd?: string;
      onLine?: (line: string) => void;
      timeoutMs?: number;
    }
  ): Promise<CliResult> {
    args = this.injectRepo(args);
    return new Promise((resolve) => {
      const timeout = options?.timeoutMs ?? 60_000;
      let timedOut = false;
      let stdout = '';
      let stderr = '';
      let lineBuffer = '';

      this.outputChannel.appendLine(`\n> ${this.cliPath} ${args.join(' ')}`);

      const child = cp.spawn(this.cliPath, args, {
        cwd: options?.cwd,
        shell: false,
        windowsHide: true,
        env: process.env
      });

      const timer = setTimeout(() => {
        timedOut = true;
        child.kill();
      }, timeout);

      const processChunk = (chunk: string, isStderr: boolean) => {
        lineBuffer += chunk;
        const parts = lineBuffer.split('\n');
        lineBuffer = parts.pop() ?? '';
        for (const line of parts) {
          const trimmed = line.trimEnd();
          if (isStderr) {
            this.outputChannel.appendLine(`[stderr] ${trimmed}`);
          } else {
            this.outputChannel.appendLine(trimmed);
            options?.onLine?.(trimmed);
          }
        }
      };

      child.stdout.setEncoding('utf8');
      child.stdout.on('data', (data: string) => {
        stdout += data;
        processChunk(data, false);
      });

      child.stderr.setEncoding('utf8');
      child.stderr.on('data', (data: string) => {
        stderr += data;
        processChunk(data, true);
      });

      child.on('close', (code) => {
        clearTimeout(timer);
        // flush remaining buffer
        if (lineBuffer.trim()) {
          this.outputChannel.appendLine(lineBuffer.trimEnd());
          options?.onLine?.(lineBuffer.trimEnd());
        }
        // stdout takes precedence: if stdout has content, treat as success regardless of stderr
        const effectiveCode = (code ?? 1);
        this.outputChannel.appendLine(`[exit: ${effectiveCode}]`);
        resolve({
          exitCode: effectiveCode,
          stdout,
          stderr,
          timedOut
        });
      });

      child.on('error', (err) => {
        clearTimeout(timer);
        this.outputChannel.appendLine(`[error] ${err.message}`);
        resolve({ exitCode: 1, stdout, stderr: err.message, timedOut: false });
      });
    });
  }

  /** Opens an integrated terminal and sends the command — for interactive prompts (e.g. crypto-setup) */
  spawnInTerminal(args: string[], terminalName = 'Claude Sync'): void {
    const terminal = vscode.window.createTerminal(terminalName);
    terminal.show();
    terminal.sendText(`"${this.cliPath}" ${args.map(a => `"${a}"`).join(' ')}`);
  }
}
