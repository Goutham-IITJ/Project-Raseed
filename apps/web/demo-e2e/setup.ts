import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { backendEnv } from "../playwright.demo.config";

export default function setup() {
  const root = resolve(__dirname, "../../..");
  const python = resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  const options = { cwd: root, env: { ...process.env, ...backendEnv }, stdio: "pipe" as const, windowsHide: true };
  execFileSync(python, ["-m", "alembic", "upgrade", "head"], options);
  execFileSync(python, ["-m", "backend.demo", "seed"], options);
}
