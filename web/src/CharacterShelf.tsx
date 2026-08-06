import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";
import {
  NotebookField,
  NotebookInput,
  NotebookSelect
} from "./NotebookUI";

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

  useEffect(() => {
    setPage(1);
  }, [query, subject, tag, sort]);

  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  return (
    <main className="notebook-shell">
      <header className="journal-header">
        <div className="brand-lockup">
          <img
            className="brand-wordmark"
            src="/assets/brand/character-relay-wordmark.png"
            alt="Character Relay"
          />
          <div>
            <p className="kicker">
              {zh ? "AI 角色创建、测试与跨平台部署" : "AI character creation, testing, and deployment"}
            </p>
            <h1 className="brand-accessible-title">Character Relay</h1>
            <p>
              {zh
                ? "创建一次，验证角色，再把稳定版本带进真实群聊。"
                : "Create once, validate the character, and bring stable versions into real conversations."}
            </p>
          </div>
        </div>
        <div className="header-actions shelf-primary-actions">
          <LanguageSwitcher />
          {demoMode && <span className="status-chip pass">PUBLIC DEMO</span>}
          {!demoMode && (
            <button className="ink-button" onClick={onCreate}>
              {t("shelf.newCard")}
            </button>
          )}
        </div>
      </header>

      <section className="shelf-intro paper-sheet">
        <div>
          <p className="tape-label">{demoMode ? "READ-ONLY DEMO" : "CHARACTER STUDIO"}</p>
          <h2>
            {zh
              ? "把角色卡从创作资产，变成可测试、可发布、可部署的角色。"
              : "Turn Character Cards into testable, publishable, deployable characters."}
          </h2>
          <p>
            {demoMode
              ? zh
                ? "共享测试账户已预载角色卡、测试场景与测试包。可以查看 Prompt、进入 Echo Masque 测试房并查看部署结构，但不能修改共享内容。"
                : "This shared account includes Character Cards, Scenarios, and Test Packs. You can inspect prompts, enter the Echo Masque test room, and view deployment structure, but shared content cannot be changed."
              : zh
                ? "角色库只保留创作与角色级操作。部署、测试、账户和诊断工具集中在右下角的猫咪工具箱。"
                : "The shelf stays focused on character work. Deployment, testing, account, and diagnostic tools are collected in the cat toolbox at the bottom right."}
          </p>
        </div>
        <div className="shelf-count">
          <strong>{cards.length}</strong>
          <span>{t("shelf.cardsFiled")}</span>
        </div>
      </section>

      <section className="library-toolbar paper-sheet" aria-label={t("shelf.filters")}>
        <NotebookField className="library-search" label={t("shelf.search")}>
          <NotebookInput
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder={t("shelf.searchPlaceholder")}
          />
        </NotebookField>
        <NotebookField label={t("shelf.subjectFilter")}>
          <NotebookSelect value={subject} onChange={(event) => setSubject(event.currentTarget.value)}>
            <option value="all">{t("shelf.allSubjects")}</option>
            <option value="companion">{t("subject.companion")}</option>
            <option value="npc">{t("subject.npc")}</option>
            <option value="assistant">{t("subject.assistant")}</option>
            <option value="custom">{t("subject.custom")}</option>
          </NotebookSelect>
        </NotebookField>
        <NotebookField label={t("shelf.tagFilter")}>
          <NotebookSelect value={tag} onChange={(event) => setTag(event.currentTarget.value)}>
            <option value="all">{t("shelf.allTags")}</option>
            {tags.map((item) => (
              <option value={item} key={item}>{item}</option>
            ))}
          </NotebookSelect>
        </NotebookField>
        <NotebookField label={t("shelf.sort")}>
          <NotebookSelect value={sort} onChange={(event) => setSort(event.currentTarget.value)}>
            <option value="newest">{t("shelf.newest")}</option>
            <option value="oldest">{t("shelf.oldest")}</option>
            <option value="name">{t("shelf.nameSort")}</option>
          </NotebookSelect>
        </NotebookField>
      </section>

      {error && <p className="error-note">{error}</p>}

      {cards.length === 0 ? (
        <section className="empty-library paper-sheet">
          <img src="/assets/brand/character-relay-mark.png" alt="" />
          <h2>{t("shelf.emptyTitle")}</h2>
          <p>{t("shelf.emptyHelp")}</p>
          {!demoMode && <button className="ink-button" onClick={onCreate}>{t("shelf.newCard")}</button>}
        </section>
      ) : (
        <>
          <section className="card-grid" aria-label={t("shelf.cardsAria")}>
            {pageCards.map((card, index) => (
              <article
                className={`character-card portrait-${card.portrait_variant}`}
                key={card.id}
              >
                <div className="card-tape" />
                <div className="portrait-window">
                  <img src="/assets/character-silhouette.svg" alt="" />
                  <span>{t(subjectKeys[card.subject_type])}</span>
                </div>
                <div className="card-copy">
                  <p className="card-index">
                    {t("shelf.file")} / {String((page - 1) * PAGE_SIZE + index + 1).padStart(2, "0")}
                  </p>
                  <h3>{card.display_name}</h3>
                  <p>{card.subtitle}</p>
                  <div className="chip-row">
                    {card.traits.slice(0, 3).map((trait) => (
                      <span key={trait}>{trait}</span>
                    ))}
                  </div>
                </div>
                <div className="card-notes">
                  <span>{t("shelf.boundTarget")}</span>
                  <strong>{card.target_id.slice(0, 12)}</strong>
                  <span>{t("shelf.preferredRooms")}</span>
                  <strong>{card.preferred_suites.length}</strong>
                </div>
                <div className="card-actions">
                  {!demoMode && (
                    <button className="paper-button" onClick={() => onEdit(card)}>
                      {t("shelf.edit")}
                    </button>
                  )}
                  <button className="paper-button" onClick={() => onPrompt(card)}>
                    {zh ? "真实 Prompt" : "View Prompt"}
                  </button>
                  <button className="paper-button" onClick={() => onDeploy(card)}>
                    {zh ? "部署" : "Deploy"}
                  </button>
                  <button className="enter-room" onClick={() => onEnter(card)}>
                    {zh ? "测试角色" : "Test Character"}
                  </button>
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
            <section className="no-results paper-sheet">
              <h3>{t("shelf.noResults")}</h3>
              <p>{t("shelf.noResultsHelp")}</p>
            </section>
          )}

          {pageCount > 1 && (
            <nav className="library-pagination" aria-label={t("shelf.pagination")}>
              <button
                className="paper-button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page === 1}
              >
                {t("shelf.previous")}
              </button>
              <span>{t("shelf.page", { page, pages: pageCount })}</span>
              <button
                className="paper-button"
                onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                disabled={page === pageCount}
              >
                {t("shelf.next")}
              </button>
            </nav>
          )}
        </>
      )}
    </main>
  );
}
