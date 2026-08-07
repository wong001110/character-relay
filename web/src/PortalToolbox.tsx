import { useState } from "react";

import { AccountPanel } from "./AccountPanel";
import { api, type AuthUser, type CharacterCard } from "./api";
import { useI18n } from "./i18n";
import { PaperModal } from "./NotebookUI";
import { ProviderTraceViewer } from "./ProviderTraceViewer";
import { SmartParticipationStudio } from "./SmartParticipationStudio";

type ToolboxSection = "actions" | "account" | "provider" | "participation";

interface Props {
  user: AuthUser;
  publicDemo: boolean;
  onDeployments: () => void;
  onWorkspace: () => void;
  onMatrix: () => void;
  onAdmin: () => void;
  onLogout: () => Promise<void>;
  onAccountDeleted: () => void;
}

export function PortalToolbox({
  user,
  publicDemo,
  onDeployments,
  onWorkspace,
  onMatrix,
  onAdmin,
  onLogout,
  onAccountDeleted
}: Props) {
  const { language } = useI18n();
  const zh = language === "zh-CN";
  const [open, setOpen] = useState(false);
  const [section, setSection] = useState<ToolboxSection>("actions");
  const [participationCards, setParticipationCards] = useState<CharacterCard[]>([]);
  const [participationLoading, setParticipationLoading] = useState(false);
  const [participationError, setParticipationError] = useState<string | null>(null);

  function run(action: () => void) {
    setOpen(false);
    window.setTimeout(action, 190);
  }

  async function openParticipation() {
    setSection("participation");
    setParticipationError(null);
    setParticipationLoading(true);
    try {
      setParticipationCards(await api.listCharacters());
    } catch (reason) {
      setParticipationError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setParticipationLoading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="portal-toolbox-fab"
        onClick={() => setOpen(true)}
        aria-label={zh ? "打开 Portal 工具箱" : "Open Portal toolbox"}
      >
        <img src="/assets/brand/character-relay-mark.png" alt="" />
        <span>{zh ? "工具箱" : "Tools"}</span>
      </button>

      {open && (
        <PaperModal
          ariaLabel={zh ? "Character Relay 工具箱" : "Character Relay toolbox"}
          onClose={() => setOpen(false)}
          className="portal-toolbox-modal"
        >
          {section !== "participation" && (
            <header className="portal-toolbox-header">
              <div>
                <p className="tape-label">CHARACTER RELAY / TOOLBOX</p>
                <h2>{zh ? "随手工具与账户" : "Tools and account"}</h2>
                <p>
                  {zh
                    ? "次要操作集中在这里，主页只保留创建角色。"
                    : "Secondary actions live here so the character shelf stays focused."}
                </p>
              </div>
            </header>
          )}

          {section !== "participation" && (
            <nav className="portal-toolbox-tabs" aria-label={zh ? "工具箱分区" : "Toolbox sections"}>
              <button
                type="button"
                className={section === "actions" ? "is-active" : ""}
                onClick={() => setSection("actions")}
              >
                {zh ? "快捷入口" : "Quick actions"}
              </button>
              {!publicDemo && (
                <button
                  type="button"
                  className={section === "account" ? "is-active" : ""}
                  onClick={() => setSection("account")}
                >
                  {zh ? "账户与安全" : "Account & security"}
                </button>
              )}
              {user.role === "admin" && !publicDemo && (
                <button
                  type="button"
                  className={section === "provider" ? "is-active" : ""}
                  onClick={() => setSection("provider")}
                >
                  Provider Trace
                </button>
              )}
            </nav>
          )}

          {section === "actions" && (
            <section className="portal-toolbox-actions">
              <button type="button" onClick={() => run(onDeployments)}>
                <span className="toolbox-sticker sticker-lavender">DEPLOY</span>
                <strong>{zh ? "部署中心" : "Deployment Center"}</strong>
                <small>
                  {zh
                    ? "管理 Discord Server、角色部署与互动场景。"
                    : "Manage Discord servers, deployments, and interaction sessions."}
                </small>
              </button>
              {!publicDemo && (
                <button type="button" onClick={() => void openParticipation()}>
                  <span className="toolbox-sticker sticker-mint">SMART</span>
                  <strong>Smart Participation</strong>
                  <small>
                    {zh
                      ? "调整角色参与风格、Primary / Secondary 关系，并用 Playground 快速测试。"
                      : "Tune participation style, Primary / Secondary relationships, and test them in the Playground."}
                  </small>
                </button>
              )}
              <button type="button" onClick={() => run(onWorkspace)}>
                <span className="toolbox-sticker sticker-mint">TEST</span>
                <strong>{zh ? "Echo Masque 测试" : "Echo Masque Lab"}</strong>
                <small>
                  {zh
                    ? "进入测试工作区、测试包与运行记录。"
                    : "Open test workspaces, packs, and run history."}
                </small>
              </button>
              {!publicDemo && (
                <button type="button" onClick={() => run(onMatrix)}>
                  <span className="toolbox-sticker sticker-peach">MATRIX</span>
                  <strong>{zh ? "Echo Masque 矩阵" : "Echo Masque Matrix"}</strong>
                  <small>
                    {zh
                      ? "查看跨角色与跨场景评测矩阵。"
                      : "Review evaluation coverage across characters and scenarios."}
                  </small>
                </button>
              )}
              {user.role === "admin" && !publicDemo && (
                <button type="button" onClick={() => run(onAdmin)}>
                  <span className="toolbox-sticker sticker-rose">ADMIN</span>
                  <strong>{zh ? "管理员设置" : "Admin settings"}</strong>
                  <small>
                    {zh
                      ? "管理 Runtime、Provider 与系统配置。"
                      : "Manage runtime, provider, and system settings."}
                  </small>
                </button>
              )}
              {publicDemo && (
                <button type="button" onClick={() => void onLogout()}>
                  <span className="toolbox-sticker sticker-rose">DEMO</span>
                  <strong>{zh ? "退出 Demo" : "Sign out of Demo"}</strong>
                  <small>{zh ? "结束共享测试 Session。" : "End the shared demo session."}</small>
                </button>
              )}
            </section>
          )}

          {section === "participation" && !publicDemo && (
            participationLoading ? (
              <section className="smart-participation-studio">
                <button className="text-button" type="button" onClick={() => setSection("actions")}>
                  ← {zh ? "返回" : "Back"}
                </button>
                <p>{zh ? "正在读取 Character Cards…" : "Loading Character Cards…"}</p>
              </section>
            ) : participationError ? (
              <section className="smart-participation-studio">
                <button className="text-button" type="button" onClick={() => setSection("actions")}>
                  ← {zh ? "返回" : "Back"}
                </button>
                <p className="error-note">{participationError}</p>
              </section>
            ) : (
              <SmartParticipationStudio
                cards={participationCards}
                zh={zh}
                onBack={() => setSection("actions")}
              />
            )
          )}

          {section === "account" && !publicDemo && (
            <AccountPanel
              embedded
              user={user}
              onClose={() => setSection("actions")}
              onLogout={onLogout}
              onDeleted={onAccountDeleted}
            />
          )}

          {section === "provider" && user.role === "admin" && !publicDemo && (
            <ProviderTraceViewer embedded onClose={() => setSection("actions")} />
          )}
        </PaperModal>
      )}
    </>
  );
}