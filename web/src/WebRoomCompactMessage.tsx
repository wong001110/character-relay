import { webRoomMessageText } from "./WebRoomMessage";
import type { WebMessage } from "./webRoomApi";

type Translate = (english: string, chinese: string) => string;

/** Only omit the transport prefix when the structured reply identifies that same message. */
export function companionMessageText(message: WebMessage): string {
  if (!message.reply_preview) return message.text;
  const prefix = /^↪\s+https:\/\/(?:(?:canary|ptb)\.)?discord(?:app)?\.com\/channels\/\d+\/\d+\/(\d+)\/?(?:\r?\n|$)/u.exec(message.text);
  if (!prefix || prefix[1] !== (message.reply_to_message_id || message.reply_preview.message_id)) {
    return message.text;
  }
  return message.text.slice(prefix[0].length).replace(/^\r?\n/u, "");
}

function mediaUrl(value: string): string {
  if (!value) return "";
  try {
    const url = new URL(value, window.location.href);
    if (url.username || url.password) return "";
    return url.protocol === "https:" || (url.protocol === "http:" && url.origin === window.location.origin)
      ? url.href : "";
  } catch {
    return "";
  }
}

function messageTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
}

function CompactMedia({ src, href, label, description, kind, tx }: {
  src: string;
  href: string;
  label: string;
  description: string;
  kind: "gif" | "image" | "file";
  tx: Translate;
}) {
  const image = kind !== "file";
  const content = <>
    {image && src && <img src={src} alt={description || label} loading="lazy" referrerPolicy="no-referrer" />}
    <span className="room-companion-file-caption">
      <span>{kind === "gif" ? "GIF · " : ""}{label}</span>
      {description && <span>{description}</span>}
      {image && !description && <small>{tx("No description provided", "未提供内容描述")}</small>}
      {image && href && <strong>
        {kind === "gif" ? tx("View GIF", "放大查看 GIF") : tx("View image", "放大查看图片")}
        {tx(" · opens a new tab", " · 在新标签页打开")}
      </strong>}
    </span>
  </>;
  return href
    ? <a className="room-companion-file" href={href} target="_blank" rel="noreferrer">{content}</a>
    : <div className="room-companion-file">{content}</div>;
}

export function CompactMessage({ message, onReply, disabled, tx }: {
  message: WebMessage;
  onReply: (id: string) => void;
  disabled: boolean;
  tx: Translate;
}) {
  const reply = message.reply_preview;
  const text = companionMessageText(message);
  const safeEmojis = message.custom_emojis.map(emoji => ({ ...emoji, asset_url: mediaUrl(emoji.asset_url) }));
  const hasContent = Boolean(text || message.attachments.length || message.stickers.length || message.embeds.length || message.poll);
  return (
    <article
      className="room-companion-message"
      data-message-id={message.id}
      data-author-id={message.author_id}
      data-actor-type={message.actor_type}
      data-reply-to-message-id={message.reply_to_message_id}
      data-deleted={message.deleted}
      data-content-available={message.content_available}
    >
      <header>
        <strong>{message.display_name || tx("Deleted source", "已删除来源")}</strong>
        <time dateTime={message.created_at || undefined}>{messageTime(message.created_at)}</time>
      </header>
      <small>{message.actor_type.replaceAll("_", " ")}{message.edited_at ? tx(" · edited", " · 已编辑") : ""}{message.pinned ? tx(" · pinned", " · 已置顶") : ""}</small>
      {reply && (
        <div className="room-companion-reply-context" data-reply-message-id={reply.message_id}>
          <strong>↪ {reply.available ? reply.display_name : tx("Original message unavailable", "原消息不可用")}</strong>
          {reply.available && <span>{reply.summary}{!reply.in_snapshot ? tx(" · outside recent view", " · 不在最近消息范围") : ""}</span>}
        </div>
      )}
      {message.deleted ? (
        <p className="room-companion-muted">{tx("Message deleted", "消息已删除")}</p>
      ) : !message.content_available ? (
        <p className="room-companion-muted">{tx("Message content unavailable", "消息内容不可用")}</p>
      ) : (
        <>
          {text && <p>{webRoomMessageText({ ...message, custom_emojis: safeEmojis }, text)}</p>}
          {!hasContent && <p className="room-companion-muted">{tx("Content cannot be displayed here.", "此内容无法在这里显示。")}</p>}
          {message.attachments.map(attachment => {
            const src = mediaUrl(attachment.proxy_url || attachment.url);
            const href = mediaUrl(attachment.url);
            const image = attachment.content_type.toLowerCase().startsWith("image/") || /\.(?:png|jpe?g|webp|gif|avif)$/iu.test(attachment.filename);
            const gif = attachment.content_type.toLowerCase() === "image/gif" || /\.gif$/iu.test(attachment.filename);
            return <CompactMedia key={attachment.attachment_id} src={src} href={href}
              label={attachment.filename} description={attachment.description}
              kind={gif ? "gif" : image ? "image" : "file"} tx={tx} />;
          })}
          {message.stickers.map(sticker => <small className="room-companion-content-note" key={sticker.resource_key || sticker.resource_id}>🏷️ {tx("Sticker", "贴图")}: {sticker.name}</small>)}
          {message.embeds.map((embed, index) => {
            const src = mediaUrl(embed.image_proxy_url || embed.thumbnail_proxy_url || embed.image_url || embed.thumbnail_url);
            const href = mediaUrl(embed.url) || src;
            const gif = embed.embed_type === "gifv" || /\.gif(?:\?|$)/iu.test(src);
            const label = embed.title || embed.provider_name || tx("Embed", "嵌入内容");
            return <CompactMedia key={index} src={src} href={href} label={label}
              description={embed.description} kind={gif ? "gif" : src ? "image" : "file"} tx={tx} />;
          })}
          {message.poll && <small className="room-companion-content-note">{tx("Poll", "投票")}: {message.poll.question}</small>}
        </>
      )}
      {!message.deleted && message.content_available && <button type="button" className="room-companion-reply-action" disabled={disabled} onClick={() => onReply(message.id)} aria-label={tx(`Reply to ${message.display_name}`, `回复 ${message.display_name}`)}>{tx("Reply", "回复")}</button>}
    </article>
  );
}
