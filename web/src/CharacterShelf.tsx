import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import { useI18n } from "./i18n";
import {
  NotebookField,
  NotebookInput,
  NotebookSelect
} from "./NotebookUI";
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

  function clearFilters() {
    setQuery("");
    setSubject("all");
    setTag("all");
    setSort("newest");
  }

  return (
    <main className="notebook-shell character-library-v2">
      <section className="character-library-layout">
        <div className="character-library-main">
          <header className="character-library-heading">
            <div>
              <span className="portal-v2-tape">
                {demoMode ? "READ-ONLY CHARACTER FILES" : "CHARACTER STUDIO"}
              </span>
              <h1>
                {zh ? "角色档案架" : "Character files"}
              </h1>
              <p>
                {demoMode
                  ? zh
                    ? "浏览共享角色档案、Prompt、语义配置与部署结构。"
                    : "Browse the shared character files, prompts, semantic profiles, and deployment structure."
                  : zh
                    ? "把每个角色当成一份持续完善的档案：创作、测试、部署，再从真实行为继续修订。"
                    : "Treat every character as a living file: create, test, deploy, then refine it from real behavior."}
              </p>
            </div>
            <aside className="character-library-count-note" aria-label={t("shelf.cardsFiled")}>
              <span>{zh ? "FILED" : "FILED"}</span>
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

          {error && <p className="error-note">{error}</p>}

          {cards.length === 0 ? (
            <section className="empty-library paper-sheet">
              <img src="/assets/brand/character-relay-mark.png" alt="" />
              <h2>{t("shelf.emptyTitle")}</h2>
              <p>{t("shelf.emptyHelp")}</p>
              {!demoMode && (
                <button className="ink-button" onClick={onCreate}>
                  {t("shelf.newCard")}
                </button>
              )}
            </section>
          ) : (
            <>
              <section className="card-grid character-file-grid" aria-label={t("shelf.cardsAria")}>
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
                      <button className="paper-button" onClick={() => setSemanticCard(card)}>
                        Semantic Profile
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
        </div>

        <aside className="character-library-tools" aria-label={t("shelf.filters")}>
          <div className="character-library-tools-note">
            <span>{zh ? "档案工具" : "SHELF TOOLS"}</span>
            <strong>{zh ? "找角色，不要找表格。" : "Find a character, not a spreadsheet."}</strong>
            <small>
              {zh
                ? "搜索和筛选固定放在页边，角色卡只负责展示角色本身。"
                : "Search and filters stay in the margin so the character cards can stay about the characters."}
            </small>
          </div>

          <section className="character-library-filter-note">
            <NotebookField label={t("shelf.search")}>
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

            <div className="character-library-filter-summary">
              <span>
                {zh
                  ? `${activeFilterCount} 个筛选条件 · ${filtered.length} 个结果`
                  : `${activeFilterCount} active filters · ${filtered.length} results`}
              </span>
              <button type="button" onClick={clearFilters} disabled={activeFilterCount === 0 && sort === "newest"}>
                {zh ? "重置" : "Reset"}
              </button>
            </div>
          </section>

          {tags.length > 0 && (
            <section className="character-library-tag-note">
              <span>{zh ? "常用标签" : "FILED TAGS"}</span>
              <div>
                {tags.slice(0, 8).map((item) => (
                  <button
                    type="button"
                    className={tag === item ? "is-active" : ""}
                    onClick={() => setTag(tag === item ? "all" : item)}
                    key={item}
                  >
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

      {semanticCard && (
        <SemanticProfilePanel
          card={semanticCard}
          zh={zh}
          demoMode={demoMode}
          onClose={() => setSemanticCard(null)}
        />
      )}
    </main>
  );
}
