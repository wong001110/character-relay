import { CompactMessage } from "./WebRoomCompactMessage";
import type { WebRoomSession, WebRoomSessionState } from "./webRoomSession";
import "./agent-reading.css";

type Translate = (english: string, chinese: string) => string;

/** Ordinary readable HTML: no tool invocation, focus acknowledgement or extra stream. */
export function AgentReadingPanel({state, session, tx}: {
  state: WebRoomSessionState; session: WebRoomSession; tx: Translate;
}) {
  const reading = state.agentReading;
  const enabled = Boolean(reading?.enabled);
  const status = reading?.status;
  const unknown = !status || reading?.localGap || state.connection !== "connected" || Boolean(reading?.error);
  const laterGap = Boolean(status?.needs_reread && status.batch && status.gap_generation > status.batch.gap_generation);
  const mode = !enabled ? "disabled" : unknown ? "unknown" : laterGap ? "needs_reread" : status?.batch ? "processing" : status?.needs_reread ? "needs_reread" : status?.pending_count ? "pending" : "idle";
  const labels: Record<string, string> = {
    disabled: tx("Agent reading is off", "Agent 阅读已关闭"),
    unknown: tx("Status unknown · reread required", "状态未知 · 需要补读"),
    needs_reread: tx("Reread required", "需要补读"),
    processing: tx("Batch in progress", "本轮处理中"),
    pending: tx("New changes to process", "有新变化待处理"),
    idle: tx("No pending changes", "暂无待处理变化")
  };
  const allowed = state.authenticated && !state.demoMode && Boolean(state.roomId && state.profileId && state.rooms.find(room => room.id === state.roomId)?.enabled);
  const blocked = !allowed || unknown || Boolean(reading?.busy);
  const roomName = state.rooms.find(room => room.id === state.roomId)?.name || state.roomId;
  const profileName = state.profiles.find(profile => profile.id === state.profileId)?.display_name || state.profileId;
  const batch = status?.batch;
  return <section className="agent-reading-panel" aria-label={tx("Agent reading", "Agent 阅读")} data-agent-reading="true"
    data-status={mode} data-room-id={state.roomId} data-profile-id={state.profileId}
    data-observed-revision={!unknown && status ? status.observed_revision : "unknown"}
    data-pending-count={!unknown && status ? status.pending_count : "unknown"}
    data-needs-reread={Boolean(unknown || status?.needs_reread)} data-companion-reader-ignore="true">
    <div className="agent-reading-controls">
      <strong>{tx("Agent reading", "Agent 阅读")}</strong>
      <button type="button" className="paper-button" disabled={!enabled && !allowed} aria-pressed={enabled} data-agent-toggle="true" onClick={() => session.setAgentReading(!enabled)}>
        {enabled ? tx("Disable Agent reading", "关闭 Agent 阅读") : tx("Enable Agent reading", "开启 Agent 阅读")}
      </button>
    </div>
    {enabled && <>
      <div data-agent-summary="true">
      <p role="status" data-agent-status="true">{labels[mode]}</p>
      <p className="agent-reading-meta">{tx("Room", "房间")}: {roomName} ({state.roomId}) · {tx("Participant", "参与者")}: {profileName} ({state.profileId})</p>
      <p className="agent-reading-meta">{tx("Observed revision", "已观察版本")}: {unknown ? tx("unknown", "未知") : status?.observed_revision} · {tx("Pending changes", "待处理变化")}: {unknown ? tx("unknown", "未知") : status?.pending_count} · {tx("Completed through revision", "已处理至版本")}: {status?.cursor_revision ?? tx("unknown", "未知")}</p>
      </div>
      <p className="agent-reading-scope">{tx("Recorded current state only; not a complete history or edit replay. Missing updates require an explicit reread. Check this status at low frequency (for example every 60 seconds).", "仅包含已采集的当前状态，不是完整历史或编辑回放。可能漏读时需要明确补读。建议低频检查此状态（例如每 60 秒）。")}</p>
      {status?.needs_reread && <p>{tx("A recovery reread is still required, even if there are no pending changes.", "即使没有待处理变化，仍需补读并确认。")}</p>}
      {reading?.error && <p role="alert">{tx("Reading state unavailable. Retry status before processing.", "读取状态不可用，请先重试状态。")}</p>}
      <div className="agent-reading-controls">
        {unknown && <button type="button" className="paper-button" data-agent-retry="true" disabled={!allowed || Boolean(reading?.busy)} onClick={() => session.refreshAgentReading()}>{tx("Retry status", "重试状态")}</button>}
        <button type="button" className="paper-button" data-agent-read="true" disabled={blocked || Boolean(batch)} onClick={() => void session.readAgentBatch()}>{tx("Read batch", "读取本轮")}</button>
        <button type="button" className="paper-button" data-agent-complete="true" disabled={blocked || !batch} onClick={() => void session.completeAgentBatch()}>{tx("Complete this batch", "确认本轮处理完成")}</button>
      </div>
      {batch && <section className="agent-reading-batch" aria-label={tx("Captured reading batch", "已固定的阅读批次")}
        data-agent-batch-id={batch.id} data-from-revision={batch.from_revision} data-to-revision={batch.to_revision}>
        <p>{tx("Batch", "批次")}: {batch.id} · {tx("Fixed revision range", "固定版本范围")}: {batch.from_revision} → {batch.to_revision}</p>
        <p>{tx("Completion advances only through this batch. Changes arriving during processing remain for the next round.", "确认完成只推进至本轮末尾；处理中到来的变化保留到下一轮。")}</p>
        {batch.needs_reread && <p>{tx("This batch includes recovery context from recorded current state.", "本轮包含已采集当前状态的补读上下文。")}</p>}
        {!batch.items.length && <p>{tx("No recorded messages in this batch. Complete explicitly to confirm this reread.", "本轮没有已采集消息；请明确确认完成此次补读。")}</p>}
        {batch.items.map(item => <div key={`${item.message_id}:${item.room_revision}`} data-agent-item-id={item.message_id}
          data-source-revision={item.source_revision} data-room-revision={item.room_revision} data-change={item.change} data-item-state={item.state}>
          <p className="agent-reading-meta">{tx("Message", "消息")}: {item.message_id} · {tx("Change", "变化")}: {tx(item.change, ({new: "新增", edited: "编辑", deleted: "删除", unavailable: "不可用"})[item.change])} · {tx("Source revision", "来源版本")}: {item.source_revision} · {tx("Room revision", "房间版本")}: {item.room_revision}</p>
          {unknown || reading?.busy ? <p>{tx("Content withheld until fresh reading state is confirmed.", "待确认最新阅读状态后再显示内容。")}</p>
            : item.state === "current" && item.message ? <CompactMessage message={item.message} disabled={true} showReply={false} onReply={() => {}} tx={tx} />
            : <p>{item.state === "changed"
              ? tx("Message changed after this batch was captured. The new version remains for the next round.", "此消息在本轮固定后已变化，新版本保留到下一轮。")
              : item.state === "removed" || item.change === "deleted"
                ? tx("Message removed; its content is unavailable.", "消息已删除，内容不可用。")
                : tx("Message content unavailable.", "消息内容不可用。")}</p>}
        </div>)}
      </section>}
    </>}
  </section>;
}
