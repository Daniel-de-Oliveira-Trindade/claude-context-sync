import * as vscode from 'vscode';
import * as os from 'os';
import { CliRunner } from '../cli/cliRunner';
import { setDefaultRepo, setDeviceName, setProjectsPath } from '../config/settings';

export function registerConfigCommands(
  context: vscode.ExtensionContext,
  runner: CliRunner
): void {
  // Set repository URL
  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.setRepo', async () => {
      const url = await vscode.window.showInputBox({
        title: 'Claude Sync: Set Repository URL',
        prompt: 'Enter the Git repository URL for session sync',
        placeHolder: 'git@github.com:user/claude-sessions.git',
        validateInput: (v) => v.trim() ? null : 'URL cannot be empty'
      });
      if (!url) { return; }

      await setDefaultRepo(url.trim());
      const result = await runner.run(['repo', url.trim()]);
      if (result.exitCode === 0) {
        vscode.window.showInformationMessage(`Claude Sync: Repository set to ${url.trim()}`);
      } else {
        vscode.window.showWarningMessage(
          'Claude Sync: URL saved in settings but could not update CLI config. ' +
          'Run "claude-sync repo <url>" manually.'
        );
      }
    })
  );

  // Configure device
  context.subscriptions.push(
    vscode.commands.registerCommand('claudeContextSync.setDevice', async () => {
      const defaultName = process.env['COMPUTERNAME'] ?? os.hostname();
      const deviceId = await vscode.window.showInputBox({
        title: 'Claude Sync: Device Name',
        prompt: 'Enter a name for this device (e.g. desktop, laptop)',
        value: defaultName,
        validateInput: (v) => v.trim() ? null : 'Device name cannot be empty'
      });
      if (!deviceId) { return; }

      const defaultProjects = `${os.homedir()}\\Documents\\projetos`;
      const projectsPath = await vscode.window.showInputBox({
        title: 'Claude Sync: Projects Directory',
        prompt: 'Path to your projects folder',
        value: defaultProjects,
        validateInput: (v) => v.trim() ? null : 'Path cannot be empty'
      });
      if (!projectsPath) { return; }

      await setDeviceName(deviceId.trim());
      await setProjectsPath(projectsPath.trim());

      const args = [
        'config',
        '--device-id', deviceId.trim(),
        '--projects-path', projectsPath.trim(),
        '--set-current'
      ];
      const result = await runner.run(args);
      if (result.exitCode === 0) {
        vscode.window.showInformationMessage(
          `Claude Sync: Device "${deviceId.trim()}" configured successfully.`
        );
      } else {
        vscode.window.showErrorMessage(
          'Claude Sync: Failed to configure device. Check output log.'
        );
      }
    })
  );
}
