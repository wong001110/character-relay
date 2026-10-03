import type { ReactNode } from "react";
import { formatPortalClock } from "./portalTime";
import type { WebExpression, WebMessage } from "./webRoomApi";

const commonReactions = ["👍", "❤️", "😂", "😮", "😢", "🔥", "🎉", "👀"];

function imageAttachment(contentType: string, filename: string): boolean {
  return contentType.toLowerCase().startsWith("image/") ||
    /\.(?:png|jpe?g|webp|gif|avif)$/iu.test(filename);
}
function videoAttachment(contentType: string, filename: string): boolean {
  return contentType.toLowerCase().startsWith("video/") ||
    /\.(?:mp4|webm|mov)$/iu.test(filename);
}
function sizeLabel(value: number | null): string {
  if (!value || value < 1) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
function messageTime(value: string | null): string {
  return value ? formatPortalClock(value) : "";
}
function emojiImage(id: string, animated: boolean): string {
  return `https://cdn.discordapp.com/emojis/${id}.${animated ? "gif" : "png"}`;
}
function messageText(message: WebMessage): ReactNode[] {
  if (!message.text) return [];
  const emojiById = new Map(message.custom_emojis.map(item => [item.resource_id, item]));
  const mentionByKey = new Map(
    message.mentions.map(item => [`${item.kind}:${item.target_id}`, item])
  );
  const token = /<(a?):([A-Za-z0-9_]+):(\d+)>|<@!?(\d+)>|<@&(\d+)>|<#(\d+)>/gu;
  const output: ReactNode[] = [];
  let cursor = 0;
  for (const match of message.text.matchAll(token)) {
    const index = match.index ?? 0;
    if (index > cursor) output.push(message.text.slice(cursor, index));
    if (match[3]) {
      const id = match[3];
      const known = emojiById.get(id);
      const name = known?.name || match[2];
      const animated = known?.animated ?? match[1] === "a";
      output.push(
        <img
          key={`emoji:${index}:${id}`}
          className="web-room-inline-emoji"
          src={known?.asset_url || emojiImage(id, animated)}
          alt={`:${name}:`}
          title={`:${name}:`}
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      );
    } else {
      const kind = match[4] ? "user" : match[5] ? "role" : "channel";
      const id = match[4] || match[5] || match[6];
      const known = mentionByKey.get(`${kind}:${id}`);
      const prefix = kind === "channel" ? "#" : "@";
      const fallback = kind === "channel" ? "channel" : kind;
      output.push(
        <span key={`mention:${index}:${id}`} className="web-room-mention">
          {prefix}{known?.label || fallback}
        </span>
      );
    }
    cursor = index + match[0].length;
  }
  if (cursor < message.text.length) output.push(message.text.slice(cursor));
  return output;
}

export function WebRoomMessage({
  message,
  canPost,
  profileId,
  expressions,
  disabled,
  onReply,
  onJump,
  onReact,
  tx
}: {
  message: WebMessage;
  canPost: boolean;
  profileId: string;
  expressions: WebExpression[];
  disabled: boolean;
  onReply: (id: string) => void;
  onJump: (id: string) => void;
  onReact: (message: WebMessage, emojiKey: string, emojiName: string, enabled: boolean) => void;
  tx: (en: string, cn: string) => string;
}) {
  const reply = message.reply_preview;
  const customEmoji = expressions.filter(item => item.resource_type === "emoji" && item.asset_url);
  const hasBody = Boolean(message.text || message.attachments.length || message.stickers.length || message.embeds.length || message.poll);

  return (
    <article className="web-room-message" id={`web-room-message-${message.id}`} data-message-id={message.id}>
      <span className="web-room-message-avatar" aria-hidden="true">
        {message.avatar_url.startsWith("https://")
          ? <img src={message.avatar_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
          : (message.display_name.slice(0, 1) || "?")}
      </span>
      <div className="web-room-message-body">
        <header>
          <strong>{message.display_name || tx("Deleted source", "已删除来源")}</strong>
          {message.pinned && <span className="web-room-message-badge" title={tx("Pinned", "已置顶")}>📌</span>}
          <small>{message.actor_type.replaceAll("_", " ")} · {messageTime(message.created_at)}{message.edited_at ? tx(" · edited", " · 已编辑") : ""}</small>
        </header>

        {reply && (
          reply.available ? (
            reply.in_snapshot ? (
              <button type="button" className="web-room-reply-context" onClick={() => onJump(reply.message_id)}>
                <strong>↪ {reply.display_name}</strong>
                <span>{reply.summary}</span>
              </button>
            ) : (
              <div className="web-room-reply-context is-static">
                <strong>↪ {reply.display_name}</strong>
                <span>{reply.summary} · {tx("not in recent view", "不在最近消息范围")}</span>
              </div>
            )
          ) : (
            <div className="web-room-reply-context is-static">
              <strong>↪ {tx("Original message unavailable", "原消息不可用")}</strong>
            </div>
          )
        )}

        {message.deleted ? (
          <p className="room-preserve-text web-room-muted">{tx("Message deleted", "消息已删除")}</p>
        ) : !message.content_available ? (
          <p className="room-preserve-text web-room-muted">{tx("Message content unavailable", "消息内容不可用")}</p>
        ) : (
          <>
            {message.text && <p className="room-preserve-text web-room-rich-text">{messageText(message)}</p>}
            {!hasBody && <p className="room-preserve-text web-room-muted">{tx("This message contains content that cannot be displayed here.", "此消息包含目前无法显示的内容。")}</p>}

            {message.attachments.length > 0 && (
              <div className="web-room-media-grid">
                {message.attachments.map(attachment => {
                  const src = attachment.proxy_url || attachment.url;
                  if (imageAttachment(attachment.content_type, attachment.filename)) {
                    return (
                      <a className="web-room-media-item" href={attachment.url} target="_blank" rel="noreferrer" key={attachment.attachment_id}>
                        <img src={src} alt={attachment.description || attachment.filename} loading="lazy" referrerPolicy="no-referrer" />
                        <span>{attachment.filename}</span>
                      </a>
                    );
                  }
                  if (videoAttachment(attachment.content_type, attachment.filename)) {
                    return (
                      <div className="web-room-media-item" key={attachment.attachment_id}>
                        <video controls preload="metadata" src={src} />
                        <a href={attachment.url} target="_blank" rel="noreferrer">{attachment.filename}</a>
                      </div>
                    );
                  }
                  return (
                    <a className="web-room-file-card" href={attachment.url} target="_blank" rel="noreferrer" key={attachment.attachment_id}>
                      <strong>📎 {attachment.filename}</strong>
                      <small>{attachment.content_type || tx("Attachment", "附件")}{attachment.size_bytes ? ` · ${sizeLabel(attachment.size_bytes)}` : ""}</small>
                    </a>
                  );
                })}
              </div>
            )}

            {message.stickers.length > 0 && (
              <div className="web-room-stickers">
                {message.stickers.map(sticker => {
                  const renderable = Boolean(sticker.asset_url) && !["3", "lottie"].includes(sticker.format_type.toLowerCase());
                  return renderable ? (
                    <img key={sticker.resource_id} src={sticker.asset_url} alt={sticker.description || sticker.name} title={sticker.name} loading="lazy" referrerPolicy="no-referrer" />
                  ) : (
                    <span className="web-room-file-card" key={sticker.resource_id}>🏷️ {tx("Sticker", "贴图")}: {sticker.name}</span>
                  );
                })}
              </div>
            )}

            {message.embeds.length > 0 && (
              <div className="web-room-embeds">
                {message.embeds.map((embed, index) => {
                  const preview = embed.image_proxy_url || embed.thumbnail_proxy_url || embed.image_url || embed.thumbnail_url;
                  const card = (
                    <div className="web-room-embed-card">
                      {(embed.provider_name || embed.author_name) && <small>{embed.provider_name || embed.author_name}</small>}
                      {embed.title && <strong>{embed.title}</strong>}
                      {embed.description && <p>{embed.description}</p>}
                      {preview && <img src={preview} alt="" loading="lazy" referrerPolicy="no-referrer" />}
                    </div>
                  );
                  return embed.url ? (
                    <a className="web-room-embed-link" href={embed.url} target="_blank" rel="noreferrer" key={`embed:${index}`}>{card}</a>
                  ) : <div key={`embed:${index}`}>{card}</div>;
                })}
              </div>
            )}

            {message.poll && (
              <section className="web-room-poll" aria-label={tx("Discord poll", "Discord 投票")}>
                <header><strong>📊 {message.poll.question}</strong><small>{message.poll.allow_multiselect ? tx("Multiple choice", "可多选") : tx("Single choice", "单选")}</small></header>
                <ol>
                  {message.poll.answers.map(answer => (
                    <li key={answer.answer_id}>
                      <span>{answer.emoji_name ? `${answer.emoji_name} ` : ""}{answer.text || tx("Option", "选项")}</span>
                      <strong>{answer.vote_count}</strong>
                    </li>
                  ))}
                </ol>
                <small>{message.poll.results_finalized ? tx("Poll ended", "投票已结束") : tx("Vote in Discord", "请在 Discord 投票")}</small>
              </section>
            )}
          </>
        )}

        {!message.deleted && message.reactions.length > 0 && (
          <div className="web-room-reactions" aria-label={tx("Reactions", "回应")}>
            {message.reactions.map(reaction => {
              const mine = Boolean(profileId && reaction.mine_profile_ids.includes(profileId));
              return (
                <button
                  type="button"
                  className={mine ? "is-mine" : ""}
                  disabled={disabled || !canPost || !profileId}
                  key={reaction.key}
                  title={`Discord ${reaction.discord_count} · Web ${reaction.web_count}`}
                  onClick={() => onReact(message, reaction.key, reaction.name, !mine)}
                >
                  {reaction.asset_url
                    ? <img src={reaction.asset_url} alt={`:${reaction.name}:`} loading="lazy" referrerPolicy="no-referrer" />
                    : <span>{reaction.name}</span>}
                  <strong>{reaction.count}</strong>
                </button>
              );
            })}
          </div>
        )}

        {!message.deleted && message.content_available && (
          <div className="web-room-message-actions">
            {canPost && (
              <button type="button" className="web-room-reply" disabled={disabled} onClick={() => onReply(message.id)}>
                {tx("Reply", "回复")}
              </button>
            )}
            {canPost && profileId && (
              <details className="web-room-reaction-picker">
                <summary aria-label={tx("Add reaction", "添加回应")}>＋ {tx("React", "回应")}</summary>
                <div>
                  {commonReactions.map(emoji => (
                    <button type="button" key={emoji} disabled={disabled} onClick={() => onReact(message, `unicode:${emoji}`, emoji, true)}>{emoji}</button>
                  ))}
                  {customEmoji.slice(0, 120).map(emoji => (
                    <button type="button" key={emoji.resource_key} disabled={disabled} title={emoji.name} onClick={() => onReact(message, emoji.resource_key, emoji.name, true)}>
                      <img src={emoji.asset_url} alt={`:${emoji.name}:`} loading="lazy" referrerPolicy="no-referrer" />
                    </button>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
