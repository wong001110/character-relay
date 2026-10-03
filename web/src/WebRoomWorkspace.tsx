import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { deploymentApi, type DiscordServerCatalog } from "./deploymentApi";
import { useI18n } from "./i18n";
import { WebRoomExpressionPicker } from "./WebRoomExpressionPicker";
import { WebRoomMessage } from "./WebRoomMessage";
import {
  snapshotForRoomTransition,
  unmatchedOutbox,
  withAcceptedOutbox,
  webRoomApi,
  type WebExpression,
  type WebMember,
  type WebProfile,
  type WebRoom,
  type WebSend,
  type WebSnapshot,
  type WebUpload
} from "./webRoomApi";
import "./web-room.css";

const empty: WebSnapshot = { room_id: "", messages: [], outbox: [], history_limit: 64 };

type LocalSubmission = {
  room: string;
  payload: WebSend;
  phase: "submitting" | "accepted" | "unknown";
  displayName: string;
  avatarUrl: string;
  attachments: WebUpload[];
};

function Avatar({ url, name }: { url: string; name: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return url.startsWith("https://") && !failed
    ? <img className="web-room-avatar" src={url} alt="" referrerPolicy="no-referrer" loading="lazy" onError={() => setFailed(true)} />
    : <span className="web-room-avatar" aria-hidden="true">{name.slice(0, 1) || "?"}</span>;
}

function time(value: string | null) {
  const date = value ? new Date(value) : null;
  return date && Number.isFinite(date.getTime())
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";
}

export function WebRoomWorkspace({ demoMode = false }: { demoMode?: boolean }) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const tx = (en: string, cn: string) => zh ? cn : en;
  const [params, setParams] = useSearchParams();
  const roomId = params.get("room") ?? "";

  const [rooms, setRooms] = useState<WebRoom[]>([]);
  const [profiles, setProfiles] = useState<WebProfile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [snapshot, setSnapshot] = useState<WebSnapshot>(empty);
  const [connection, setConnection] = useState("disconnected");
  const [streamVersion, setStreamVersion] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [reply, setReply] = useState("");
  const [name, setName] = useState("");
  const [avatar, setAvatar] = useState("");
  const [editId, setEditId] = useState("");
  const [members, setMembers] = useState<WebMember[]>([]);
  const [memberId, setMemberId] = useState("");
  const [canPost, setCanPost] = useState(true);
  const [catalog, setCatalog] = useState<DiscordServerCatalog[]>([]);
  const [publishServer, setPublishServer] = useState("");
  const [channelId, setChannelId] = useState("");
  const [threadId, setThreadId] = useState("");
  const [roomName, setRoomName] = useState("");
  const [expressions, setExpressions] = useState<WebExpression[]>([]);
  const [stickerResourceKey, setStickerResourceKey] = useState("");
  const [attachments, setAttachments] = useState<WebUpload[]>([]);
  const [localSubmission, setLocalSubmission] = useState<LocalSubmission | null>(null);
  const [unread, setUnread] = useState(0);

  const end = useRef<HTMLDivElement>(null);
  const messagesNode = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const nearBottom = useRef(true);
  const activeRoomId = useRef("");
  const attachmentsRef = useRef<WebUpload[]>([]);

  const room = rooms.find(item => item.id === roomId);
  const profile = profiles.find(item => item.id === profileId);
  const latestMessageId = snapshot.messages.at(-1)?.id ?? "";

  const releaseAttachmentPreviews = (items: WebUpload[]) => {
    for (const item of items) {
      if (item.preview_url) URL.revokeObjectURL(item.preview_url);
    }
  };

  const clearAttachments = () => {
    setAttachments(current => {
      releaseAttachmentPreviews(current);
      return [];
    });
  };

  const report = (reason: unknown) =>
    setError(reason instanceof Error ? reason.message : "request_failed");

  async function refresh() {
    const [nextRooms, nextProfiles] = await Promise.all([
      webRoomApi.rooms(),
      webRoomApi.profiles()
    ]);
    const stableRooms =
      roomId && room && !nextRooms.some(item => item.id === roomId)
        ? [...nextRooms, room]
        : nextRooms;
    setRooms(stableRooms);
    setProfiles(nextProfiles);
    setProfileId(previous =>
      nextProfiles.some(item => item.id === previous)
        ? previous
        : nextProfiles[0]?.id ?? ""
    );
  }

  useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);

  useEffect(() => () => releaseAttachmentPreviews(attachmentsRef.current), []);

  useEffect(() => {
    let active = true;
    Promise.all([webRoomApi.rooms(), webRoomApi.profiles()])
      .then(([nextRooms, nextProfiles]) => {
        if (!active) return;
        setRooms(nextRooms);
        setProfiles(nextProfiles);
        setProfileId(nextProfiles[0]?.id ?? "");
      })
      .catch(reason => {
        if (active) report(reason);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const nextRoomId = room?.id ?? "";
    const roomChanged = activeRoomId.current !== nextRoomId;
    if (roomChanged) {
      activeRoomId.current = nextRoomId;
      setReply("");
      setMembers([]);
      setExpressions([]);
      setStickerResourceKey("");
      clearAttachments();
      setUnread(0);
      setLocalSubmission(null);
      nearBottom.current = true;
    }
    setSnapshot(current => snapshotForRoomTransition(current, nextRoomId));
    setConnection(room?.enabled ? "connecting" : "disconnected");
    if (!room?.enabled) return;

    let closed = false;
    const stream = new EventSource(webRoomApi.eventsUrl(room.id));
    stream.addEventListener("snapshot", event => {
      if (closed) return;
      try {
        const next: WebSnapshot = JSON.parse((event as MessageEvent<string>).data);
        if (
          next.room_id !== room.id ||
          !Array.isArray(next.messages) ||
          !Array.isArray(next.outbox)
        ) {
          throw new Error("invalid_room_snapshot");
        }
        setSnapshot(current => {
          if (current.room_id === next.room_id && current.messages.length) {
            const previousIds = new Set(current.messages.map(item => item.id));
            const newCount = next.messages.filter(item => !previousIds.has(item.id)).length;
            if (newCount && !nearBottom.current) setUnread(value => value + newCount);
            if (nearBottom.current) setUnread(0);
          } else {
            setUnread(0);
          }
          return next;
        });
        setConnection("connected");
      } catch {
        setError("invalid_room_snapshot");
        setSnapshot(empty);
        setUnread(0);
        stream.close();
        setConnection("unavailable");
      }
    });
    stream.addEventListener("revoked", () => {
      if (closed) return;
      setSnapshot(empty);
      setReply("");
      setUnread(0);
      setRooms(current => current.filter(item => item.id !== room.id));
      setParams({});
      setConnection("unavailable");
      stream.close();
    });
    stream.addEventListener("unavailable", () => {
      if (closed) return;
      setConnection("unavailable");
      stream.close();
    });
    stream.onerror = () => {
      if (!closed) setConnection("reconnecting");
    };
    return () => {
      closed = true;
      stream.close();
    };
  }, [room?.id, room?.enabled, streamVersion]);

  useEffect(() => {
    if (!room?.enabled) return;
    let active = true;
    webRoomApi.expressions(room.id)
      .then(items => {
        if (active) setExpressions(items);
      })
      .catch(reason => {
        if (active) report(reason);
      });
    return () => {
      active = false;
    };
  }, [room?.id, room?.enabled, streamVersion]);

  useEffect(() => {
    if (nearBottom.current) end.current?.scrollIntoView({ block: "end" });
  }, [latestMessageId, snapshot.outbox.length]);

  useEffect(() => {
    if (
      localSubmission &&
      snapshot.outbox.some(item => item.client_message_id === localSubmission.payload.client_message_id)
    ) {
      setLocalSubmission(null);
    }
  }, [snapshot.outbox, localSubmission]);

  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await run();
    } catch (reason) {
      report(reason);
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    await action(async () => {
      const saved = await webRoomApi.profile(
        { display_name: name, avatar_url: avatar },
        profiles.find(item => item.id === editId)
      );
      await refresh();
      setProfileId(saved.id);
      setEditId("");
      setName("");
      setAvatar("");
    });
  }

  function insertEmoji(token: string) {
    const node = textarea.current;
    const start = node?.selectionStart ?? text.length;
    const finish = node?.selectionEnd ?? start;
    const next = text.slice(0, start) + token + text.slice(finish);
    setText(next);
    requestAnimationFrame(() => {
      if (!node) return;
      const cursor = start + token.length;
      node.focus();
      node.setSelectionRange(cursor, cursor);
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (
      !room ||
      !profile ||
      (!text.trim() && !stickerResourceKey && !attachments.length) ||
      localSubmission
    ) return;

    const pending: LocalSubmission = {
      room: room.id,
      payload: {
        client_message_id: crypto.randomUUID(),
        profile_id: profile.id,
        text,
        reply_to_message_id: reply,
        sticker_resource_key: stickerResourceKey,
        attachment_ids: attachments.map(item => item.id)
      },
      phase: "submitting",
      displayName: profile.display_name,
      avatarUrl: profile.avatar_url,
      attachments: [...attachments]
    };
    setLocalSubmission(pending);
    await dispatch(pending);
  }

  async function dispatch(pending: LocalSubmission) {
    setBusy(true);
    setError("");
    setLocalSubmission({ ...pending, phase: "submitting" });
    try {
      const accepted = await webRoomApi.send(pending.room, pending.payload);
      setSnapshot(current => withAcceptedOutbox(current, pending.room, accepted));
      setLocalSubmission(null);
      setText("");
      setReply("");
      setStickerResourceKey("");
      clearAttachments();
      nearBottom.current = true;
    } catch (reason) {
      setLocalSubmission({ ...pending, phase: "unknown" });
      report(reason);
    } finally {
      setBusy(false);
    }
  }

  async function addImages(files: Iterable<File> | null) {
    if (!room || !room.can_post || demoMode || busy || localSubmission || !files) return;
    const selected = Array.from(files);
    if (!selected.length) return;
    if (attachments.length + selected.length > 4) {
      setError(tx("A message can include up to 4 images.", "每条消息最多可附加 4 张图片。"));
      return;
    }
    setBusy(true);
    setError("");
    let firstFailure: unknown = null;
    try {
      for (const file of selected) {
        try {
          const uploaded = await webRoomApi.uploadImage(room.id, file);
          const preview = URL.createObjectURL(file);
          setAttachments(current => [...current, { ...uploaded, preview_url: preview }].slice(0, 4));
        } catch (reason) {
          firstFailure ??= reason;
        }
      }
      if (firstFailure) report(firstFailure);
    } finally {
      setBusy(false);
    }
  }

  function removeAttachment(id: string) {
    setAttachments(current => {
      const removed = current.find(item => item.id === id);
      if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
      return current.filter(item => item.id !== id);
    });
  }

  function jumpTo(messageId: string) {
    const node = document.getElementById(`web-room-message-${messageId}`);
    if (!node) return;
    nearBottom.current = false;
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    node.classList.add("is-jump-target");
    window.setTimeout(() => node.classList.remove("is-jump-target"), 1200);
  }

  function jumpLatest() {
    nearBottom.current = true;
    setUnread(0);
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  const server = catalog.find(
    item => `${item.connection_id}:${item.guild_id}` === publishServer
  );
  const replyMessage = snapshot.messages.find(item => item.id === reply);
  const selectedSticker = expressions.find(item => item.resource_key === stickerResourceKey);

  const statusLabel = (status: string) => ({
    pending: tx("Website accepted", "网站已接收"),
    claimed: tx("Sending to Discord", "正在发送到 Discord"),
    delivered: tx("Delivered to Discord", "Discord 已送达"),
    failed: tx("Failed", "发送失败"),
    uncertain: tx("Delivery uncertain", "送达状态不确定"),
    cancelled: tx("Cancelled", "已取消")
  } as Record<string, string>)[status] ?? status;

  return (
    <main className="web-room-page">
      <header className="web-room-heading">
        <div>
          <h1>{tx("Rooms", "聊天室")}</h1>
          <p>{tx(
            "Discord and website participants, in the same conversation.",
            "Discord 与网页参与者，共用一个对话。"
          )}</p>
        </div>
        <button type="button" className="paper-button" disabled={busy} onClick={() => void action(refresh)}>
          {tx("Refresh rooms", "刷新房间")}
        </button>
      </header>

      {demoMode && <p role="status">{tx("Public Demo is read-only.", "公开演示仅供查看。")}</p>}
      {error && <p role="alert" className="error-note">{error}</p>}

      <div className="web-room-layout">
        <aside className="web-room-sidebar" aria-label={tx("Room and identity", "房间与身份")}>
          <label>
            {tx("Room", "房间")}
            <select
              value={roomId}
              disabled={busy || Boolean(localSubmission)}
              onChange={event => {
                setParams(event.target.value ? { room: event.target.value } : {});
                setText("");
              }}
            >
              <option value="">{tx("Select a room", "选择房间")}</option>
              {rooms.map(item => (
                <option key={item.id} value={item.id}>
                  {item.name}{item.enabled ? "" : tx(" (paused)", "（暂停）")}
                </option>
              ))}
            </select>
          </label>
          {!rooms.length && (
            <p>{tx(
              "No published rooms have been granted to this account. Server membership alone does not reveal a room.",
              "此账号尚无获授权的网页房间。加入服务器不等于拥有房间访问权。"
            )}</p>
          )}

          <label>
            {tx("Chat as", "发言身份")}
            <select
              value={profileId}
              disabled={busy || Boolean(localSubmission)}
              onChange={event => setProfileId(event.target.value)}
            >
              <option value="">{tx("Choose a profile", "选择身份")}</option>
              {profiles.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}
            </select>
          </label>
          {profile && (
            <div className="web-room-profile">
              <Avatar url={profile.avatar_url} name={profile.display_name} />
              <span>{profile.display_name}<small>{tx("Web participant", "网页参与者")}</small></span>
            </div>
          )}

          <details>
            <summary>{tx("Edit / create a profile", "编辑／创建身份")}</summary>
            <form onSubmit={saveProfile}>
              <label>
                {tx("Profile to edit", "要编辑的身份")}
                <select
                  value={editId}
                  disabled={busy}
                  onChange={event => {
                    setEditId(event.target.value);
                    const selected = profiles.find(item => item.id === event.target.value);
                    setName(selected?.display_name ?? "");
                    setAvatar(selected?.avatar_url ?? "");
                  }}
                >
                  <option value="">{tx("New profile", "新身份")}</option>
                  {profiles.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                </select>
              </label>
              <label>{tx("Display name", "显示名")}<input required maxLength={80} value={name} onChange={event => setName(event.target.value)} /></label>
              <label>{tx("Avatar URL (HTTPS, optional)", "头像网址（HTTPS，可选）")}<input type="url" maxLength={1000} value={avatar} onChange={event => setAvatar(event.target.value)} placeholder="https://…" /></label>
              <small>{tx(
                "Your name and avatar do not change identity or permissions. External images may disclose your IP to their host.",
                "名称与头像不改变身份或权限；外部图片可能让图片主机得知你的 IP。"
              )}</small>
              <button className="paper-button" disabled={busy || demoMode}>{tx("Save profile", "保存身份")}</button>
            </form>
          </details>

          <details onToggle={event => {
            if (event.currentTarget.open && !catalog.length) {
              void deploymentApi.listDiscordServerCatalog().then(setCatalog).catch(report);
            }
          }}>
            <summary>{tx("Publish a room (connection owner)", "发布房间（连接所有者）")}</summary>
            <form onSubmit={event => {
              event.preventDefault();
              if (!server) return;
              void action(async () => {
                const saved = await webRoomApi.publish({
                  connection_id: server.connection_id,
                  guild_id: server.guild_id,
                  channel_id: channelId,
                  thread_id: threadId.trim(),
                  name: roomName.trim()
                });
                await refresh();
                setParams({ room: saved.id });
              });
            }}>
              <label>
                {tx("Server", "服务器")}
                <select required value={publishServer} onChange={event => {
                  setPublishServer(event.target.value);
                  setChannelId("");
                }}>
                  <option value="">{tx("Choose server", "选择服务器")}</option>
                  {catalog.map(item => (
                    <option key={`${item.connection_id}:${item.guild_id}`} value={`${item.connection_id}:${item.guild_id}`}>
                      {item.guild_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {tx("Channel", "频道")}
                <select required value={channelId} onChange={event => {
                  setChannelId(event.target.value);
                  setRoomName(server?.channels.find(item => item.id === event.target.value)?.name ?? "");
                }}>
                  <option value="">{tx("Choose channel", "选择频道")}</option>
                  {server?.channels.filter(item => ["text", "announcement", "forum", "media"].includes(item.type)).map(item => (
                    <option key={item.id} value={item.id}>#{item.name}</option>
                  ))}
                </select>
              </label>
              <label>{tx("Native Thread ID (optional)", "原生 Thread ID（可选）")}<input value={threadId} maxLength={200} onChange={event => setThreadId(event.target.value)} /></label>
              <label>{tx("Room name", "房间名称")}<input required value={roomName} maxLength={80} onChange={event => setRoomName(event.target.value)} /></label>
              <small>{tx(
                "The connector must be able to read the exact destination and manage its webhook. Other accounts need a separate room grant.",
                "Connector 必须能读取此频道并管理 webhook；其他账号需要单独的房间授权。"
              )}</small>
              <button className="paper-button" disabled={busy || demoMode}>{tx("Publish room", "发布房间")}</button>
            </form>
          </details>
        </aside>

        <section className="web-room-conversation" aria-label={tx("Conversation", "对话")}>
          <header>
            <h2>{room ? `# ${room.name}` : tx("Choose a room", "选择房间")}</h2>
            <span role="status" className={`web-room-connection is-${connection}`}>
              {tx(
                connection,
                ({
                  disconnected: "未连接",
                  connecting: "连接中",
                  connected: "实时连接",
                  reconnecting: "重新连接中",
                  unavailable: "访问或连接不可用"
                } as Record<string, string>)[connection] ?? connection
              )}
            </span>
          </header>
          <p className="web-room-history-note">{tx(
            "Latest 64 messages. Reconnect keeps the visible transcript mounted while fresh state arrives.",
            "显示最近 64 条消息；重连时保留当前内容，收到新状态后原位更新。"
          )}</p>

          <div
            ref={messagesNode}
            className="web-room-messages"
            role="log"
            aria-live="polite"
            aria-relevant="additions text"
            aria-label={tx("Messages", "消息")}
            onScroll={event => {
              const node = event.currentTarget;
              nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 100;
              if (nearBottom.current) setUnread(0);
            }}
          >
            {!snapshot.messages.length && (
              <p className="web-room-empty">
                {connection === "connected"
                  ? tx("No recent messages.", "尚无最近消息。")
                  : tx("Messages are shown after current room access is confirmed.", "确认当前房间访问权后显示消息。")}
              </p>
            )}

            {snapshot.messages.map(message => (
              <WebRoomMessage
                key={message.id}
                message={message}
                canPost={Boolean(room?.can_post)}
                profileId={profileId}
                expressions={expressions}
                disabled={busy || demoMode || Boolean(localSubmission)}
                onReply={setReply}
                onJump={jumpTo}
                onReact={(target, emojiKey, emojiName, enabled) => {
                  if (!room || !profile) return;
                  void action(async () => {
                    const payload = { profile_id: profile.id, emoji_key: emojiKey, emoji_name: emojiName };
                    if (enabled) await webRoomApi.react(room.id, target.id, payload);
                    else await webRoomApi.unreact(room.id, target.id, payload);
                  });
                }}
                tx={tx}
              />
            ))}

            {unmatchedOutbox(snapshot).map(item => (
              <article className={`web-room-message web-room-pending is-${item.status}`} key={`pending:${item.id}`}>
                <Avatar url={item.avatar_url} name={item.display_name} />
                <div>
                  <header><strong>{item.display_name}</strong><small>{statusLabel(item.status)} · {time(item.created_at)}</small></header>
                  {item.text && <p className="room-preserve-text">{item.text}</p>}
                  {item.sticker_resource_key && (
                    <small>🏷️ {expressions.find(expression => expression.resource_key === item.sticker_resource_key)?.name ?? tx("Sticker", "贴图")}</small>
                  )}
                  {item.attachments?.map(attachment => (
                    <small key={attachment.id}>🖼️ {attachment.filename}</small>
                  ))}
                  {item.reason && <small>{item.reason}</small>}
                  {item.status === "uncertain" && <p>{tx(
                    "Discord may have received this message. It will not be resent automatically.",
                    "Discord 可能已收到此消息；系统不会自动重发。"
                  )}</p>}
                </div>
              </article>
            ))}

            {localSubmission && !snapshot.outbox.some(item => item.client_message_id === localSubmission.payload.client_message_id) && (
              <article className={`web-room-message web-room-pending is-${localSubmission.phase}`}>
                <Avatar url={localSubmission.avatarUrl} name={localSubmission.displayName} />
                <div>
                  <header>
                    <strong>{localSubmission.displayName}</strong>
                    <small>{
                      localSubmission.phase === "submitting"
                        ? tx("Submitting", "提交中")
                        : localSubmission.phase === "accepted"
                          ? tx("Website accepted", "网站已接收")
                          : tx("Submission result unknown", "提交结果未知")
                    }</small>
                  </header>
                  {localSubmission.payload.text && <p className="room-preserve-text">{localSubmission.payload.text}</p>}
                  {localSubmission.payload.sticker_resource_key && (
                    <small>🏷️ {expressions.find(expression => expression.resource_key === localSubmission.payload.sticker_resource_key)?.name ?? tx("Sticker", "贴图")}</small>
                  )}
                  {localSubmission.attachments.map(attachment => (
                    <small key={attachment.id}>🖼️ {attachment.filename}</small>
                  ))}
                </div>
              </article>
            )}
            <div ref={end} />
          </div>

          {unread > 0 && (
            <button type="button" className="web-room-unread-button" onClick={jumpLatest}>
              {tx(`${unread} new message${unread === 1 ? "" : "s"} · Jump to latest`, `${unread} 条新消息 · 跳到最新`)}
            </button>
          )}

          <form
            className="web-room-composer"
            onSubmit={submit}
            onDragOver={event => {
              if (event.dataTransfer.types.includes("Files")) event.preventDefault();
            }}
            onDrop={event => {
              if (!event.dataTransfer.files.length) return;
              event.preventDefault();
              void addImages(event.dataTransfer.files);
            }}
          >
            {reply && (
              <div className="web-room-reply-preview">
                <span>
                  {tx("Replying to", "正在回复")} <strong>{replyMessage?.display_name ?? tx("message", "消息")}</strong>
                  {replyMessage?.text ? <> · {replyMessage.text.slice(0, 100)}</> : null}
                </span>
                <button type="button" disabled={Boolean(localSubmission)} onClick={() => setReply("")}>
                  {tx("Cancel reply", "取消回复")}
                </button>
              </div>
            )}

            <label>
              {tx("Message", "消息")}
              <textarea
                ref={textarea}
                value={text}
                maxLength={1800}
                rows={3}
                disabled={busy || Boolean(localSubmission) || demoMode || !room?.can_post}
                onChange={event => setText(event.target.value)}
                onPaste={event => {
                  const images = Array.from(event.clipboardData.files).filter(file =>
                    !file.type || file.type.startsWith("image/")
                  );
                  if (!images.length) return;
                  event.preventDefault();
                  void addImages(images);
                }}
                placeholder={tx(
                  "Write a message. Name a Character explicitly to ask it to reply.",
                  "输入消息。明确叫出角色名称可请求回复。"
                )}
              />
            </label>

            <div className="web-room-upload-row">
              <label className="web-room-upload-picker">
                <span>{tx("＋ Add images", "＋ 添加图片")}</span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  multiple
                  disabled={busy || Boolean(localSubmission) || demoMode || !room?.can_post || attachments.length >= 4}
                  onChange={event => {
                    void addImages(event.currentTarget.files);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              {attachments.map(attachment => (
                <span className="web-room-upload-chip" key={attachment.id}>
                  {attachment.preview_url
                    ? <img src={attachment.preview_url} alt="" />
                    : <span aria-hidden="true">🖼️</span>}
                  <span title={attachment.filename}>{attachment.filename}</span>
                  <button
                    type="button"
                    disabled={busy || Boolean(localSubmission)}
                    aria-label={tx(`Remove ${attachment.filename}`, `移除 ${attachment.filename}`)}
                    onClick={() => removeAttachment(attachment.id)}
                  >×</button>
                </span>
              ))}
            </div>

            <WebRoomExpressionPicker
              expressions={expressions}
              disabled={busy || Boolean(localSubmission) || demoMode || !room?.can_post}
              selectedStickerKey={stickerResourceKey}
              onEmoji={insertEmoji}
              onSticker={resource => setStickerResourceKey(resource?.resource_key ?? "")}
              tx={tx}
            />

            <footer>
              <small>
                {text.length}/1800 · {tx(
                  "Paste, drop, or attach images. Mentions never ping everyone or roles; media is not appended to LLM prose.",
                  "可粘贴、拖入或附加图片。提及不会触发全体或身份组通知；媒体不会作为裸链接塞进 LLM 文本。"
                )}
              </small>
              <button
                className="paper-button"
                disabled={
                  busy ||
                  Boolean(localSubmission) ||
                  demoMode ||
                  !room?.can_post ||
                  !profile ||
                  (!text.trim() && !stickerResourceKey && !attachments.length) ||
                  connection !== "connected"
                }
              >
                {tx("Send", "发送")}
              </button>
            </footer>

            {localSubmission?.phase === "unknown" && (
              <div role="status" className="web-room-delivery-uncertain">
                <p>{tx(
                  "The website did not receive a definitive acceptance result. Retrying uses the same client message ID.",
                  "网站没有收到明确的接收结果。重试会使用相同的 Client Message ID，不会创建第二个逻辑发送。"
                )}</p>
                <button type="button" className="paper-button" disabled={busy || demoMode} onClick={() => void dispatch(localSubmission)}>
                  {tx("Check / retry safely", "安全核对／重试")}
                </button>
                <button type="button" disabled={busy} onClick={() => setLocalSubmission(null)}>
                  {tx("Clear local pending state", "清除本地待确认状态")}
                </button>
              </div>
            )}
          </form>
        </section>
      </div>

      {room?.can_manage && (
        <details className="web-room-management" onToggle={event => {
          if (event.currentTarget.open) void webRoomApi.members(room.id).then(setMembers).catch(report);
        }}>
          <summary>{tx("Room access and pause", "房间授权与暂停")}</summary>
          <p>{tx(
            "Accounts must first join this Discord server workspace. Grant only the specific people allowed to read this channel or private Thread.",
            "账号需要先加入此 Discord 服务器工作区。仅授权有权查看该频道或私密 Thread 的参与者。"
          )}</p>
          <button type="button" className="paper-button" disabled={busy || demoMode} onClick={() => void action(async () => {
            await webRoomApi.configure(room.id, !room.enabled);
            await refresh();
          })}>
            {room.enabled ? tx("Pause web room", "暂停网页房间") : tx("Resume web room", "恢复网页房间")}
          </button>
          <form className="room-controls" onSubmit={event => {
            event.preventDefault();
            void action(async () => {
              await webRoomApi.grant(room.id, memberId.trim(), canPost);
              setMembers(await webRoomApi.members(room.id));
              setMemberId("");
            });
          }}>
            <label>{tx("Account user ID", "账号 User ID")}<input required value={memberId} maxLength={120} onChange={event => setMemberId(event.target.value)} /></label>
            <label><input type="checkbox" checked={canPost} onChange={event => setCanPost(event.target.checked)} />{tx("Allow sending", "允许发送")}</label>
            <button className="paper-button" disabled={busy || demoMode}>{tx("Grant / update", "授权／更新")}</button>
          </form>
          <ul>
            {members.map(item => (
              <li key={item.user_id}>
                <span>{item.display_name || item.user_id} — {item.can_post ? tx("read + send", "查看＋发送") : tx("read only", "仅查看")}</span>
                {" "}
                <button type="button" disabled={busy || demoMode} onClick={() => {
                  if (window.confirm(tx(
                    "Revoke this account's access to this web room?",
                    "撤销此账号对该网页房间的访问权？"
                  ))) {
                    void action(async () => {
                      await webRoomApi.revoke(room.id, item.user_id);
                      setMembers(await webRoomApi.members(room.id));
                    });
                  }
                }}>{tx("Revoke", "撤销")}</button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {selectedSticker && selectedSticker.resource_type === "sticker" && null}
    </main>
  );
}
