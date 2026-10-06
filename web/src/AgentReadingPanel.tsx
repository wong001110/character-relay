import type { WebRoomSession, WebRoomSessionState } from "./webRoomSession";
import "./agent-reading.css";

type Translate = (english: string, chinese: string) => string;

/** Session-only visible reminders for low-frequency HTML checks. */
export function AgentReadingPanel({state, session, tx}: {
  state: WebRoomSessionState; session: WebRoomSession; tx: Translate;
}) {
  const enabled = Boolean(state.agentReading?.enabled);
  const count = state.agentReading?.pendingCount ?? 0;
  const connected = state.connection === "connected";
  const mode = !enabled ? "disabled" : !connected ? "disconnected" : count ? "pending" : "idle";
  const allowed = state.authenticated && !state.demoMode && Boolean(state.profileId && state.rooms.find(room => room.id === state.roomId)?.enabled);
  const roomName = state.rooms.find(room => room.id === state.roomId)?.name || state.roomId;
  const profileName = state.profiles.find(profile => profile.id === state.profileId)?.display_name || state.profileId;
  return <section className="agent-reading-panel" data-agent-reading="true" data-status={mode}
    data-room-id={state.roomId} data-profile-id={state.profileId} data-pending-count={count}
    data-connection={state.connection} data-companion-reader-ignore="true">
    <div className="agent-reading-controls">
      <strong>{tx("Agent reading", "Agent 阅读")}</strong>
      <button type="button" className="paper-button" disabled={!enabled && !allowed} aria-pressed={enabled}
        data-agent-toggle="true" onClick={() => session.setAgentReading(!enabled)}>
        {enabled ? tx("Disable Agent reading", "关闭 Agent 阅读") : tx("Enable Agent reading", "开启 Agent 阅读")}
      </button>
    </div>
    {enabled && <>
      <div data-agent-summary="true">
        <p role="status" data-agent-status="true">{!connected
          ? tx("Not connected · incoming messages may be missed", "未连接 · 可能漏掉新消息")
          : count ? tx("New messages to check", "有新消息待查看") : tx("No new messages counted", "暂无已计入的新消息")}</p>
        <p className="agent-reading-meta">{tx("Room", "房间")}: {roomName} ({state.roomId}) · {tx("Participant", "参与者")}: {profileName} ({state.profileId})</p>
        <p className="agent-reading-meta">{tx("New messages this session", "本次会话新消息")}: {count} · {tx("Connection", "连接状态")}: {state.connection}</p>
      </div>
      <button type="button" className="paper-button" data-agent-clear="true" disabled={!allowed}
        onClick={() => session.clearAgentReminders()}>{tx("Done · clear reminders", "已处理，清空提醒")}</button>
      <p className="agent-reading-scope">{tx("Counts messages received since joining. Refreshing or rejoining starts at zero; messages missed while disconnected are not guaranteed to be counted. Check at low frequency, for example every 60 seconds.", "只计入加入后收到的消息。刷新或重新加入从 0 开始；断线期间漏掉的消息不保证计入。建议低频检查，例如每 60 秒。")}</p>
    </>}
  </section>;
}
