import { useEffect, useState } from "react";

import type { CharacterCard } from "./api";
import { PaperDrawer } from "./NotebookUI";
import {
  smartParticipationApi,
  type SemanticProfile,
  type SemanticProfileStatus
} from "./smartParticipationApi";

interface Props {
  card: CharacterCard;
  zh: boolean;
  demoMode?: boolean;
  onClose: () => void;
}

function statusCopy(status: SemanticProfileStatus, zh: boolean): { label: string; note: string } {
  const values: Record<SemanticProfileStatus, { en: string; zh: string; enNote: string; zhNote: string }> = {
    disabled: {
      en: "Unavailable",
      zh: "服务未启用",
      enNote: "Semantic embedding is disabled on this Character Relay deployment.",
      zhNote: "当前 Character Relay 环境没有启用 Semantic Embedding。"
    },
    not_created: {
      en: "Not created",
      zh: "尚未创建",
      enNote: "This Character Card exists without an embedding. That is valid until semantic participation is needed.",
      zhNote: "这张 Character Card 目前没有 Embedding；如果只用于创建、测试或整理角色卡，这是正常状态。"
    },
    ready: {
      en: "Ready",
      zh: "已就绪",
      enNote: "The stored vector matches the current Character Card semantic source and configured embedding model.",
      zhNote: "已保存的 Vector 与当前 Character Card 内容和 Embedding Model 一致。"
    },
    stale: {
      en: "Out of date",
      zh: "需要更新",
      enNote: "The Character Card or embedding configuration changed after this vector was created.",
      zhNote: "建立 Vector 后 Character Card 或 Embedding 配置发生了变化。"
    },
    invalid: {
      en: "Invalid",
      zh: "数据异常",
      enNote: "The stored vector metadata or byte length is invalid and should be rebuilt.",
      zhNote: "已保存 Vector 的 metadata 或 byte 长度异常，建议重新建立。"
    }
  };
  const item = values[status];
  return { label: zh ? item.zh : item.en, note: zh ? item.zhNote : item.enNote };
}

function formatDate(value: string | null, zh: boolean): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(zh ? "zh-CN" : "en-US");
}

export function SemanticProfilePanel({ card, zh, demoMode = false, onClose }: Props) {
  const [profile, setProfile] = useState<SemanticProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");

  async function load() {
    try {
      setLoading(true);
      setError(null);
      const value = await smartParticipationApi.getSemanticProfile(card.id);
      setProfile(value);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [card.id]);

  async function createOrRefresh() {
    try {
      setBuilding(true);
      setError(null);
      setNote("");
      const value = await smartParticipationApi.createSemanticProfile(card.id);
      setProfile(value);
      setNote(
        value.rebuilt
          ? zh
            ? "Semantic Profile 已建立并保存到 SQLite。"
            : "Semantic Profile was built and persisted to SQLite."
          : zh
            ? "现有 Semantic Profile 已经是最新版本，无需重新建立。"
            : "The existing Semantic Profile is already current; no rebuild was needed."
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBuilding(false);
    }
  }

  const status = profile ? statusCopy(profile.status, zh) : null;
  const actionNeeded = profile && ["not_created", "stale", "invalid"].includes(profile.status);

  return (
    <PaperDrawer
      onClose={onClose}
      ariaLabel={zh ? `${card.display_name} · Semantic Profile` : `${card.display_name} · Semantic Profile`}
      className="semantic-profile-drawer"
    >
      <div className="semantic-profile-panel">
        <header className="semantic-profile-header">
          <div>
            <p className="tape-label">SEMANTIC PROFILE</p>
            <h2>{card.display_name}</h2>
            <p>
              {zh
                ? "Embedding 是可选的。单纯创建 Character Card 不需要先建立 Vector；只有你主动建立，或未来 Smart semantic runtime 真正需要它时才会生成。"
                : "Embedding is optional. Creating a Character Card alone does not require a vector; it is generated only when you create it here or when Smart semantic runtime actually needs it."}
            </p>
          </div>
        </header>

        {error && <p className="error-note" role="alert">{error}</p>}
        {note && <p className="success-note">{note}</p>}

        {loading ? (
          <p className="semantic-profile-loading">{zh ? "检查中…" : "Checking…"}</p>
        ) : profile && status ? (
          <>
            <section className={`semantic-profile-status is-${profile.status}`}>
              <div>
                <span>{zh ? "状态" : "Status"}</span>
                <strong>{status.label}</strong>
              </div>
              <p>{status.note}</p>
            </section>

            <section className="semantic-profile-metadata paper-sheet">
              <div>
                <span>{zh ? "Embedding Model" : "Embedding model"}</span>
                <strong>{profile.model_name || "—"}</strong>
              </div>
              <div>
                <span>{zh ? "维度" : "Dimension"}</span>
                <strong>{profile.dimension || "—"}</strong>
              </div>
              <div>
                <span>Vector bytes</span>
                <strong>{profile.embedding_bytes || 0}</strong>
              </div>
              <div>
                <span>{zh ? "建立时间" : "Created"}</span>
                <strong>{formatDate(profile.created_at, zh)}</strong>
              </div>
              <div>
                <span>{zh ? "更新时间" : "Updated"}</span>
                <strong>{formatDate(profile.updated_at, zh)}</strong>
              </div>
              <div>
                <span>Source hash</span>
                <strong title={profile.source_hash}>{profile.source_hash ? profile.source_hash.slice(0, 16) : "—"}</strong>
              </div>
            </section>

            <section className="semantic-profile-source">
              <div className="smart-section-heading">
                <div>
                  <span>SEMANTIC SOURCE</span>
                  <strong>{zh ? "实际用于角色语义的内容" : "Character content used for semantic relevance"}</strong>
                </div>
              </div>
              <p>
                {zh
                  ? "这里只显示用于 Participation semantic profile 的角色身份信息；Memory 与 forbidden behavior 不会进入这份 embedding。"
                  : "This is the identity content used by the participation semantic profile. Memory and forbidden behavior are excluded from this embedding."}
              </p>
              <pre>{profile.semantic_text || "—"}</pre>
            </section>

            {!demoMode && actionNeeded && profile.enabled && (
              <div className="semantic-profile-actions">
                <button
                  className="ink-button"
                  type="button"
                  disabled={building}
                  onClick={() => void createOrRefresh()}
                >
                  {building
                    ? zh
                      ? "建立中…"
                      : "Building…"
                    : profile.status === "not_created"
                      ? zh
                        ? "建立 Semantic Profile"
                        : "Create Semantic Profile"
                      : zh
                        ? "更新 Embedding"
                        : "Refresh Embedding"}
                </button>
                <small>
                  {zh
                    ? "操作只会建立这张 Character Card 的语义 Vector，不需要先 Deployment。"
                    : "This creates only the semantic vector for this Character Card; deployment is not required."}
                </small>
              </div>
            )}

            {demoMode && actionNeeded && (
              <p className="semantic-profile-readonly">
                {zh ? "Public Demo 为只读模式，无法建立或更新 Embedding。" : "Public Demo is read-only, so embeddings cannot be created or refreshed."}
              </p>
            )}
          </>
        ) : null}
      </div>
    </PaperDrawer>
  );
}
