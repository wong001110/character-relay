import type { CharacterCard } from "./api";
import { useI18n } from "./i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface Props {
  cards: CharacterCard[];
  error: string | null;
  onCreate: () => void;
  onEnter: (card: CharacterCard) => void;
}

const subjectKeys = {
  companion: "subject.companion",
  npc: "subject.npc",
  assistant: "subject.assistant",
  custom: "subject.custom"
} as const;

export function CharacterShelf({ cards, error, onCreate, onEnter }: Props) {
  const { t } = useI18n();

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

      {error && <p className="error-note">{error}</p>}

      <section className="card-grid" aria-label={t("shelf.cardsAria")}>
        {cards.map((card, index) => (
          <article
            className={`character-card portrait-${card.portrait_variant}`}
            key={card.id}
            style={{ transform: `rotate(${index % 2 === 0 ? -0.45 : 0.45}deg)` }}
          >
            <div className="card-tape" />
            <div className="portrait-window">
              <img src="/assets/character-silhouette.svg" alt="" />
              <span>{t(subjectKeys[card.subject_type])}</span>
            </div>
            <div className="card-copy">
              <p className="card-index">
                {t("shelf.file")} / {String(index + 1).padStart(2, "0")}
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
              <strong>{card.target_id.replace("demo-", "")}</strong>
              <span>{t("shelf.preferredRooms")}</span>
              <strong>{card.preferred_suites.length}</strong>
            </div>
            <button className="enter-room" onClick={() => onEnter(card)}>
              {t("shelf.enterRoom")}
            </button>
          </article>
        ))}

        <button className="blank-card" onClick={onCreate}>
          <span className="plus-mark">+</span>
          <strong>{t("shelf.createAnother")}</strong>
          <small>{t("shelf.bindHelp")}</small>
        </button>
      </section>
    </main>
  );
}
