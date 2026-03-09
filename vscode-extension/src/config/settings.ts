import * as vscode from 'vscode';

const SECTION = 'claudeContextSync';

function cfg() {
  return vscode.workspace.getConfiguration(SECTION);
}

export function getCliPath(): string {
  return cfg().get<string>('cliPath', '');
}

export function getDefaultRepo(): string {
  return cfg().get<string>('defaultRepo', '');
}

export function getDeviceName(): string {
  return cfg().get<string>('deviceName', '');
}

export function isEncryptionEnabled(): boolean {
  return cfg().get<boolean>('encryptionEnabled', false);
}

export function getProjectsPath(): string {
  return cfg().get<string>('projectsPath', '');
}

export function isAutoRefreshOnFocus(): boolean {
  return cfg().get<boolean>('autoRefreshOnFocus', true);
}

export function isSetupCompleted(): boolean {
  return cfg().get<boolean>('setupCompleted', false);
}

export async function setCliPath(value: string): Promise<void> {
  await cfg().update('cliPath', value, vscode.ConfigurationTarget.Global);
}

export async function setDefaultRepo(value: string): Promise<void> {
  await cfg().update('defaultRepo', value, vscode.ConfigurationTarget.Global);
}

export async function setDeviceName(value: string): Promise<void> {
  await cfg().update('deviceName', value, vscode.ConfigurationTarget.Global);
}

export async function setEncryptionEnabled(value: boolean): Promise<void> {
  await cfg().update('encryptionEnabled', value, vscode.ConfigurationTarget.Global);
}

export async function setProjectsPath(value: string): Promise<void> {
  await cfg().update('projectsPath', value, vscode.ConfigurationTarget.Global);
}

export async function setSetupCompleted(value: boolean): Promise<void> {
  await cfg().update('setupCompleted', value, vscode.ConfigurationTarget.Global);
}
