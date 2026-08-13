interface ParticipationCandidateObservation {
  deployment_id: string;
  character_name: string;
  score: number | null;
  minimum_score: number;
  eligible: boolean;
  semantic_relevance: number | null;
  signals: Record<string, number>;
  matched_topics: string[];
  matched_keywords: string[];
  matched_trigger_phrases: string[];
  matched_avoid_phrases: string[];
}

interface ParticipationObservation {
  source: "smart" | "explicit" | "lightweight";
  reason: string;
  selected_deployment_ids: string[];
  candidates: ParticipationCandidateObservation[];
  minimum_margin: number | null;
}

function record(metadata: Array<[string, string]>): Record<string, string> {
  return Object.fromEntries(metadata);
}

function parseParticipation(value: string): ParticipationObservation | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as ParticipationObservation;
    if (!parsed || !Array.isArray(parsed.selected_deployment_ids)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function signalLabel(value: string, zh: boolean): string {
  const labels: Record<string, [string, string]> = {
    question: ["问题", "Question"],
    help_request: ["求助", "Help request"],
    name_match: ["名字命中", "Name match"],
    topic_match: ["Topic 命中", "Topic match"],
    keyword_match: ["关键词", "Keyword"],
    trigger_phrase: ["触发短语", "Trigger phrase"],
    semantic_match: ["语义相关", "Semantic match"],
    initiative: ["主动性", "Initiative"],
    short_message_penalty: ["短消息惩罚", "Short-message penalty"],
    recent_turn_match: ["近期发言连续性", "Recent-turn continuity"],
    lightweight_follow_up: ["轻量跟进", "Lightweight follow-up"],
    cooldown_blocked: ["Cooldown 阻挡", "Cooldown blocked"],
    avoid_phrase_blocked: ["Avoid phrase 阻挡", "Avoid phrase blocked"],
    profile_disabled_blocked: ["Profile 关闭", "Profile disabled"]
  };
  const label = labels[value];
  return label ? label[zh ? 0 : 1] : value.replaceAll("_", " ");
}

export function TurnContextObservationDetails({
  metadata,
  zh
}: {
  metadata: Array<[string, string]>;
  zh: boolean;
}) {
  const value = record(metadata);
  const participation = parseParticipation(value.participation_observation);
  return (
    <div className="runtime-epistemic-panel">
      <p>
        <strong>{zh ? "当前 Topic" : "Active topic"}</strong>
        {" · "}
        {value.topic_label || (zh ? "尚未形成 Topic" : "No active topic")}
      </p>
      <dl className="provider-trace-meta-grid">
        <div>
          <dt>Topic ID</dt>
          <dd>{value.topic_id ? value.topic_id.slice(0, 12) : "—"}</dd>
        </div>
        <div>
          <dt>{zh ? "状态" : "Status"}</dt>
          <dd>{value.topic_status || "—"}</dd>
        </div>
        <div>
          <dt>{zh ? "消息数" : "Messages"}</dt>
          <dd>{value.topic_message_count || "0"}</dd>
        </div>
        <div>
          <dt>{zh ? "连续性判断" : "Continuity"}</dt>
          <dd>{value.continuity_reason || "—"}</dd>
        </div>
      </dl>

      {value.recalled_media === "available" && (
        <p>
          <strong>{zh ? "媒体连续性：" : "Media continuity: "}</strong>
          {zh
            ? `已恢复之前跳过的媒体来源 · Message ${value.recalled_media_source_message_id || "—"}`
            : `Restored an earlier skipped media source · Message ${value.recalled_media_source_message_id || "—"}`}
        </p>
      )}

      {participation ? (
        <>
          <p>
            <strong>{zh ? "为什么轮到这个角色" : "Why this Character got the turn"}</strong>
            {" · "}
            {participation.source} / {participation.reason}
          </p>
          {participation.candidates.length > 0 ? (
            <div className="provider-trace-json-stack">
              {participation.candidates.map((candidate) => {
                const selected = participation.selected_deployment_ids.includes(
                  candidate.deployment_id
                );
                const signals = Object.entries(candidate.signals).filter(
                  ([, score]) => score !== 0
                );
                return (
                  <div className="provider-trace-json-card" key={candidate.deployment_id}>
                    <div className="provider-trace-badge-row">
                      <strong>{candidate.character_name || candidate.deployment_id}</strong>
                      <span
                        className={`provider-trace-status ${selected ? "trace-completed" : candidate.eligible ? "trace-running" : "trace-failed"}`}
                      >
                        {selected
                          ? zh
                            ? "本轮入选"
                            : "Selected"
                          : candidate.eligible
                            ? zh
                              ? "候选"
                              : "Candidate"
                            : zh
                              ? "被阻挡"
                              : "Blocked"}
                      </span>
                    </div>
                    <p>
                      {zh ? "总分" : "Score"}: {candidate.score ?? "—"}
                      {" / "}
                      {zh ? "门槛" : "threshold"} {candidate.minimum_score}
                      {candidate.semantic_relevance !== null &&
                        ` · semantic ${candidate.semantic_relevance.toFixed(3)}`}
                    </p>
                    {signals.length > 0 && (
                      <small>
                        {signals
                          .map(
                            ([name, score]) =>
                              `${signalLabel(name, zh)} ${score > 0 ? "+" : ""}${score}`
                          )
                          .join(" · ")}
                      </small>
                    )}
                    {candidate.matched_topics.length > 0 && (
                      <p>
                        <strong>{zh ? "命中 Topic：" : "Matched topics: "}</strong>
                        {candidate.matched_topics.join(" · ")}
                      </p>
                    )}
                    {candidate.matched_keywords.length > 0 && (
                      <p>
                        <strong>{zh ? "命中关键词：" : "Matched keywords: "}</strong>
                        {candidate.matched_keywords.join(" · ")}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p>
              {zh
                ? "这一轮是明确 Tag / Reply / 指定角色路由，因此没有伪造 Smart Participation 点数。"
                : "This turn used explicit Tag/Reply/Character routing, so no synthetic Smart Participation score is shown."}
            </p>
          )}
          {participation.minimum_margin !== null && participation.candidates.length > 1 && (
            <small>
              {zh ? "多角色入选最大分差" : "Multi-Character selection margin"}: {participation.minimum_margin}
            </small>
          )}
        </>
      ) : (
        <p>
          {zh
            ? "这条旧 Trace 没有 Speaker Selection Observation；新回合会显示实际候选评分。"
            : "This older trace has no Speaker Selection Observation. New turns will show the actual candidate scorecard."}
        </p>
      )}
    </div>
  );
}
