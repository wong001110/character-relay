import type { RelayClient } from "./relayClient.js";
import type { DiscordDeployment } from "./types.js";

interface DiscordApiWebhook {
  id: string;
  type: number;
  name?: string | null;
  token?: string | null;
  user?: { id: string } | null;
}

interface DiscordApiMessage {
  id: string;
}

const DISCORD_API = "https://discord.com/api/v10";
const WEBHOOK_NAME = "Character Relay";

export class DiscordWebhookManager {
  constructor(
    private readonly botToken: string,
    private readonly relay: RelayClient
  ) {}

  async ensure(
    deployment: DiscordDeployment,
    botUserId: string
  ): Promise<{ id: string; token: string }> {
    if (deployment.webhook_id && deployment.webhook_token) {
      return { id: deployment.webhook_id, token: deployment.webhook_token };
    }

    const existing = await this.listChannelWebhooks(deployment.channel_id);
    let webhook = existing.find(
      (item) => item.type === 1 && item.user?.id === botUserId && Boolean(item.token)
    );
    if (!webhook) {
      webhook = await this.createChannelWebhook(deployment.channel_id);
    }
    if (!webhook.token) {
      throw new Error("Discord did not return a usable incoming-webhook token.");
    }

    const registered = await this.relay.registerWebhook({
      deployment_id: deployment.deployment_id,
      workspace_id: deployment.workspace_id,
      channel_id: deployment.channel_id,
      category_id: deployment.category_id,
      thread_id: deployment.thread_id,
      webhook_id: webhook.id,
      webhook_token: webhook.token
    });
    deployment.webhook_id = registered.webhook_id;
    deployment.webhook_token = registered.webhook_token;
    deployment.webhook_status = "active";
    return {
      id: registered.webhook_id,
      token: registered.webhook_token
    };
  }

  async sendAsset(
    deployment: DiscordDeployment,
    content: string,
    assetUrl: string,
    filename: string,
    botUserId: string
  ): Promise<string[]> {
    try {
      let binding = await this.ensure(deployment, botUserId);
      let response = await this.executeWebhookAsset(
        binding,
        deployment,
        content,
        assetUrl,
        filename
      );
      if (response.status === 401 || response.status === 404) {
        deployment.webhook_id = null;
        deployment.webhook_token = null;
        deployment.webhook_status = "pending";
        binding = await this.ensure(deployment, botUserId);
        response = await this.executeWebhookAsset(
          binding,
          deployment,
          content,
          assetUrl,
          filename
        );
      }
      if (!response.ok) {
        throw new Error(
          `Discord webhook attachment returned HTTP ${response.status}: ${await response.text()}`
        );
      }
      const message = (await response.json()) as DiscordApiMessage;
      deployment.webhook_status = "active";
      await this.relay
        .reportWebhookStatus({
          deployment_id: deployment.deployment_id,
          status: "active",
          last_error: ""
        })
        .catch(() => undefined);
      return [message.id];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      deployment.webhook_status = "error";
      await this.relay
        .reportWebhookStatus({
          deployment_id: deployment.deployment_id,
          status: "error",
          last_error: message
        })
        .catch(() => undefined);
      throw error;
    }
  }

  async send(
    deployment: DiscordDeployment,
    chunks: string[],
    botUserId: string
  ): Promise<string[]> {
    if (!chunks.length) return [];
    try {
      return await this.sendWithBinding(deployment, chunks, botUserId);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      deployment.webhook_status = "error";
      await this.relay
        .reportWebhookStatus({
          deployment_id: deployment.deployment_id,
          status: "error",
          last_error: message
        })
        .catch(() => undefined);
      throw error;
    }
  }

