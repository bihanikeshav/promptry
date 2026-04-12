import * as vscode from "vscode";
import { execFile } from "child_process";

function getPythonPath(): string {
  const config = vscode.workspace.getConfiguration("promptry");
  return config.get<string>("pythonPath", "python");
}

function runInTerminal(name: string, command: string): void {
  const terminal = vscode.window.createTerminal(name);
  terminal.show();
  terminal.sendText(command);
}

function listSuites(): Promise<string[]> {
  const pythonPath = getPythonPath();
  return new Promise((resolve, reject) => {
    execFile(
      pythonPath,
      ["-m", "promptry", "suites", "--module", "evals"],
      { cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error(stderr || error.message));
          return;
        }
        const suites = stdout
          .split("\n")
          .map((line) => line.trim())
          .filter((line) => line.length > 0);
        resolve(suites);
      }
    );
  });
}

async function runSuite(): Promise<void> {
  let suites: string[];
  try {
    suites = await listSuites();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage(`Failed to list suites: ${message}`);
    return;
  }

  if (suites.length === 0) {
    vscode.window.showWarningMessage("No eval suites found.");
    return;
  }

  const selected = await vscode.window.showQuickPick(suites, {
    placeHolder: "Select an eval suite to run",
  });

  if (!selected) {
    return;
  }

  const pythonPath = getPythonPath();
  runInTerminal(
    `promptry: ${selected}`,
    `${pythonPath} -m promptry run ${selected} --module evals`
  );
}

function doctor(): void {
  const pythonPath = getPythonPath();
  runInTerminal("promptry: doctor", `${pythonPath} -m promptry doctor`);
}

function dashboard(): void {
  const pythonPath = getPythonPath();
  runInTerminal("promptry: dashboard", `${pythonPath} -m promptry dashboard`);
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("promptry.runSuite", runSuite),
    vscode.commands.registerCommand("promptry.doctor", doctor),
    vscode.commands.registerCommand("promptry.dashboard", dashboard)
  );
}

export function deactivate(): void {
  // nothing to clean up
}
