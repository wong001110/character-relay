from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "connectors/discord/src/index.ts"
text = INDEX.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch anchor not found: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once(
    'import { RelayClient } from "./relayClient.js";\n',
    'import { RelayClient } from "./relayClient.js";\n'
    'import { RecoveryLoop } from "./recoveryLoop.js";\n',
)

replace_once(
    "let lastError: string | null = null;\n"
    "let ready = false;\n"
    "let refreshTimer: NodeJS.Timeout | undefined;\n"
    "let heartbeatTimer: NodeJS.Timeout | undefined;",
    "let lastError: string | null = null;\n"
    "let ready = false;\n"
    "let stateSynchronized = false;\n"
    "let recoveryLoop: RecoveryLoop | undefined;\n"
    "let heartbeatTimer: NodeJS.Timeout | undefined;",
)

replace_once(
    '      status: ready ? "ready" : "starting",\n'
    '      discord_user: client.user?.tag ?? null,',
    '      status: ready ? (stateSynchronized ? "ready" : "degraded") : "starting",\n'
    '      gateway_ready: ready,\n'
    '      state_synchronized: stateSynchronized,\n'
    '      railway_replica_region: process.env.RAILWAY_REPLICA_REGION ?? null,\n'
    '      discord_user: client.user?.tag ?? null,',
)

old_ready = '''client.once(Events.ClientReady, async (readyClient) => {
  try {
    await refreshConnectorState();
    await sendHeartbeat("connected");
    ready = true;
    lastError = null;
    log("Discord connector ready.", {
      discordUser: readyClient.user.tag,
      connectionId: config.relayConnectionId,
      activeDeployments: flattenDeployments(deployments).length,
      activeDestinations: deployments.size
    });
    refreshTimer = setInterval(() => {
      void refreshConnectorState().catch((error: unknown) => {
        lastError = error instanceof Error ? error.message : String(error);
        log("Connector state refresh failed.", { error: lastError });
      });
    }, config.deploymentRefreshSeconds * 1000);
    heartbeatTimer = setInterval(() => {
      void sendHeartbeat("connected").catch((error: unknown) => {
        lastError = error instanceof Error ? error.message : String(error);
        log("Connector heartbeat failed.", { error: lastError });
      });
    }, config.heartbeatSeconds * 1000);
  } catch (error) {
    lastError = error instanceof Error ? error.message : String(error);
    log("Discord connector failed during startup.", { error: lastError });
    await sendHeartbeat("error", lastError).catch(() => undefined);
  }
});'''

new_ready = '''client.once(Events.ClientReady, (readyClient) => {
  ready = true;
  log("Discord Gateway connected.", {
    discordUser: readyClient.user.tag,
    connectionId: config.relayConnectionId,
    railwayReplicaRegion: process.env.RAILWAY_REPLICA_REGION ?? null
  });

  recoveryLoop = new RecoveryLoop(config.deploymentRefreshSeconds * 1000, {
    execute: refreshConnectorState,
    succeeded: async () => {
      const recovered = !stateSynchronized || Boolean(lastError);
      stateSynchronized = true;
      lastError = null;
      await sendHeartbeat("connected").catch((error: unknown) => {
        lastError = error instanceof Error ? error.message : String(error);
        log("Connector heartbeat failed after state synchronization.", {
          error: lastError
        });
      });
      if (recovered) {
        log("Discord connector state synchronized.", {
          discordUser: readyClient.user.tag,
          connectionId: config.relayConnectionId,
          activeDeployments: flattenDeployments(deployments).length,
          activeDestinations: deployments.size
        });
      }
    },
    failed: async (error: unknown) => {
      lastError = error instanceof Error ? error.message : String(error);
      log("Connector state synchronization failed; retry scheduled.", {
        error: lastError,
        retrySeconds: config.deploymentRefreshSeconds
      });
      await sendHeartbeat("error", lastError).catch(() => undefined);
    }
  });
  recoveryLoop.start();

  heartbeatTimer = setInterval(() => {
    const status = stateSynchronized ? "connected" : "error";
    const error = stateSynchronized
      ? ""
      : (lastError ?? "Waiting for initial Character Relay synchronization.");
    void sendHeartbeat(status, error).catch((reason: unknown) => {
      lastError = reason instanceof Error ? reason.message : String(reason);
      log("Connector heartbeat failed.", { error: lastError });
    });
  }, config.heartbeatSeconds * 1000);
});'''

replace_once(old_ready, new_ready)

replace_once(
    "async function shutdown(signal: string): Promise<void> {\n"
    "  ready = false;\n"
    "  if (refreshTimer) clearInterval(refreshTimer);\n"
    "  if (heartbeatTimer) clearInterval(heartbeatTimer);",
    "async function shutdown(signal: string): Promise<void> {\n"
    "  ready = false;\n"
    "  stateSynchronized = false;\n"
    "  recoveryLoop?.stop();\n"
    "  if (heartbeatTimer) clearInterval(heartbeatTimer);",
)

INDEX.write_text(text, encoding="utf-8")

Path(__file__).unlink(missing_ok=True)
(ROOT / ".github/workflows/apply-discord-startup-recovery.yml").unlink(missing_ok=True)
