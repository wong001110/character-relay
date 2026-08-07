import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CharacterCard } from "./api";
import {
  smartParticipationApi,
  type SmartParticipationFeedbackLabel,
  type SmartParticipationGroupRole,
  type SmartParticipationPreview,
  type SmartParticipationProfile,
  type SmartParticipationProfileUpdate,
  type SmartParticipationStyle
} from "./smartParticipationApi";

interface Props {
  cards: CharacterCard[];
  zh: boolean;
  onBack: () => void;
}

function listText(values: string[]): string {
  return values.join("\n");
}

function parseList(value: string): string[] {
  return [...new Set(value.split(/\r?\n|,/u).map((item) => item.trim()).filter(Boolean))];
}

function styleDescription(style: SmartParticipationStyle, zh: boolean): string {
  const values = {
    quiet: {
      en: "Conservative. Needs stronger relevance and waits longer before speaking again.",
      zh: "保守。需要更强的相关信号，并在再次主动发言前等待更久。"
    },
    balanced: {
      en: "Default balance between relevance and initiative.",
      zh: "在相关性与主动性之间采用默认平衡。"
    },
    active: {
      en: "More willing to join relevant conversation while still respecting hard boundaries.",
      zh: "更愿意加入相关对话，但仍遵守硬性边界。"
    }
  } as const;
  return zh ? values[style].zh : values[style].en;
}

function reasonLabel(reason: string, zh: boolean): string {
  const labels: Record<string, { en: string; zh: string }> = {
    selected: { en: "Relevant signals reached the participation threshold.", zh: "相关信号达到参与门槛。" },
    below_threshold: { en: "The message did not contain enough participation signals.", zh: "当前消息的参与信号不足。" },
    avoid_phrase: { en: "A stay-quiet boundary matched.", zh: "命中了保持安静的边界。" },
    low_information_message: { en: "Low-information acknowledgement.", zh: "低信息量确认消息。" },
    profile_disabled: { en: "Smart Participation is disabled for this character.", zh: "该角色已关闭 Smart Participation。" },
    empty_message: { en: "No readable message was supplied.", zh: "没有可读取的消息。" }
  };
  const item = labels[reason];
  return item ? (zh ? item.zh : item.en) : reason.replaceAll("_", " ");
}

function emptyUpdate(profile: SmartParticipationProfile): SmartParticipationProfileUpdate {
  return {
    enabled: profile.enabled,
    style: profile.style,
    group_role: profile.group_role,
    topics: profile.topics,
    keywords: profile.keywords,
    trigger_phrases: profile.trigger_phrases,
    avoid_phrases: profile.avoid_phrases,
    cooldown_seconds: profile.cooldown_seconds,
    preferred_follow_up_character_card_id: profile.preferred_follow_up_character_card_id,
    follow_up_window_seconds: profile.follow_up_window_seconds
  };
}

