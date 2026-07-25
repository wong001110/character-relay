import { useEffect, useState } from "react";

import { api, type CharacterCard, type TargetView } from "./api";
import { CharacterCreator } from "./CharacterCreator";
import { CharacterShelf } from "./CharacterShelf";
import { TestRoom } from "./TestRoom";
import "./styles.css";
import "./polish.css";

export default function App() {
  const [cards, setCards] = useState<CharacterCard[]>([]);
  const [targets, setTargets] = useState<TargetView[]>([]);
  const [activeCard, setActiveCard] = useState<CharacterCard | null>(null);
  const [showCreator, setShowCreator] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [nextCards, nextTargets] = await Promise.all([
        api.listCharacters(),
        api.listTargets()
      ]);
      setCards(nextCards);
      setTargets(nextTargets);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to open the card shelf.");
    }
  }

  useEffect(() => { void load(); }, []);

  if (activeCard) {
    const target = targets.find((item) => item.id === activeCard.target_id);
    if (!target) {
      return (
        <main className="room-page">
          <section className="paper-sheet missing-binding">
            <h1>Target binding unavailable.</h1>
            <p>The Character Card points to a target that could not be loaded.</p>
            <button className="paper-button" onClick={() => setActiveCard(null)}>
              Return to Character Shelf
            </button>
          </section>
        </main>
      );
    }
    return <TestRoom card={activeCard} target={target} onBack={() => setActiveCard(null)} />;
  }

  return (
    <>
      <CharacterShelf
        cards={cards}
        error={error}
        onCreate={() => setShowCreator(true)}
        onEnter={setActiveCard}
      />
      {showCreator && (
        <CharacterCreator
          targets={targets}
          onClose={() => setShowCreator(false)}
          onCreated={() => { setShowCreator(false); void load(); }}
        />
      )}
    </>
  );
}
