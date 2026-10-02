import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { deploymentApi, type DiscordServerCatalog } from "./deploymentApi";
import { useI18n } from "./i18n";
import { snapshotForRoomTransition, unmatchedOutbox, webRoomApi, type WebMember, type WebProfile, type WebRoom, type WebSend, type WebSnapshot } from "./webRoomApi";
import "./web-room.css";

const empty: WebSnapshot = {room_id: "", messages: [], outbox: [], history_limit: 64};
function Avatar({url, name}: {url: string; name: string}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return url.startsWith("https://") && !failed ? <img className="web-room-avatar" src={url} alt="" referrerPolicy="no-referrer" loading="lazy" onError={() => setFailed(true)} /> : <span className="web-room-avatar" aria-hidden="true">{name.slice(0, 1) || "?"}</span>;
}
function time(value: string | null) {
  const date = value ? new Date(value) : null;
  return date && Number.isFinite(date.getTime()) ? date.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : "";
}

export function WebRoomWorkspace({demoMode = false}: {demoMode?: boolean}) {
  const {language} = useI18n(); const zh = language === "zh-CN";
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
  const [text, setText] = useState(""); const [reply, setReply] = useState("");
  const [name, setName] = useState(""); const [avatar, setAvatar] = useState("");
  const [editId, setEditId] = useState("");
  const [retry, setRetry] = useState<{room: string; payload: WebSend} | null>(null);
  const [members, setMembers] = useState<WebMember[]>([]);
  const [memberId, setMemberId] = useState(""); const [canPost, setCanPost] = useState(true);
  const [catalog, setCatalog] = useState<DiscordServerCatalog[]>([]);
  const [publishServer, setPublishServer] = useState(""); const [channelId, setChannelId] = useState("");
  const [threadId, setThreadId] = useState(""); const [roomName, setRoomName] = useState("");
  const end = useRef<HTMLDivElement>(null); const nearBottom = useRef(true);\n  const activeRoomId = useRef("");
  const room = rooms.find(item => item.id === roomId);
  const profile = profiles.find(item => item.id === profileId);
  const report = (reason: unknown) => setError(reason instanceof Error ? reason.message : "request_failed");
  async function refresh() {
    const [nextRooms, nextProfiles] = await Promise.all([webRoomApi.rooms(), webRoomApi.profiles()]);
    setRooms(nextRooms); setProfiles(nextProfiles); setStreamVersion(version => version + 1);
    setProfileId(previous => nextProfiles.some(item => item.id === previous) ? previous : nextProfiles[0]?.id ?? "");
  }
  useEffect(() => { let active = true; Promise.all([webRoomApi.rooms(), webRoomApi.profiles()]).then(([r, p]) => {
    if (!active) return; setRooms(r); setProfiles(p); setProfileId(p[0]?.id ?? "");
  }).catch(reason => { if (active) report(reason); }); return () => {active = false;}; }, []);
  useEffect(() => {
    const nextRoomId = room?.id ?? "";
    setSnapshot(current => snapshotForRoomTransition(current, nextRoomId));
    if (snapshot.room_id !== nextRoomId) {
      setReply("");
      setMembers([]);
    }
    setConnection(room?.enabled ? "connecting" : "disconnected");
    if (!room?.enabled) return;
    let closed = false;
    const stream = new EventSource(webRoomApi.eventsUrl(room.id));
    stream.addEventListener("snapshot", event => {
      if (closed) return;
      try {
        const next: WebSnapshot = JSON.parse((event as MessageEvent<string>).data);
        if (next.room_id !== room.id || !Array.isArray(next.messages) || !Array.isArray(next.outbox)) throw new Error("invalid_room_snapshot");
        // Same-room refresh/reconnect keeps the current list mounted until the new
        // authoritative snapshot arrives. Stable message keys let React update in place.
        setSnapshot(next); setConnection("connected");
      } catch {
        setError("invalid_room_snapshot");
        setSnapshot(empty);
        stream.close();
        setConnection("unavailable");
      }
    });
    stream.addEventListener("revoked", () => {
      if (closed) return;
      setSnapshot(empty);
      setReply("");
      setConnection("unavailable");
      stream.close();
    });
    // EventSource reconnects itself. Keep the last authorized snapshot visible while
    // transport is recovering instead of flashing an empty conversation.
    stream.onerror = () => { if (!closed) setConnection("reconnecting"); };
    return () => {closed = true; stream.close();};
  }, [room?.id, room?.enabled, streamVersion]);
  useEffect(() => {
    if (nearBottom.current) end.current?.scrollIntoView({block: "end"});
  }, [snapshot.messages.length, snapshot.outbox.length]);
  async function action(run: () => Promise<void>) { setBusy(true); setError(""); try {await run();} catch (reason) {report(reason);} finally {setBusy(false);} }
  async function saveProfile(event: FormEvent) {
    event.preventDefault(); await action(async () => {
      const saved = await webRoomApi.profile({display_name: name, avatar_url: avatar}, profiles.find(item => item.id === editId));
      await refresh(); setProfileId(saved.id); setEditId(""); setName(""); setAvatar("");
    });
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!room || !profile || !text.trim() || retry) return;
    const pending = {room: room.id, payload: {client_message_id: crypto.randomUUID(), profile_id: profile.id, text, reply_to_message_id: reply}};
    setRetry(pending);
    await dispatch(pending);
  }
  async function dispatch(pending: {room: string; payload: WebSend}) {
    await action(async () => {
      await webRoomApi.send(pending.room, pending.payload);
      setRetry(null); setText(""); setReply(""); nearBottom.current = true;
      // SSE is the display authority; a successful POST is only acceptance, never delivery.
    });
  }
  const server = catalog.find(item => `${item.connection_id}:${item.guild_id}` === publishServer);
  return <main className="web-room-page">
    <header className="web-room-heading"><div><h1>{tx("Rooms", "聊天室")}</h1><p>{tx("Discord and website participants, in the same conversation.", "Discord 与网页参与者，共用一个对话。")}</p></div>
      <button type="button" className="paper-button" disabled={busy} onClick={() => void action(refresh)}>{tx("Refresh rooms", "刷新房间")}</button></header>
    {demoMode && <p role="status">{tx("Public Demo is read-only.", "公开演示仅供查看。")}</p>}
    {error && <p role="alert" className="error-note">{error}</p>}
    <div className="web-room-layout">
      <aside className="web-room-sidebar" aria-label={tx("Room and identity", "房间与身份")}>
        <label>{tx("Room", "房间")}<select value={roomId} disabled={busy || Boolean(retry)} onChange={event => {setParams(event.target.value ? {room: event.target.value} : {}); setText("");}}><option value="">{tx("Select a room", "选择房间")}</option>{rooms.map(item => <option key={item.id} value={item.id}>{item.name}{item.enabled ? "" : tx(" (paused)", "（暂停）")}</option>)}</select></label>
        {!rooms.length && <p>{tx("No published rooms have been granted to this account. Server membership alone does not reveal a room.", "此账号尚无获授权的网页房间。加入服务器不等于拥有房间访问权。")}</p>}
        <label>{tx("Chat as", "发言身份")}<select value={profileId} disabled={busy || Boolean(retry)} onChange={event => setProfileId(event.target.value)}><option value="">{tx("Choose a profile", "选择身份")}</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
        {profile && <div className="web-room-profile"><Avatar url={profile.avatar_url} name={profile.display_name}/><span>{profile.display_name}<small>{tx("Web participant", "网页参与者")}</small></span></div>}
        <details><summary>{tx("Edit / create a profile", "编辑／创建身份")}</summary><form onSubmit={saveProfile}>
          <label>{tx("Profile to edit", "要编辑的身份")}<select value={editId} disabled={busy} onChange={event => {setEditId(event.target.value); const selected = profiles.find(item => item.id === event.target.value); setName(selected?.display_name ?? ""); setAvatar(selected?.avatar_url ?? "");}}><option value="">{tx("New profile", "新身份")}</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
          <label>{tx("Display name", "显示名")}<input required maxLength={80} value={name} onChange={event => setName(event.target.value)}/></label>
          <label>{tx("Avatar URL (HTTPS, optional)", "头像网址（HTTPS，可选）")}<input type="url" maxLength={1000} value={avatar} onChange={event => setAvatar(event.target.value)} placeholder="https://…"/></label>
          <small>{tx("Your name and avatar do not change identity or permissions. External images may disclose your IP to their host.", "名称与头像不改变身份或权限；外部图片可能让图片主机得知你的 IP。")}</small>
          <button className="paper-button" disabled={busy || demoMode}>{tx("Save profile", "保存身份")}</button></form></details>
        <details onToggle={event => {if (event.currentTarget.open && !catalog.length) void deploymentApi.listDiscordServerCatalog().then(setCatalog).catch(report);}}>
          <summary>{tx("Publish a room (connection owner)", "发布房间（连接所有者）")}</summary>
          <form onSubmit={event => {event.preventDefault(); if (!server) return; void action(async () => {const saved = await webRoomApi.publish({connection_id: server.connection_id, guild_id: server.guild_id, channel_id: channelId, thread_id: threadId.trim(), name: roomName.trim()}); await refresh(); setParams({room: saved.id});});}}>
            <label>{tx("Server", "服务器")}<select required value={publishServer} onChange={event => {setPublishServer(event.target.value); setChannelId("");}}><option value="">{tx("Choose server", "选择服务器")}</option>{catalog.map(item => <option key={`${item.connection_id}:${item.guild_id}`} value={`${item.connection_id}:${item.guild_id}`}>{item.guild_name}</option>)}</select></label>
            <label>{tx("Channel", "频道")}<select required value={channelId} onChange={event => {setChannelId(event.target.value); setRoomName(server?.channels.find(item => item.id === event.target.value)?.name ?? "");}}><option value="">{tx("Choose channel", "选择频道")}</option>{server?.channels.filter(item => ["text", "announcement", "forum", "media"].includes(item.type)).map(item => <option key={item.id} value={item.id}>#{item.name}</option>)}</select></label>
            <label>{tx("Native Thread ID (optional)", "原生 Thread ID（可选）")}<input value={threadId} maxLength={200} onChange={event => setThreadId(event.target.value)}/></label>
            <label>{tx("Room name", "房间名称")}<input required value={roomName} maxLength={80} onChange={event => setRoomName(event.target.value)}/></label>
            <small>{tx("The connector must be able to read the exact destination and manage its webhook. Other accounts need a separate room grant.", "Connector 必须能读取此频道并管理 webhook；其他账号需要单独的房间授权。")}</small>
            <button className="paper-button" disabled={busy || demoMode}>{tx("Publish room", "发布房间")}</button>
          </form>
        </details>
      </aside>
      <section className="web-room-conversation" aria-label={tx("Conversation", "对话")}>
        <header><h2>{room ? `# ${room.name}` : tx("Choose a room", "选择房间")}</h2><span role="status" className={`web-room-connection is-${connection}`}>{tx(connection, ({disconnected:"未连接", connecting:"连接中", connected:"实时连接", reconnecting:"重新连接中", unavailable:"访问或连接不可用"} as Record<string,string>)[connection] ?? connection)}</span></header>
        <p className="web-room-history-note">{tx("Latest 64 messages. Edits and deletions stay synchronized; reconnect replaces this bounded view.", "显示最近 64 条消息；编辑与删除同步更新，重新连接会重建此范围内的视图。")}</p>
        <div className="web-room-messages" role="log" aria-live="polite" aria-relevant="additions text" aria-label={tx("Messages", "消息")} onScroll={event => {const node = event.currentTarget; nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 100;}}>
          {!snapshot.messages.length && <p className="web-room-empty">{connection === "connected" ? tx("No recent messages.", "尚无最近消息。") : tx("Messages are shown after current room access is confirmed.", "确认当前房间访问权后显示消息。")}</p>}
          {snapshot.messages.map(message => <article className="web-room-message" key={message.id} data-message-id={message.id}><Avatar url={message.avatar_url} name={message.display_name}/><div><header><strong>{message.display_name || tx("Deleted source", "已删除来源")}</strong><small>{message.actor_type.replaceAll("_", " ")} · {time(message.created_at)}{message.edited_at ? tx(" · edited", " · 已编辑") : ""}</small></header>
            {message.reply_to_message_id && <small>{tx("Reply to", "回复")} {snapshot.messages.find(item => item.id === message.reply_to_message_id)?.display_name ?? message.reply_to_message_id}</small>}
            <p className="room-preserve-text">{message.deleted ? tx("Message deleted", "消息已删除") : !message.content_available ? tx("Message content unavailable", "消息内容不可用") : message.text}</p>
            {!message.deleted && message.content_available && room?.can_post && <button type="button" className="web-room-reply" disabled={Boolean(retry)} onClick={() => setReply(message.id)}>{tx("Reply", "回复")}</button>}
          </div></article>)}
          {unmatchedOutbox(snapshot).map(item => <article className="web-room-message web-room-pending" key={`pending:${item.id}`}><Avatar url={item.avatar_url} name={item.display_name}/><div><header><strong>{item.display_name}</strong><small>{item.status} · {time(item.created_at)}</small></header><p className="room-preserve-text">{item.text}</p>{item.reason && <small>{item.reason}</small>}{item.status === "uncertain" && <p>{tx("Discord may have received this message. It will not be resent automatically.", "Discord 可能已收到此消息；系统不会自动重发。")}</p>}</div></article>)}<div ref={end}/>
        </div>
        <form className="web-room-composer" onSubmit={submit}>
          {reply && <div className="web-room-reply-preview">{tx("Replying to", "正在回复")} {snapshot.messages.find(item => item.id === reply)?.display_name ?? reply}<button type="button" disabled={Boolean(retry)} onClick={() => setReply("")}>{tx("Cancel reply", "取消回复")}</button></div>}
          <label>{tx("Message", "消息")}<textarea value={text} maxLength={1800} rows={3} disabled={busy || Boolean(retry) || demoMode || !room?.can_post} onChange={event => setText(event.target.value)} placeholder={tx("Write a message. Name a Character explicitly to ask it to reply.", "输入消息。明确叫出角色名称可请求回复。")}/></label>
          <footer><small>{text.length}/1800 · {tx("Mentions never ping everyone or roles.", "提及不会触发全体或身份组通知。")}</small><button className="paper-button" disabled={busy || Boolean(retry) || demoMode || !room?.can_post || !profile || !text.trim() || connection !== "connected"}>{tx("Send", "发送")}</button></footer>
          {retry && <div role="status"><p>{tx("Submission is not yet confirmed. Retrying uses the same message ID and will not create a second send.", "尚未确认提交结果。重试使用同一消息 ID，不会创建第二次发送。")}</p><button type="button" className="paper-button" disabled={busy || demoMode} onClick={() => void dispatch(retry)}>{tx("Check / retry safely", "安全核对／重试")}</button><button type="button" disabled={busy} onClick={() => {if (window.confirm(tx("This message may already have been accepted. Clear the editor without resending? Its server receipt will remain visible.", "此消息可能已经被接受。清空编辑框但不重发？服务器回执仍会保留。"))) {setRetry(null); setText(""); setReply("");}}}>{tx("Clear editor without resending", "清空编辑框，不重发")}</button></div>}
        </form>
      </section>
    </div>
    {room?.can_manage && <details className="web-room-management" onToggle={event => {if (event.currentTarget.open) void webRoomApi.members(room.id).then(setMembers).catch(report);}}><summary>{tx("Room access and pause", "房间授权与暂停")}</summary>
      <p>{tx("Accounts must first join this Discord server workspace. Grant only the specific people allowed to read this channel or private Thread.", "账号需要先加入此 Discord 服务器工作区。仅授权有权查看该频道或私密 Thread 的参与者。")}</p>
      <button type="button" className="paper-button" disabled={busy || demoMode} onClick={() => void action(async () => {await webRoomApi.configure(room.id, !room.enabled); await refresh();})}>{room.enabled ? tx("Pause web room", "暂停网页房间") : tx("Resume web room", "恢复网页房间")}</button>
      <form className="room-controls" onSubmit={event => {event.preventDefault(); void action(async () => {await webRoomApi.grant(room.id, memberId.trim(), canPost); setMembers(await webRoomApi.members(room.id)); setMemberId("");});}}>
        <label>{tx("Account user ID", "账号 User ID")}<input required value={memberId} maxLength={120} onChange={event => setMemberId(event.target.value)}/></label><label><input type="checkbox" checked={canPost} onChange={event => setCanPost(event.target.checked)}/>{tx("Allow sending", "允许发送")}</label><button className="paper-button" disabled={busy || demoMode}>{tx("Grant / update", "授权／更新")}</button>
      </form><ul>{members.map(item => <li key={item.user_id}><span>{item.display_name || item.user_id} — {item.can_post ? tx("read + send", "查看＋发送") : tx("read only", "仅查看")}</span> <button type="button" disabled={busy || demoMode} onClick={() => {if (window.confirm(tx("Revoke this account's access to this web room?", "撤销此账号对该网页房间的访问权？"))) void action(async () => {await webRoomApi.revoke(room.id, item.user_id); setMembers(await webRoomApi.members(room.id));});}}>{tx("Revoke", "撤销")}</button></li>)}</ul>
    </details>}
  </main>;
}
