# Set up Discord

This guide takes one Discord Bot from the Discord Developer Portal to a working Character reply. Keep Bot tokens, provider keys, and connector secrets outside Git and screenshots.

## 1. Prepare Discord

Create an Application and Bot in the Discord Developer Portal. Invite the Bot with the `bot` OAuth scope and only these minimum permissions:

```text
View Channels
Send Messages
Send Messages in Threads
Read Message History
Manage Webhooks
```

Administrator is not required. Enable **Message Content Intent** for the Bot; ordinary message context, reply routing, and Smart Participation depend on it.

## 2. Prepare Character Relay

The configured Bootstrap Super Admin creates the managed Discord Connection. In the Portal:

1. Create or select the Character Card you want to deploy.
2. Open **Deployment Center** and add a Discord Connection (Super Admin only).
3. Open the Connection details and copy the **internal Connection ID**. It is the UUID shown as `Internal Connection ID`; do not use the Discord Bot / external account ID.
4. Create a Server Profile from a Discord Server synchronized by that Connection.
5. Create the Character Deployment in that Server workspace, choose its Channel or Thread, then activate it when the connector and destination have been checked.

Regular users cannot create managed Connections. They first receive Server Access (a join code or a Super Admin assignment), then select or claim a Server already synchronized by the operator and create their Character Deployment in that Server workspace. Connector synchronization, Server Access, Server Profiles, and Knowledge Fabric scopes are separate records: synchronization does not grant access or create either kind of scope.

Only the Super Admin can bootstrap a Knowledge Fabric Server scope. It uses the exact Discord Connection ID and Server ID, and it does not grant Fabric administration to Discord members or Server Access members; those memberships stay explicit.

New deployments are created **Paused**. This retains the destination, identity, and exclusions while the connector is checked; it does not participate in Discord until you activate it from Deployment Center. A Server Profile sets the Server-wide channel exclusions. A deployment can add its own exclusions but cannot re-enable a location excluded by that profile.

## 3. Configure the shared secret

Set one random secret on the Character Relay API:

```text
CHARACTER_RELAY_CONNECTOR_SHARED_SECRET=<long random secret>
```

Set the same value on the Discord Connector under a different setting name:

```text
CHARACTER_RELAY_CONNECTOR_TOKEN=<same secret>
```

Do not paste either value into a Character Card, document, log, or issue.

## 4. Start the Connector

The Connector requires:

```text
DISCORD_BOT_TOKEN=<Discord Bot token>
CHARACTER_RELAY_API_URL=https://<Character Relay service domain>
CHARACTER_RELAY_CONNECTOR_TOKEN=<shared secret>
CHARACTER_RELAY_CONNECTION_ID=<internal Connection UUID copied from Connection details>
DISCORD_MESSAGE_CONTENT_INTENT=true
```

For local development, copy `connectors/discord/.env.example` to `.env`, fill the values, then run:

```bash
cd connectors/discord
npm install
npm run dev
```

## 5. Verify the path

1. Open the Connector `/health` endpoint and confirm it has refreshed deployments.
2. Confirm the Deployment is Active and its Server, Channel, and optional Thread match Discord.
3. Send `@CharacterRelayBot hello` in the allowed destination.
4. If multiple Characters share it, include the Character name after the Bot mention.
5. Reply directly to the Character message and confirm it routes back to the same Deployment.

If this fails, follow [Discord debugging](discord-debugging.md). Advanced addressing, group aliases, Bot-to-Bot Tag limits, Stickers, and Railway settings are documented in the [Connector reference](../../connectors/discord/README.md).
