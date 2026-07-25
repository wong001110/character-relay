import { useEffect, useState } from "react";

import { api, type CharacterCard, type TargetView } from "./api";
import { CharacterCreator } from "./CharacterCreator";
import { CharacterShelf } from "./CharacterShelf";
import { TestRoom } from "./TestRoom";
import "./styles.css";

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
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to open the card shelf.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (activeCard) {
    return <TestRoom card={activeCard} onBack={() => setActiveCard(null)} />;
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
          onCreated={(card) => {
            setCards((current) => [...current, card]);
            setShowCreator(false);
          }}
        />
      )}
    </>
  );
}