  private async sendWithBinding(
    deployment: DiscordDeployment,
    chunks: string[],
    botUserId: string
  ): Promise<string[]> {
    let binding = await this.ensure(deployment, botUserId);
    const messageIds: string[] = [];

    for (let index = 0; index < chunks.length; index += 1) {
      const chunk = chunks[index];
      if (!chunk) continue;
      let response = await this.executeWebhook(binding, deployment, chunk);
      if ((response.status === 401 || response.status === 404) && index === 0) {
        deployment.webhook_id = null;
        deployment.webhook_token = null;
        deployment.webhook_status = "pending";
        binding = await this.ensure(deployment, botUserId);
        response = await this.executeWebhook(binding, deployment, chunk);
      }
      if (!response.ok) {
        throw new Error(
          `Discord webhook returned HTTP ${response.status}: ${await response.text()}`
        );
      }
      const message = (await response.json()) as DiscordApiMessage;
      messageIds.push(message.id);
    }

    deployment.webhook_status = "active";
    await this.relay
      .reportWebhookStatus({
        deployment_id: deployment.deployment_id,
        status: "active",
        last_error: ""
      })
      .catch(() => undefined);
    return messageIds;
  }

  private async executeWebhookAsset(
    binding: { id: string; token: string },
    deployment: DiscordDeployment,
    content: string,
    assetUrl: string,
    filename: string
  ): Promise<Response> {
    const asset = await fetch(assetUrl, {
      signal: AbortSignal.timeout(30_000)
    });
    if (!asset.ok) {
      throw new Error(
        `Unable to download Discord expression asset (HTTP ${asset.status}).`
      );
    }
    const bytes = await asset.arrayBuffer();
    const mediaType = asset.headers.get("content-type") || "application/octet-stream";
    const form = new FormData();
    form.append(
      "payload_json",
      JSON.stringify({
        ...(content ? { content } : {}),
        username: deployment.identity_display_name.slice(0, 80),
        ...(deployment.identity_avatar_url
          ? { avatar_url: deployment.identity_avatar_url }
          : {}),
        allowed_mentions: { parse: [] },
        attachments: [{ id: 0, filename }]
      })
    );
    form.append("files[0]", new Blob([bytes], { type: mediaType }), filename);

    const url = new URL(`${DISCORD_API}/webhooks/${binding.id}/${binding.token}`);
    url.searchParams.set("wait", "true");
    if (deployment.thread_id) {
      url.searchParams.set("thread_id", deployment.thread_id);
    }
    return fetch(url, {
      method: "POST",
      signal: AbortSignal.timeout(30_000),
      body: form
    });
  }

  private executeWebhook(
    binding: { id: string; token: string },
    deployment: DiscordDeployment,
    content: string
  ): Promise<Response> {
    const url = new URL(`${DISCORD_API}/webhooks/${binding.id}/${binding.token}`);
    url.searchParams.set("wait", "true");
    if (deployment.thread_id) {
      url.searchParams.set("thread_id", deployment.thread_id);
    }
    return fetch(url, {
      method: "POST",
      signal: AbortSignal.timeout(30_000),
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        username: deployment.identity_display_name.slice(0, 80),
        ...(deployment.identity_avatar_url
          ? { avatar_url: deployment.identity_avatar_url }
          : {}),
        allowed_mentions: { parse: [] }
      })
    });
  }

  private async listChannelWebhooks(channelId: string): Promise<DiscordApiWebhook[]> {
    const response = await this.botRequest(`/channels/${channelId}/webhooks`);
    if (!response.ok) {
      throw new Error(
        `Unable to inspect Discord webhooks (HTTP ${response.status}): ${await response.text()}`
      );
    }
    return response.json() as Promise<DiscordApiWebhook[]>;
  }

  private async createChannelWebhook(channelId: string): Promise<DiscordApiWebhook> {
    const response = await this.botRequest(`/channels/${channelId}/webhooks`, {
      method: "POST",
      body: JSON.stringify({ name: WEBHOOK_NAME })
    });
    if (!response.ok) {
      throw new Error(
        `Unable to create Discord webhook (HTTP ${response.status}): ${await response.text()}`
      );
    }
    return response.json() as Promise<DiscordApiWebhook>;
  }

  private botRequest(path: string, init?: RequestInit): Promise<Response> {
    return fetch(`${DISCORD_API}${path}`, {
      ...init,
      signal: AbortSignal.timeout(30_000),
      headers: {
        Authorization: `Bot ${this.botToken}`,
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      }
    });
  }
}
