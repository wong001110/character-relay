from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "connectors/discord/src/webhookManager.ts",
    '''  async send(
    deployment: DiscordDeployment,
    chunks: string[],
    botUserId: string
  ): Promise<string[]> {''',
    '''  async sendAsset(
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
  ): Promise<string[]> {''',
)

replace_once(
    "connectors/discord/src/webhookManager.ts",
    '''  private executeWebhook(
    binding: { id: string; token: string },
    deployment: DiscordDeployment,
    content: string
  ): Promise<Response> {''',
    '''  private async executeWebhookAsset(
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
  ): Promise<Response> {''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''    } else if (decision.action === "sticker" && candidate.resource_type === "sticker") {
      try {
        const sent = await source.reply({
          ...(visibleText ? { content: visibleText } : {}),
          stickers: [candidate.resource_id],
          allowedMentions: { parse: [], repliedUser: false }
        });
        sentMessageIds = [sent.id];
      } catch (error) {
        fallback = "sticker_to_text";
        if (!visibleText) throw error;
        sentMessageIds = await sendCharacterReply(source, deployment, visibleText, botUserId);
      }
    } else {''',
    '''    } else if (decision.action === "sticker" && candidate.resource_type === "sticker") {
      let webhookAssetError: unknown = null;
      if (deployment.identity_mode === "webhook" && candidate.asset_url) {
        try {
          const extension = candidate.format_type === "gif" ? "gif" : "png";
          sentMessageIds = await webhookManager.sendAsset(
            deployment,
            visibleText,
            candidate.asset_url,
            `${candidate.name || "expression"}.${extension}`,
            botUserId
          );
          fallback = "webhook_attachment";
        } catch (error) {
          webhookAssetError = error;
          fallback = "webhook_attachment_to_native_sticker";
          log("Webhook Sticker-like attachment failed; trying native Bot Sticker.", {
            deploymentId: deployment.deployment_id,
            resourceKey: candidate.resource_key,
            error: error instanceof Error ? error.message : String(error)
          });
        }
      }
      if (!sentMessageIds.length) {
        try {
          const sent = await source.reply({
            ...(visibleText ? { content: visibleText } : {}),
            stickers: [candidate.resource_id],
            allowedMentions: { parse: [], repliedUser: false }
          });
          sentMessageIds = [sent.id];
          if (!fallback || fallback === "none") fallback = "native_bot_sticker";
        } catch (nativeStickerError) {
          fallback = "sticker_to_text";
          if (!visibleText) {
            throw webhookAssetError ?? nativeStickerError;
          }
          sentMessageIds = await sendCharacterReply(source, deployment, visibleText, botUserId);
        }
      }
    } else {''',
)