export function SmartParticipationStudio({ cards, zh, onBack }: Props) {
  const [characterId, setCharacterId] = useState(cards[0]?.id ?? "");
  const [profile, setProfile] = useState<SmartParticipationProfile | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [style, setStyle] = useState<SmartParticipationStyle>("balanced");
  const [groupRole, setGroupRole] = useState<SmartParticipationGroupRole>("independent");
  const [topics, setTopics] = useState("");
  const [keywords, setKeywords] = useState("");
  const [triggers, setTriggers] = useState("");
  const [avoids, setAvoids] = useState("");
  const [cooldownSeconds, setCooldownSeconds] = useState(120);
  const [preferredFollowUpId, setPreferredFollowUpId] = useState("");
  const [followUpWindowSeconds, setFollowUpWindowSeconds] = useState(30);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState("");

  const [playgroundMessage, setPlaygroundMessage] = useState("");
  const [previousCharacterId, setPreviousCharacterId] = useState("");
  const [preview, setPreview] = useState<SmartParticipationPreview | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [feedbackNote, setFeedbackNote] = useState("");

  const selectedCard = useMemo(
    () => cards.find((card) => card.id === characterId) ?? null,
    [cards, characterId]
  );
  const followUpOptions = cards.filter((card) => card.id !== characterId);

  function applyProfile(value: SmartParticipationProfile) {
    setProfile(value);
    setEnabled(value.enabled);
    setStyle(value.style);
    setGroupRole(value.group_role);
    setTopics(listText(value.topics));
    setKeywords(listText(value.keywords));
    setTriggers(listText(value.trigger_phrases));
    setAvoids(listText(value.avoid_phrases));
    setCooldownSeconds(value.cooldown_seconds);
    setPreferredFollowUpId(value.preferred_follow_up_character_card_id);
    setFollowUpWindowSeconds(value.follow_up_window_seconds);
  }

  useEffect(() => {
    if (!characterId) return;
    let active = true;
    setLoading(true);
    setPreview(null);
    setSavedNote("");
    setFeedbackNote("");
    smartParticipationApi
      .getProfile(characterId)
      .then((value) => {
        if (active) applyProfile(value);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [characterId]);

  useEffect(() => {
    if (preferredFollowUpId === characterId) setPreferredFollowUpId("");
  }, [characterId, preferredFollowUpId]);

  function profilePayload(): SmartParticipationProfileUpdate {
    return {
      enabled,
      style,
      group_role: groupRole,
      topics: parseList(topics),
      keywords: parseList(keywords),
      trigger_phrases: parseList(triggers),
      avoid_phrases: parseList(avoids),
      cooldown_seconds: cooldownSeconds,
      preferred_follow_up_character_card_id:
        groupRole === "secondary" ? preferredFollowUpId : "",
      follow_up_window_seconds: followUpWindowSeconds
    };
  }

  async function saveProfile(event?: FormEvent) {
    event?.preventDefault();
    if (!characterId) return;
    try {
      setSaving(true);
      setError(null);
      const saved = await smartParticipationApi.updateProfile(characterId, profilePayload());
      applyProfile(saved);
      setSavedNote(zh ? "Participation Profile 已保存。Connector 会在下次同步时取得新配置。" : "Participation Profile saved. The Connector will pick it up on its next refresh.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function evaluate() {
    if (!characterId || !playgroundMessage.trim()) return;
    try {
      setEvaluating(true);
      setError(null);
      setFeedbackNote("");
      // Evaluate the persisted contract so Playground and Discord use the same saved profile.
      if (!profile?.configured || JSON.stringify(emptyUpdate(profile)) !== JSON.stringify(profilePayload())) {
        await saveProfile();
      }
      const result = await smartParticipationApi.evaluate(
        characterId,
        playgroundMessage.trim(),
        previousCharacterId
      );
      setPreview(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setEvaluating(false);
    }
  }

  async function recordFeedback(label: SmartParticipationFeedbackLabel) {
    if (!preview || !characterId || !playgroundMessage.trim()) return;
    try {
      setError(null);
      await smartParticipationApi.recordFeedback(characterId, {
        message: playgroundMessage.trim(),
        previous_character_card_id: previousCharacterId,
        predicted_decision: preview.decision,
        predicted_reason: preview.reason,
        score: preview.score,
        minimum_score: preview.minimum_score,
        signals: preview.signals,
        feedback_label: label
      });
      setFeedbackNote(
        zh
          ? "已保存为未来 Participation Judge 的评估样本。"
          : "Saved as an evaluation example for a future Participation Judge."
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  if (!cards.length) {
    return (
      <section className="smart-participation-studio">
        <button className="text-button" type="button" onClick={onBack}>
          ← {zh ? "返回" : "Back"}
        </button>
        <p>{zh ? "请先建立 Character Card。" : "Create a Character Card first."}</p>
      </section>
    );
  }

  return (
    <section className="smart-participation-studio">
      <header className="smart-participation-header">
        <div>
          <p className="tape-label">SMART PARTICIPATION</p>
          <h2>{zh ? "角色参与规则与 Playground" : "Participation profile & Playground"}</h2>
          <p>
            {zh
              ? "这里调整角色何时主动加入群聊。运行时仍使用 deterministic gate，不增加 LLM Judge 或 Vector DB。"
              : "Tune when a character proactively joins group chat. Runtime remains deterministic with no LLM Judge or Vector DB."}
          </p>
        </div>
        <button className="paper-button" type="button" onClick={onBack}>
          {zh ? "返回工具箱" : "Back to tools"}
        </button>
      </header>

      {error && <p className="error-note">{error}</p>}

      <div className="smart-participation-grid">
        <form className="smart-profile-panel paper-sheet" onSubmit={saveProfile}>
          <div className="smart-section-heading">
            <div>
              <span>{zh ? "角色设置" : "Character profile"}</span>
              <strong>{selectedCard?.display_name ?? "—"}</strong>
            </div>
            {profile && (
              <small>{profile.configured ? (zh ? "已保存" : "Saved") : zh ? "使用默认值" : "Defaults"}</small>
            )}
          </div>

          <label>
            {zh ? "角色" : "Character"}
            <select value={characterId} onChange={(event) => setCharacterId(event.currentTarget.value)}>
              {cards.map((card) => (
                <option key={card.id} value={card.id}>{card.display_name}</option>
              ))}
            </select>
          </label>

          <label className="smart-toggle-row">
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.currentTarget.checked)} />
            <span>
              <strong>{zh ? "启用 Smart Participation" : "Enable Smart Participation profile"}</strong>
              <small>{zh ? "Deployment 仍需选择 Smart participation 才会主动加入。" : "The deployment must still use Smart participation for proactive turns."}</small>
            </span>
          </label>

          <fieldset className="smart-preset-fieldset">
            <legend>{zh ? "主动程度" : "Participation style"}</legend>
            <div className="smart-preset-row">
              {(["quiet", "balanced", "active"] as SmartParticipationStyle[]).map((item) => (
                <button
                  type="button"
                  key={item}
                  className={style === item ? "smart-preset is-active" : "smart-preset"}
                  onClick={() => setStyle(item)}
                >
                  <strong>{item === "quiet" ? (zh ? "安静" : "Quiet") : item === "balanced" ? (zh ? "平衡" : "Balanced") : zh ? "活跃" : "Active"}</strong>
                </button>
              ))}
            </div>
            <small>{styleDescription(style, zh)}</small>
          </fieldset>

          <label>
            {zh ? "群聊角色" : "Group role"}
            <select value={groupRole} onChange={(event) => setGroupRole(event.currentTarget.value as SmartParticipationGroupRole)}>
              <option value="independent">{zh ? "Independent · 独立参与" : "Independent"}</option>
              <option value="primary">{zh ? "Primary · 主位" : "Primary"}</option>
              <option value="secondary">{zh ? "Secondary · 跟进 / 补位" : "Secondary / follow-up"}</option>
            </select>
          </label>

          {groupRole === "secondary" && (
            <div className="smart-follow-up-fields">
              <label>
                {zh ? "优先跟进角色" : "Preferred primary"}
                <select value={preferredFollowUpId} onChange={(event) => setPreferredFollowUpId(event.currentTarget.value)}>
                  <option value="">{zh ? "不指定" : "None"}</option>
                  {followUpOptions.map((card) => (
                    <option key={card.id} value={card.id}>{card.display_name}</option>
                  ))}
                </select>
              </label>
              <label>
                {zh ? "跟进窗口" : "Follow-up window"}
                <select value={followUpWindowSeconds} onChange={(event) => setFollowUpWindowSeconds(Number(event.currentTarget.value))}>
                  <option value={15}>15s</option>
                  <option value={30}>30s</option>
                  <option value={60}>60s</option>
                  <option value={120}>120s</option>
                </select>
              </label>
            </div>
          )}

          <label>
            {zh ? "主动回复冷却" : "Proactive cooldown"}
            <select value={cooldownSeconds} onChange={(event) => setCooldownSeconds(Number(event.currentTarget.value))}>
              <option value={30}>30s</option>
              <option value={60}>1 min</option>
              <option value={120}>2 min</option>
              <option value={180}>3 min</option>
              <option value={300}>5 min</option>
            </select>
          </label>

          <div className="smart-list-grid">
            <label>
              {zh ? "通常加入的话题" : "Usually joins for"}
              <textarea rows={4} value={topics} onChange={(event) => setTopics(event.currentTarget.value)} placeholder={zh ? "嘴硬\n吹嘘\n逻辑漏洞" : "banter\nboasting\nabsurd claims"} />
            </label>
            <label>
              {zh ? "关键词" : "Keywords"}
              <textarea rows={4} value={keywords} onChange={(event) => setKeywords(event.currentTarget.value)} placeholder={zh ? "尴尬\n离谱\n硬撑" : "awkward\nabsurd"} />
            </label>
            <label>
              {zh ? "明显邀请 / Trigger" : "Trigger phrases"}
              <textarea rows={4} value={triggers} onChange={(event) => setTriggers(event.currentTarget.value)} placeholder={zh ? "你认真的\n真的假的\n不会吧" : "are you serious\nreally"} />
            </label>
            <label>
              {zh ? "必须保持安静" : "Stay quiet when"}
              <textarea rows={4} value={avoids} onChange={(event) => setAvoids(event.currentTarget.value)} placeholder={zh ? "不要继续\n不舒服\n认真求助" : "stop\nserious help\ndistress"} />
            </label>
          </div>

          <button className="ink-button" disabled={saving || loading}>
            {saving ? (zh ? "保存中…" : "Saving…") : zh ? "保存 Participation Profile" : "Save Participation Profile"}
          </button>
          {savedNote && <p className="success-note">{savedNote}</p>}
        </form>

        <section className="smart-playground-panel paper-sheet">
          <div className="smart-section-heading">
            <div>
              <span>PLAYGROUND</span>
              <strong>{zh ? "先解释规则，再去 Discord 实测" : "Explain first, then test in Discord"}</strong>
            </div>
          </div>
          <label>
            {zh ? "测试消息" : "Test message"}
            <textarea
              rows={5}
              value={playgroundMessage}
              onChange={(event) => {
                setPlaygroundMessage(event.currentTarget.value);
                setPreview(null);
                setFeedbackNote("");
              }}
              placeholder={zh ? "例如：等等，这个逻辑漏洞也太明显了吧，你认真的？" : "e.g. Wait, that logic gap is obvious. Are you serious?"}
            />
          </label>
          <label>
            {zh ? "上一位角色（可选）" : "Previous character (optional)"}
            <select value={previousCharacterId} onChange={(event) => setPreviousCharacterId(event.currentTarget.value)}>
              <option value="">{zh ? "没有 / 测普通 Smart" : "None / ordinary Smart"}</option>
              {followUpOptions.map((card) => (
                <option key={card.id} value={card.id}>{card.display_name}</option>
              ))}
            </select>
            <small>{zh ? "用于检查 Primary → Secondary follow-up 关系。" : "Used to inspect Primary → Secondary follow-up eligibility."}</small>
          </label>
          <button className="ink-button" type="button" disabled={evaluating || !playgroundMessage.trim()} onClick={() => void evaluate()}>
            {evaluating ? (zh ? "评估中…" : "Evaluating…") : zh ? "Evaluate" : "Evaluate"}
          </button>

          {preview && (
            <div className={`smart-preview ${preview.decision === "participate" ? "is-participate" : "is-silent"}`}>
              <div className="smart-preview-head">
                <div>
                  <span>{zh ? "判断" : "Decision"}</span>
                  <strong>{preview.decision === "participate" ? (zh ? "✓ 会参与" : "✓ Participate") : zh ? "○ 保持安静" : "○ Stay silent"}</strong>
                </div>
                <div className="smart-score">
                  <span>{zh ? "分数" : "Score"}</span>
                  <strong>{preview.score.toFixed(2)} / {preview.minimum_score.toFixed(2)}</strong>
                </div>
              </div>
              <p>{reasonLabel(preview.reason, zh)}</p>

              <div className="smart-signal-list">
                {Object.entries(preview.signals)
                  .filter(([, value]) => value !== 0)
                  .map(([key, value]) => (
                    <div key={key}>
                      <span>{key.replaceAll("_", " ")}</span>
                      <strong>{value > 0 ? `+${value}` : value}</strong>
                    </div>
                  ))}
              </div>

              <div className="smart-match-grid">
                <div><span>Topics</span><strong>{preview.matched_topics.join(" · ") || "—"}</strong></div>
                <div><span>Keywords</span><strong>{preview.matched_keywords.join(" · ") || "—"}</strong></div>
                <div><span>Triggers</span><strong>{preview.matched_trigger_phrases.join(" · ") || "—"}</strong></div>
                <div><span>Avoid</span><strong>{preview.matched_avoid_phrases.join(" · ") || "—"}</strong></div>
              </div>

              {previousCharacterId && (
                <div className={preview.follow_up_eligible ? "smart-follow-up-result is-ready" : "smart-follow-up-result"}>
                  <span>Primary → Secondary</span>
                  <strong>
                    {preview.follow_up_eligible
                      ? zh ? "✓ 可作为 Follow-up" : "✓ Follow-up eligible"
                      : zh ? "○ 不符合 Follow-up 关系" : "○ No follow-up relation"}
                  </strong>
                  <small>{preview.follow_up_reason.replaceAll("_", " ")}</small>
                </div>
              )}

              <div className="smart-feedback-row">
                <span>{zh ? "这次判断对吗？" : "Was this decision right?"}</span>
                <button type="button" onClick={() => void recordFeedback("correct")}>{zh ? "正确" : "Correct"}</button>
                <button type="button" onClick={() => void recordFeedback("should_speak")}>{zh ? "应该说话" : "Should speak"}</button>
                <button type="button" onClick={() => void recordFeedback("should_stay_silent")}>{zh ? "应该安静" : "Should stay silent"}</button>
              </div>
              {feedbackNote && <p className="success-note">{feedbackNote}</p>}
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
