import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import { CharacterPortrait } from "./CharacterPortrait";
import { characterPortraitApi } from "./characterPortraitApi";
import {
  Button,
  EmptyState,
  PaperDrawer,
  SearchField,
  Select,
  StickyLabel,
  Toast
} from "./components/ui";
import { useI18n } from "./i18n";
import { SemanticProfilePanel } from "./SemanticProfilePanel";

interface Props {
  cards: CharacterCard[];
  error: string | null;
  demoMode?: boolean;
  onCreate: () => void;
  onEdit: (card: CharacterCard) => void;
  onPrompt: (card: CharacterCard) => void;
  onEnter: (card: CharacterCard) => void;
  onDeploy: (card: CharacterCard) => void;
}

const PAGE_SIZE = 8;

const subjectKeys = {
  companion: "subject.companion",
  npc: "subject.npc",
  assistant: "subject.assistant",
  custom: "subject.custom"
} as const;

export function CharacterShelf({
  cards,
  error,
  demoMode = false,
  onCreate,
  onEdit,
  onPrompt,
  onEnter,
  onDeploy
}: Props) {
  const { language, t } = useI18n();
  const zh = language === "zh-CN";
  const [query, setQuery] = useState("");
  const [subject, setSubject] = useState("all");
  const [tag, setTag] = useState("all");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [semanticCard, setSemanticCard] = useState<CharacterCard | null>(null);
  const [fileCard, setFileCard] = useState<CharacterCard | null>(null);
  const [portraitVersions, setPortraitVersions] = useState<Record<string, number>>({});
  const [portraitWorking, setPortraitWorking] = useState<string | null>(null);
  const [portraitMessage, setPortraitMessage] = useState<string | null>(null);

  const tags = useMemo(
    () => [...new Set(cards.flatMap((card) => card.tags))].sort((a, b) => a.localeCompare(b)),
    [cards]
  );
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const next = cards.filter((card) => {
      const searchable = [
        card.display_name,
        card.subtitle,
        card.persona_summary,
        ...card.traits,
        ...card.tags
      ]
        .join(" ")
        .toLocaleLowerCase();
      return (
        (!needle || searchable.includes(needle)) &&
        (subject === "all" || card.subject_type === subject) &&
        (tag === "all" || card.tags.includes(tag))
      );
    });
    return [...next].sort((left, right) => {
      if (sort === "name") return left.display_name.localeCompare(right.display_name);
      if (sort === "oldest") return left.created_at.localeCompare(right.created_at);
      return right.created_at.localeCompare(left.created_at);
    });
  }, [cards, query, subject, tag, sort]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageCards = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const activeFilterCount = Number(Boolean(query.trim())) + Number(subject !== "all") + Number(tag !== "all");

  useEffect(() => {
    setPage(1);
  }, [query, subject, tag, sort]);

  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  useEffect(() => {
    if (!fileCard) return;
    const fresh = cards.find((item) => item.id === fileCard.id);
    if (!fresh) setFileCard(null);
    else if (fresh !== fileCard) setFileCard(fresh);
  }, [cards, fileCard]);

  function clearFilters() {
    setQuery("");
    setSubject("all");
    setTag("all");
    setSort("newest");
  }

  async function uploadPortrait(card: CharacterCard, file: File | null) {
    if (!file) return;
    try {
      setPortraitWorking(card.id);
      setPortraitMessage(null);
      await characterPortraitApi.upload(card.id, file);
      setPortraitVersions((current) => ({ ...current, [card.id]: Date.now() }));
      setPortraitMessage(
        zh
          ? `已更新 ${card.display_name} 的角色图片。未设置 Deployment icon 时，Discord 会继承这张图片。`
          : `Updated ${card.display_name}'s portrait. Discord inherits it when the Deployment has no custom icon.`
      );
    } catch (reason) {
      setPortraitMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPortraitWorking(null);
    }
  }

  async function removePortrait(card: CharacterCard) {
    try {
      setPortraitWorking(card.id);
      setPortraitMessage(null);
      await characterPortraitApi.remove(card.id);
      setPortraitVersions((current) => ({ ...current, [card.id]: Date.now() }));
      setPortraitMessage(
        zh ? `已移除 ${card.display_name} 的角色图片。` : `Removed ${card.display_name}'s portrait.`
      );
    } catch (reason) {
      setPortraitMessage(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPortraitWorking(null);
    }
  }

  return (
    <main className="notebook-shell character-library-v2 character-library-v3">
      <section className="character-library-layout">
        <div className="character-library-main">
          <header className="character-library-heading">
            <div>
              <span className="portal-v2-tape">
                {demoMode ? "READ-ONLY CHARACTER FILES" : "CHARACTER STUDIO"}
              </span>
              <h1>{zh ? "角色档案架" : "Character files"}</h1>
              <p>
                {demoMode
                  ? zh
                    ? "浏览共享角色档案、Prompt、语义配置与部署结构。"
                    : "Browse shared character files, prompts, semantic profiles, and deployment structure."
                  : zh
                    ? "角色卡只负责让你认出这个角色；编辑、Prompt、语义与图片管理统一收进档案页。"
                    : "Cards stay focused on character identity; editing, prompts, semantics, and portrait management live inside the file."}
              </p>
            </div>
            <aside className="character-library-count-note" aria-label={t("shelf.cardsFiled")}>
              <span>FILED</span>
              <strong>{filtered.length}</strong>
              <small>
                {filtered.length === cards.length
                  ? t("shelf.cardsFiled")
                  : zh
                    ? `共 ${cards.length} 张角色卡`
                    : `of ${cards.length} character cards`}
              </small>
            </aside>
          </header>

          {error && <Toast tone="danger" title={zh ? "角色档案读取失败" : "Character files unavailable"}>{error}</Toast>}
          {portraitMessage && <Toast tone="success" title={zh ? "角色图片已更新" : "Portrait updated"}>{portraitMessage}</Toast>}

          {cards.length === 0 ? (
            <EmptyState
              className="empty-library paper-sheet"
              illustration={<img src="/assets/brand/character-relay-mark.png" alt="" />}
              title={t("shelf.emptyTitle")}
              description={t("shelf.emptyHelp")}
              action={!demoMode ? <Button variant="primary" onClick={onCreate}>{t("shelf.newCard")}</Button> : undefined}
            />
          ) : (
            <>
              <section className="card-grid character-file-grid" aria-label={t("shelf.cardsAria")}>
                {pageCards.map((card, index) => (
                  <article className={`character-card portrait-${card.portrait_variant}`} key={card.id}>
                    <div className="card-tape" />
                    <button
                      type="button"
                      className="character-file-cover"
                      onClick={() => setFileCard(card)}
                      aria-label={`${zh ? "打开档案" : "Open file"}: ${card.display_name}`}
                    >
                      <div className="portrait-window">
                        <CharacterPortrait
                          cardId={card.id}
                          version={portraitVersions[card.id] ?? 0}
                          alt={card.display_name}
                        />
                        <span>{t(subjectKeys[card.subject_type])}</span>
                      </div>
                      <div className="card-copy">
                        <p className="card-index">
                          {t("shelf.file")} / {String((page - 1) * PAGE_SIZE + index + 1).padStart(2, "0")}
                        </p>
                        <h3>{card.display_name}</h3>
                        <p>{card.subtitle}</p>
                        <div className="chip-row">
                          {card.traits.slice(0, 3).map((trait) => <span key={trait}>{trait}</span>)}
                        </div>
                      </div>
                    </button>
                    <div className="card-notes">
                      <span>{t("shelf.boundTarget")}</span>
                      <strong>{card.target_id.slice(0, 12)}</strong>
                      <span>{t("shelf.preferredRooms")}</span>
                      <strong>{card.preferred_suites.length}</strong>
                    </div>
                    <div className="card-actions character-card-primary-actions">
                      <Button variant="primary" onClick={() => onEnter(card)}>
                        {zh ? "测试角色" : "Test Character"}
                      </Button>
                      <Button variant="secondary" onClick={() => setFileCard(card)}>
                        {zh ? "打开档案" : "Open File"}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => onDeploy(card)}>
                        {zh ? "部署" : "Deploy"}
                      </Button>
                    </div>
                  </article>
                ))}

                {!demoMode && page === pageCount && (
                  <button className="blank-card" onClick={onCreate}>
                    <span className="plus-mark">+</span>
                    <strong>{t("shelf.createAnother")}</strong>
                    <small>{t("shelf.bindHelp")}</small>
                  </button>
                )}
              </section>

              {filtered.length === 0 && (
                <EmptyState
                  className="no-results paper-sheet"
                  title={t("shelf.noResults")}
                  description={t("shelf.noResultsHelp")}
                  action={<Button variant="secondary" onClick={clearFilters}>{zh ? "清除筛选" : "Clear filters"}</Button>}
                />
              )}

              {pageCount > 1 && (
                <nav className="library-pagination" aria-label={t("shelf.pagination")}>
                  <Button variant="secondary" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}>
                    {t("shelf.previous")}
                  </Button>
                  <span>{t("shelf.page", { page, pages: pageCount })}</span>
                  <Button variant="secondary" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page === pageCount}>
                    {t("shelf.next")}
                  </Button>
                </nav>
              )}
            </>
          )}
        </div>

        <aside className="character-library-tools" aria-label={t("shelf.filters")}>
          <div className="character-library-tools-note">
            <span>{zh ? "档案工具" : "SHELF TOOLS"}</span>
            <strong>{zh ? "找角色，不要找表格。" : "Find a character, not a spreadsheet."}</strong>
            <small>{zh ? "搜索与分类固定在页边，卡片只保留真正需要的动作。" : "Search and classification stay in the margin; cards keep only the actions you need most."}</small>
          </div>

          <section className="character-library-filter-note">
            <label className="character-library-filter-field">
              <span>{t("shelf.search")}</span>
              <SearchField
                value={query}
                onChange={(event) => setQuery(event.currentTarget.value)}
                placeholder={t("shelf.searchPlaceholder")}
                label={t("shelf.search")}
              />
            </label>
            <label className="character-library-filter-field">
              <span>{t("shelf.subjectFilter")}</span>
              <Select value={subject} onChange={(event) => setSubject(event.currentTarget.value)}>
                <option value="all">{t("shelf.allSubjects")}</option>
                <option value="companion">{t("subject.companion")}</option>
                <option value="npc">{t("subject.npc")}</option>
                <option value="assistant">{t("subject.assistant")}</option>
                <option value="custom">{t("subject.custom")}</option>
              </Select>
            </label>
            <label className="character-library-filter-field">
              <span>{t("shelf.tagFilter")}</span>
              <Select value={tag} onChange={(event) => setTag(event.currentTarget.value)}>
                <option value="all">{t("shelf.allTags")}</option>
                {tags.map((item) => <option value={item} key={item}>{item}</option>)}
              </Select>
            </label>
            <label className="character-library-filter-field">
              <span>{t("shelf.sort")}</span>
              <Select value={sort} onChange={(event) => setSort(event.currentTarget.value)}>
                <option value="newest">{t("shelf.newest")}</option>
                <option value="oldest">{t("shelf.oldest")}</option>
                <option value="name">{t("shelf.nameSort")}</option>
              </Select>
            </label>

            <div className="character-library-filter-summary">
              <span>{zh ? `${activeFilterCount} 个筛选条件 · ${filtered.length} 个结果` : `${activeFilterCount} active filters · ${filtered.length} results`}</span>
              <Button variant="ghost" size="sm" type="button" onClick={clearFilters} disabled={activeFilterCount === 0 && sort === "newest"}>
                {zh ? "重置" : "Reset"}
              </Button>
            </div>
          </section>

          {tags.length > 0 && (
            <section className="character-library-tag-note">
              <span>{zh ? "常用标签" : "FILED TAGS"}</span>
              <div>
                {tags.slice(0, 8).map((item) => (
                  <button type="button" className={tag === item ? "is-active" : ""} onClick={() => setTag(tag === item ? "all" : item)} key={item}>
                    #{item}
                  </button>
                ))}
              </div>
            </section>
          )}

          {!demoMode && (
            <button className="character-library-create-note" type="button" onClick={onCreate}>
              <span>＋</span>
              <strong>{t("shelf.newCard")}</strong>
              <small>{zh ? "建立新的角色档案" : "File a new character"}</small>
            </button>
          )}
        </aside>
      </section>

      {fileCard && (
        <PaperDrawer
          onClose={() => setFileCard(null)}
          ariaLabel={`${fileCard.display_name} · ${zh ? "角色档案" : "Character file"}`}
          className="character-file-drawer"
        >
          <div className="character-file-drawer-sheet">
            <header className="character-file-drawer-header">
              <div>
                <StickyLabel variant="neutral">CHARACTER FILE</StickyLabel>
                <h2>{fileCard.display_name}</h2>
                <p>{fileCard.subtitle}</p>
              </div>
              <Button variant="ghost" onClick={() => setFileCard(null)}>{zh ? "关闭" : "Close"}</Button>
            </header>

            <div className={`character-file-drawer-portrait portrait-${fileCard.portrait_variant}`}>
              <CharacterPortrait
                cardId={fileCard.id}
                version={portraitVersions[fileCard.id] ?? 0}
                alt={fileCard.display_name}
              />
            </div>

            <div className="character-file-drawer-tags">
              <StickyLabel variant="neutral">{t(subjectKeys[fileCard.subject_type])}</StickyLabel>
              {fileCard.traits.slice(0, 5).map((trait) => <StickyLabel key={trait} variant="neutral">{trait}</StickyLabel>)}
            </div>

            {!demoMode && (
              <section className="character-file-portrait-tools">
                <strong>{zh ? "角色图片" : "Portrait"}</strong>
                <div>
                  <label className="cr-button cr-button--secondary cr-control--sm character-file-upload-button">
                    {portraitWorking === fileCard.id ? (zh ? "处理中…" : "Working…") : (zh ? "更换图片" : "Change image")}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      disabled={portraitWorking === fileCard.id}
                      onChange={(event) => {
                        const file = event.currentTarget.files?.[0] ?? null;
                        void uploadPortrait(fileCard, file);
                        event.currentTarget.value = "";
                      }}
                    />
                  </label>
                  <Button variant="ghost" size="sm" disabled={portraitWorking === fileCard.id} onClick={() => void removePortrait(fileCard)}>
                    {zh ? "移除图片" : "Remove image"}
                  </Button>
                </div>
              </section>
            )}

            <section className="character-file-drawer-actions">
              <Button variant="primary" onClick={() => { setFileCard(null); onEnter(fileCard); }}>
                {zh ? "测试角色" : "Test Character"}
              </Button>
              {!demoMode && <Button variant="secondary" onClick={() => { setFileCard(null); onEdit(fileCard); }}>{zh ? "编辑角色卡" : "Edit Character"}</Button>}
              <Button variant="secondary" onClick={() => onPrompt(fileCard)}>{zh ? "查看真实 Prompt" : "View Prompt"}</Button>
              <Button variant="secondary" onClick={() => setSemanticCard(fileCard)}>Semantic Profile</Button>
              <Button variant="secondary" onClick={() => { setFileCard(null); onDeploy(fileCard); }}>{zh ? "打开部署" : "Open Deployment"}</Button>
            </section>
          </div>
        </PaperDrawer>
      )}

      {semanticCard && (
        <SemanticProfilePanel card={semanticCard} zh={zh} demoMode={demoMode} onClose={() => setSemanticCard(null)} />
      )}
    </main>
  );
}