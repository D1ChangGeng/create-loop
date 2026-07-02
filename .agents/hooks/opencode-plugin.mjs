// Self-Evolution Knowledge Hooks — OpenCode Native Plugin
// Replaces hooks.json bridge with direct event subscriptions.
// Install: add "file://<project-root>/.agents/hooks/opencode-plugin.mjs" to opencode.json plugin array.
//
// Events handled:
//   session.idle      → runs stop.sh (inbox pressure + evolution staleness check)
//   session.deleted   → runs session-end.sh (inbox marker for next session)
//   session.compacted → runs compact-recovery.sh (re-read directive injected into context)

import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

function runHook(cwd, scriptName) {
  const scriptPath = join(cwd, ".agents", "hooks", scriptName);
  if (!existsSync(scriptPath)) return null;
  try {
    return execSync(`sh "${scriptPath}"`, {
      cwd,
      timeout: 5000,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch {
    return null;
  }
}

export default async () => {
  const cwd = process.cwd();

  return {
    event: async (input) => {
      const name = input?.event?.type;

      if (name === "session.idle") {
        // Equivalent to Claude Code "Stop" — check knowledge health
        const stderr = runHook(cwd, "stop.sh");
        if (stderr && stderr.trim()) {
          process.stderr.write(stderr);
        }
      }

      if (name === "session.deleted") {
        // Equivalent to Claude Code "SessionEnd" — leave inbox marker
        runHook(cwd, "session-end.sh");
      }
    },

    "experimental.session.compacting": async (_input, output) => {
      // Equivalent to Claude Code "SessionStart" with compact matcher
      // Inject re-read directive into compacted context
      const directive = runHook(cwd, "compact-recovery.sh");
      if (directive && directive.trim() && output.context) {
        output.context = directive.trim() + "\n\n" + output.context;
      }
    },
  };
};
