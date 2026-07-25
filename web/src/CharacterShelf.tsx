import type { CharacterCard } from "./api";

interface Props {
  cards: CharacterCard[];
  error: string | null;
  onCreate: () => void;
  onEnter: (card: CharacterCard) => void;
}

export function CharacterShelf({ cards, error, onCreate, onEnter }: Props) {
  return (
    <main className="notebook-shell">
      <header className="journal-header">
        <div className="brand-lockup">
          <img src="/assets/masque-mark.svg" alt="" />
          <div>
            <p className="kicker">Character observation journal</p>
            <h1>Echo Masque</h1>
            <p>Collect a character. Challenge the role. Keep the evidence.</p>
          </div>
        </div>
        <button className="ink-button" onClick={onCreate}>
          + New character card
        </button>
      </header>

      <section className="shelf-intro paper-sheet">
        <div>
          <p className="tape-label">Character Shelf</p>
          <h2>Your artificial cast, kept as observation cards.</h2>
          <p>
            Each card stores the identity you expect, the target it is bound to, and
            the rooms it should survive.
          </p>
        </div>
        <div className="shelf-count">
          <strong>{cards.length}</strong>
          <span>cards filed</span>
        </div>
      </section>

      {error && <p className="error-note">{error}</p>}

      <section className="card-grid" aria-label="Character Cards">
        {cards.map((card, index) => (
          <article
            className={`character-card portrait-${card.portrait_variant}`}
            key={card.id}
            style={{ transform: `rotate(${index % 2 === 0 ? -0.45 : 0.45}deg)` }}
          >
            <div className="card-tape" />
            <div className="portrait-window">
              <img src="/assets/character-silhouette.svg" alt="" />
              <span>{card.subject_type}</span>
            </div>
            <div className="card-copy">
              <p className="card-index">FILE / {String(index + 1).padStart(2, "0")}</p>
              <h3>{card.display_name}</h3>
              <p>{card.subtitle}</p>
              <div className="chip-row">
                {card.traits.slice(0, 3).map((trait) => (
                  <span key={trait}>{trait}</span>
                ))}
              </div>
            </div>
            <div className="card-notes">
              <span>Bound target</span>
              <strong>{card.target_id.replace("demo-", "")}</strong>
              <span>Preferred rooms</span>
              <strong>{card.preferred_suites.length}</strong>
            </div>
            <button className="enter-room" onClick={() => onEnter(card)}>
              Enter Test Room
            </button>
          </article>
        ))}

        <button className="blank-card" onClick={onCreate}>
          <span className="plus-mark">+</span>
          <strong>Create another subject</strong>
          <small>Bind a prompt, model, API, or existing target.</small>
        </button>
      </section>
    </main>
  );
}
