// Intentionally kept separate from the large connector type file during the hotfix.
// RelayClient enriches DiscordInboundMessage JSON with this backward-compatible field;
// the backend DiscordInboundMessage schema owns validation of the final payload.
export interface DiscordInboundAttachmentMetadata {
  attachment_id: string;
  url: string;
  proxy_url: string;
  filename: string;
  content_type: string;
  size_bytes: number | null;
  width: number | null;
  height: number | null;
}
