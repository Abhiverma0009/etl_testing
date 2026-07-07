/**
 * Spawns the existing `etl-test` Python CLI (in the repo's .venv) as a child
 * process. This is a direct `python.exe` binary call — unaffected by the
 * locked-down VM's `.cmd` restriction. Server-only.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { PYTHON_EXE, REPO_ROOT } from "./paths";

export interface EtlSpawnOptions {
  args: string[];
  env?: Record<string, string>;
  progress?: boolean; // set ETL_TEST_PROGRESS_JSON=1 for JSON-lines progress on stdout
}

export function spawnEtl({ args, env, progress }: EtlSpawnOptions): ChildProcess {
  const childEnv: NodeJS.ProcessEnv = { ...process.env, ...(env ?? {}) };
  if (progress) childEnv.ETL_TEST_PROGRESS_JSON = "1";
  return spawn(PYTHON_EXE, ["-m", "etl_test.cli", ...args], {
    cwd: REPO_ROOT,
    env: childEnv,
    windowsHide: true,
  });
}

export interface EtlResult {
  code: number;
  stdout: string;
  stderr: string;
}

/** Run a one-shot CLI command and collect its output (no streaming). */
export function runEtl(args: string[], env?: Record<string, string>): Promise<EtlResult> {
  return new Promise((resolve) => {
    const child = spawnEtl({ args, env });
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (d) => (stdout += d.toString()));
    child.stderr?.on("data", (d) => (stderr += d.toString()));
    child.on("close", (code) => resolve({ code: code ?? -1, stdout, stderr }));
    child.on("error", (err) =>
      resolve({ code: -1, stdout, stderr: stderr + String(err) }),
    );
  });
}
