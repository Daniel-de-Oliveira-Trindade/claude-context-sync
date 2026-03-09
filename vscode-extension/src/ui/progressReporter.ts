import * as vscode from 'vscode';

export async function withCliProgress<T>(
  title: string,
  fn: (progress: vscode.Progress<{ message?: string }>) => Promise<T>
): Promise<T> {
  return vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title,
      cancellable: false
    },
    fn
  );
}
