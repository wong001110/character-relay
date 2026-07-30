import { useEffect, useMemo, useState } from "react";

import type { CharacterCard } from "./api";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface Props {
  cards: CharacterCard[];
  error: string | null;
  onCreate: () => void;
  onEdit: (card: CharacterCard) => void;
  onEnter: (card: CharacterCard) => void;
  onAdmin: () => void;
  onWorkspace: () => void;
  onMatrix: () => void;
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
  onCreate,
  onEdit,
  onEnter,
  onAdmin,
  onWorkspace,
  onMatrix
}: Props) {
  const { language, t } = useI18n();
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
          <img src="/assets/masque-mark.svg" alt="" />
          <div>
            <p className="kicker">{t("shelf.kicker")}</p>
            <h1>Echo Masque</h1>
            <p>{t("shelf.tagline")}</p>
          </div>
        </div>
        <div className="header-actions">
          <LanguageSwitcher />
          <button className="paper-button" onClick={onMatrix}>
            {language === "zh-CN" ? "矩阵实验室" : "Matrix Lab"}
          </button>
          <button className="paper-button" onClick={onWorkspace}>
            {language === "zh-CN" ? "实验工作区" : "Workspace"}
          </button>
          <button className="paper-button" onClick={onAdmin}>
            {t("shelf.admin")}
          </button>
          <button className="ink-button" onClick={onCreate}>
            {t("shelf.newCard")}
          </button>
        </div>
      </header>

      <section className="shelf-intro paper-sheet">
        <div>
          <p className="tape-label">{t("shelf.label")}</p>
          <h2>{t("shelf.heading")}</h2>
          <p>{t("shelf.description")}</p>
        </div>
        <div className="shelf-count">
          <strong>{cards.length}</strong>
          <span>{t("shelf.cardsFiled")}</span>
        </div>
      </section>

      <section className="library-toolbar paper-sheet" aria-label={t("shelf.filters")}>
        <label className="library-search">
          <span>{t("shelf.search")}</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder={t("shelf.searchPlaceholder")}
          />
        </label>
        <label>
          <span>{t("shelf.subjectFilter")}</span>
          <select value={subject} onChange={(event) => setSubject(event.currentTarget.value)}>
            <option value="all">{t("shelf.allSubjects")}</option>
            <option value="companion">{t("subject.companion")}</option>
            <option value="npc">{t("subject.npc")}</option>
            <option value="assistant">{t("subject.assistant")}</option>
            <option value="custom">{t("subject.custom")}</option>
          </select>
        </label>
        <label>
          <span>{t("shelf.tagFilter")}</span>
          <select value={tag} onChange={(event) => setTag(event.currentTarget.value)}>
            <option value="all">{t("shelf.allTags")}</option>
            {tags.map((item) => (
              <option value={item} key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          <span>{t("shelf.sort")}</span>
          <select value={sort} onChange={(event) => setSort(event.currentTarget.value)}>
            <option value="newest">{t("shelf.newest")}</option>
            <option value="oldest">{t("shelf.oldest")}</option>
            <option value="name">{t("shelf.nameSort")}</option>
          </select>
        </label>
      </section>

      {error && <p className="error-note">{error}</p>}

      {cards.length === 0 ? (
        <section className="empty-library paper-sheet">
          <img src="/assets/masque-mark.svg" alt="" />
          <h2>{t("shelf.emptyTitle")}</h2>
          <p>{t("shelf.emptyHelp")}</p>
          <button className="ink-button" onClick={onCreate}>{t("shelf.newCard")}</button>
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
                  <button className="paper-button" onClick={() => onEdit(card)}>
                    {t("shelf.edit")}
                  </button>
                  <button className="enter-room" onClick={() => onEnter(card)}>
                    {t("shelf.enterRoom")}
                  </button>
                </div>
              </article>
            ))}

            {page === pageCount && (
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
