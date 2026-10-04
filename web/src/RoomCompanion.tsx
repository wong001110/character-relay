import { useEffect, useId, useRef, useState } from "react";
import { useI18n } from "./i18n";
import { RoomCompanionSizeControls, type RoomCompanionSizeOptions } from "./RoomCompanionSizeControls";
import { unmatchedOutbox, webRoomCanSubmit, type WebMessage } from "./webRoomApi";
import type { WebRoomSession, WebRoomSessionState } from "./webRoomSession";
import "./room-companion.css";

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

function CompactMessage({ message, onReply, disabled, tx }: {
  message: WebMessage;
  onReply: (id: string) => void;
  disabled: boolean;
  tx: Translate;
}) {
  const reply = message.reply_preview;
  const text = companionMessageText(message);
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
          {text && <p>{text}</p>}
          {!hasContent && <p className="room-companion-muted">{tx("Content cannot be displayed here.", "此内容无法在这里显示。")}</p>}
          {message.attachments.map(attachment => {
            const src = mediaUrl(attachment.proxy_url || attachment.url);
            const href = mediaUrl(attachment.url);
            const image = attachment.content_type.toLowerCase().startsWith("image/") || /\.(?:png|jpe?g|webp|gif|avif)$/iu.test(attachment.filename);
            const content = <>{image && src && <img src={src} alt={attachment.description || attachment.filename} loading="lazy" referrerPolicy="no-referrer" />}<span>📎 {attachment.filename}</span></>;
            return href ? (
              <a className="room-companion-file" href={href} target="_blank" rel="noreferrer" key={attachment.attachment_id}>{content}</a>
            ) : (
              <div className="room-companion-file" key={attachment.attachment_id}>{content}</div>
            );
          })}
          {message.stickers.map(sticker => <small className="room-companion-content-note" key={sticker.resource_key || sticker.resource_id}>🏷️ {tx("Sticker", "贴图")}: {sticker.name}</small>)}
          {message.embeds.map((embed, index) => <small className="room-companion-content-note" key={index}>{tx("Embed", "嵌入内容")}: {embed.title || embed.description || embed.provider_name || tx("Open full room to view", "打开完整房间查看")}</small>)}
          {message.poll && <small className="room-companion-content-note">{tx("Poll", "投票")}: {message.poll.question}</small>}
        </>
      )}
      {!message.deleted && message.content_available && <button type="button" className="room-companion-reply-action" disabled={disabled} onClick={() => onReply(message.id)} aria-label={tx(`Reply to ${message.display_name}`, `回复 ${message.display_name}`)}>{tx("Reply", "回复")}</button>}
    </article>
  );
}

export function RoomCompanion({ state, session, onClose, onOpenFull, pip, sizeControls }: {
  state: WebRoomSessionState;
  session: WebRoomSession;
  onClose: () => void;
  onOpenFull: () => void;
  pip: boolean;
  sizeControls?: RoomCompanionSizeOptions;
}) {
  const { language } = useI18n();
  const tx: Translate = (en, cn) => language === "zh-CN" ? cn : en;
  const id = useId();
  const readerId = `companion:${id}`;
  const root = useRef<HTMLElement>(null);
  const history = useRef<HTMLDivElement>(null);
  const activated = useRef(false);
  const atLatest = useRef(true);
  const syncReader = useRef<() => void>(() => {});
  const [minimized, setMinimized] = useState(false);
  const [sizeExpanded, setSizeExpanded] = useState(false);
  const [restoreFailed, setRestoreFailed] = useState(false);
  const minimizedRef = useRef(minimized);
  minimizedRef.current = minimized;
  const preferredSize = sizeControls?.preferredSize;
  const needsSizeRestore = Boolean(pip && preferredSize && sizeControls && (
    preferredSize.width !== sizeControls.size.width || preferredSize.height !== sizeControls.size.height
  ));

  useEffect(() => {
    if (!needsSizeRestore) setRestoreFailed(false);
  }, [needsSizeRestore]);

  const room = state.rooms.find(item => item.id === state.roomId);
  const profile = state.profiles.find(item => item.id === state.profileId);
  const snapshot = state.snapshot.room_id === state.roomId ? state.snapshot : null;
  const messages = snapshot?.messages.slice(-5) || [];
  const latestId = messages.at(-1)?.id || "";
  const reply = snapshot?.messages.find(item => item.id === state.reply);
  const hiddenPayload = Boolean(state.attachments.length || state.stickerResourceKey);
  const sendingDisabled = !state.authenticated || state.busy || Boolean(state.localSubmission) || state.demoMode || !room?.enabled || !room.can_post || !profile || !webRoomCanSubmit(state.connection);
  const receipts = snapshot ? unmatchedOutbox(snapshot) : [];
  // Keep recent unresolved sends visible before filling the bounded list with final receipts.
  const unresolved = receipts.filter(item => ["pending", "claimed", "uncertain"].includes(item.status));
  const final = receipts.filter(item => !["pending", "claimed", "uncertain"].includes(item.status));
  const visibleReceipts = [...unresolved, ...final].slice(0, 8);
  const local = state.localSubmission?.room === state.roomId && !snapshot?.outbox.some(item => item.client_message_id === state.localSubmission?.payload.client_message_id)
    ? state.localSubmission : null;

  const statusLabels: Record<string, string> = {
    pending: tx("Website accepted", "网站已接收"),
    claimed: tx("Sending to Discord", "正在发送到 Discord"),
    delivered: tx("Delivered to Discord", "Discord 已送达"),
    failed: tx("Failed", "发送失败"),
    uncertain: tx("Delivery uncertain", "送达状态不确定"),
    cancelled: tx("Cancelled", "已取消")
  };
  const connectionLabels: Record<string, string> = {
    disconnected: tx("Disconnected", "未连接"),
    connecting: tx("Connecting", "连接中"),
    connected: tx("Live", "实时连接"),
    reconnecting: tx("Reconnecting · sending available", "重连中 · 仍可发送"),
    unavailable: tx("Access or connection unavailable", "访问或连接不可用")
  };

  useEffect(() => {
    const node = root.current;
    if (!node) return;
    const doc = node.ownerDocument;
    const view = doc.defaultView;
    if (!view) return;
    const sync = () => session.setReader(readerId,
      activated.current && !minimizedRef.current && atLatest.current && doc.visibilityState === "visible" && doc.hasFocus()
    );
    syncReader.current = sync;
    session.setReader(readerId, false);
    doc.addEventListener("visibilitychange", sync);
    // requestWindow may focus a newly opened PiP after mounting. Only content
    // focus/interaction or View latest activates reading; window focus resyncs it.
    view.addEventListener("focus", sync);
    view.addEventListener("blur", sync);
    if (view !== window) {
      window.addEventListener("focus", sync);
      window.addEventListener("blur", sync);
    }
    return () => {
      doc.removeEventListener("visibilitychange", sync);
      view.removeEventListener("focus", sync);
      view.removeEventListener("blur", sync);
      if (view !== window) {
        window.removeEventListener("focus", sync);
        window.removeEventListener("blur", sync);
      }
      syncReader.current = () => {};
      session.removeReader(readerId);
    };
  }, [session, readerId, pip]);

  useEffect(() => {
    syncReader.current();
  }, [minimized]);

  useEffect(() => {
    if (history.current && atLatest.current) history.current.scrollTop = history.current.scrollHeight;
  }, [latestId, minimized]);

  const activate = (target: EventTarget) => {
    const element = target as Element;
    if (minimizedRef.current || element.closest?.("[data-companion-reader-ignore]")) return;
    activated.current = true;
    syncReader.current();
  };
  const markLatest = () => {
    activated.current = true;
    atLatest.current = true;
    if (history.current) history.current.scrollTop = history.current.scrollHeight;
    syncReader.current();
    session.markRead();
  };

  return (
    <aside
      ref={root}
      className={`room-companion${pip ? " is-pip" : " is-in-app"}${minimized ? " is-minimized" : ""}`}
      aria-label={tx("Room Companion", "房间伴随窗口")}
      data-room-id={state.roomId}
      data-connection-state={state.connection}
      data-connection={state.connection}
      data-latest-message-id={latestId}
      data-unread-count={state.unread}
      data-unread={state.unread}
      data-minimized={minimized}
      onFocusCapture={event => activate(event.target)}
      onPointerDownCapture={event => activate(event.target)}
    >
      <header className="room-companion-header">
        <div className="room-companion-heading">
          <strong>{room ? `# ${room.name}` : tx("Choose a room in Rooms", "请在聊天室中选择房间")}</strong>
          <span role="status" className={`room-companion-connection is-${state.connection}`}>{connectionLabels[state.connection] || state.connection}</span>
        </div>
        <div className="room-companion-controls">
          {needsSizeRestore && sizeControls && preferredSize && <button type="button" data-companion-reader-ignore="true" data-companion-restore-size="true" onClick={() => {
            // Native PiP resizing needs this real child-window click. Keep the
            // browser call synchronous so its user activation is available.
            let accepted = false;
            try {
              accepted = sizeControls.onResize(preferredSize);
            } catch {
              // The browser may reject resizing after the window is opened.
            }
            setRestoreFailed(!accepted);
            if (!accepted) {
              setSizeExpanded(true);
              setMinimized(false);
            }
          }}>{tx(`Use ${preferredSize.width}×${preferredSize.height}`, `应用 ${preferredSize.width}×${preferredSize.height}`)}</button>}
          {pip && sizeControls && <button type="button" data-companion-reader-ignore="true" data-companion-size-toggle="true" aria-controls={`companion-size-${id}`} aria-expanded={sizeExpanded && !minimized} onClick={() => {
            setSizeExpanded(!sizeExpanded);
            if (minimized) setMinimized(false);
          }}>{tx("Window size", "窗口尺寸")}</button>}
          <button type="button" data-companion-reader-ignore="true" onClick={onOpenFull}>{tx("Open full room", "打开完整房间")}</button>
          <button type="button" data-companion-reader-ignore="true" aria-controls={`companion-content-${id}`} aria-expanded={!minimized} aria-label={minimized ? tx("Expand Room Companion", "展开房间伴随窗口") : tx("Minimize Room Companion", "最小化房间伴随窗口")} onClick={() => {
            activated.current = false;
            setSizeExpanded(false);
            minimizedRef.current = !minimized;
            setMinimized(!minimized);
            syncReader.current();
          }}>{minimized ? "+" : "−"}</button>
          <button type="button" data-companion-reader-ignore="true" aria-label={tx("Close Room Companion", "关闭房间伴随窗口")} onClick={onClose}>×</button>
        </div>
      </header>
      {needsSizeRestore && preferredSize && <p className="room-companion-size-notice" role="status" data-companion-reader-ignore="true">{tx(
        `Browser kept a different size. Click Use ${preferredSize.width}×${preferredSize.height} to apply your selection.`,
        `浏览器窗口尺寸与所选不同，请点击应用 ${preferredSize.width}×${preferredSize.height}。`
      )}</p>}
      {restoreFailed && <p className="room-companion-error" role="alert" data-companion-reader-ignore="true">{tx(
        "The browser could not resize this window. Try a smaller size or resize it manually.",
        "浏览器无法调整此窗口。请尝试更小的尺寸，或手动调整窗口。"
      )}</p>}
      {pip && sizeControls && sizeExpanded && !minimized && <RoomCompanionSizeControls {...sizeControls} id={`companion-size-${id}`} />}
      <button type="button" className="room-companion-unread" data-companion-reader-ignore={minimized || undefined} disabled={minimized || !room} onClick={markLatest}>
        {tx(`${state.unread} unread · View latest`, `${state.unread} 条未读 · 查看最新`)}
      </button>
      {!minimized && <div className="room-companion-content" id={`companion-content-${id}`}>
        {!pip && <p className="room-companion-capability">{tx("In-app companion. This panel stays inside Character Relay.", "应用内伴随面板，仅显示于 Character Relay 页面内。")}</p>}
        {pip && <p className="room-companion-capability">{tx("Keep the Character Relay tab open.", "请保持 Character Relay 主标签页打开。")}</p>}
        <div ref={history} className="room-companion-history" role="log" aria-live="polite" aria-relevant="additions text" aria-label={tx("Latest five room messages", "房间最近五条消息")} tabIndex={0} onScroll={event => {
          const node = event.currentTarget;
          atLatest.current = node.scrollHeight - node.scrollTop - node.clientHeight < 32;
          syncReader.current();
        }}>
          {!messages.length && <p className="room-companion-empty">{room ? tx("No recent messages.", "暂无最近消息。") : tx("Open full room to select an accessible room.", "打开完整房间，选择有权访问的房间。")}</p>}
          {messages.map(message => <CompactMessage key={message.id} message={message} disabled={sendingDisabled} onReply={id => session.patch({ reply: id })} tx={tx} />)}
          {visibleReceipts.map(item => <article className={`room-companion-receipt is-${item.status}`} key={item.id} data-outbox-id={item.id} data-client-message-id={item.client_message_id} data-delivery-status={item.status} data-reply-to-message-id={item.reply_to_message_id}>
            <header><strong>{item.display_name}</strong><small>{statusLabels[item.status]}</small></header>
            {item.text && <p>{item.text}</p>}
            {item.sticker_resource_key && <small className="room-companion-content-note">🏷️ {tx("Sticker included", "包含贴图")}</small>}
            {item.attachments?.map(attachment => <small className="room-companion-content-note" key={attachment.id}>📎 {attachment.filename}</small>)}
            {item.reason && <small className="room-companion-content-note">{item.reason}</small>}
            {item.status === "uncertain" && <p>{tx("Discord may have received this message. It will not be resent automatically.", "Discord 可能已收到此消息；系统不会自动重发。")}</p>}
          </article>)}
          {receipts.length > visibleReceipts.length && <button type="button" onClick={onOpenFull}>{tx("View more delivery receipts in full room", "在完整房间查看其余发送回执")}</button>}
          {local && <article className={`room-companion-receipt is-${local.phase}`} data-client-message-id={local.payload.client_message_id} data-delivery-status={local.phase} data-reply-to-message-id={local.payload.reply_to_message_id}>
            <header><strong>{local.displayName}</strong><small>{local.phase === "submitting" ? tx("Submitting", "提交中") : tx("Submission result unknown", "提交结果未知")}</small></header>
            {local.payload.text && <p>{local.payload.text}</p>}
            {local.payload.sticker_resource_key && <small className="room-companion-content-note">🏷️ {tx("Sticker included", "包含贴图")}</small>}
            {local.attachments.map(attachment => <small className="room-companion-content-note" key={attachment.id}>📎 {attachment.filename}</small>)}
            {local.phase === "unknown" && <>
              <p>{tx("Acceptance is unknown. An explicit retry uses the same client message ID and original payload.", "接收结果未知。明确重试会使用相同 Client Message ID 与原始内容。")}</p>
              <button type="button" disabled={!state.authenticated || state.busy || state.demoMode || !room?.enabled || !room.can_post || !webRoomCanSubmit(state.connection)} onClick={() => void session.retry()}>{tx("Check / retry safely", "安全核对／重试")}</button>
            </>}
          </article>}
        </div>
        <form className="room-companion-composer" onSubmit={event => {
          event.preventDefault();
          if (!sendingDisabled && !hiddenPayload && state.text.trim()) void session.send();
        }}>
          {state.reply && <div className="room-companion-draft-reply">
            <span>{tx("Replying to", "正在回复")} <strong>{reply?.display_name || tx("message", "消息")}</strong>{reply?.text ? ` · ${reply.text.slice(0, 100)}` : ""}</span>
            <button type="button" disabled={Boolean(state.localSubmission)} onClick={() => session.patch({ reply: "" })}>{tx("Cancel reply", "取消回复")}</button>
          </div>}
          {hiddenPayload && <div className="room-companion-draft-notice" role="status">
            <p>{tx("The shared draft contains attachments or a sticker. Open full room to review and send it.", "共享草稿包含附件或贴图，请打开完整房间检查并发送。")}</p>
            <button type="button" onClick={onOpenFull}>{tx("Review full draft", "检查完整草稿")}</button>
          </div>}
          <label htmlFor={`companion-message-${id}`}>{tx("Message", "消息")}{profile ? ` · ${profile.display_name}` : ""}</label>
          <textarea id={`companion-message-${id}`} rows={2} maxLength={1800} value={state.text} disabled={sendingDisabled} onChange={event => session.patch({ text: event.target.value })} placeholder={tx("Write a message", "输入消息")} />
          <footer><small>{state.text.length}/1800{state.demoMode ? tx(" · Demo is read only", " · 演示模式仅可查看") : !room?.can_post ? tx(" · Read only", " · 仅可查看") : ""}</small><button type="submit" disabled={sendingDisabled || hiddenPayload || !state.text.trim()}>{tx("Send", "发送")}</button></footer>
        </form>
        {state.error && <p className="room-companion-error" role="alert">{state.error}</p>}
      </div>}
    </aside>
  );
}
