import { useEffect, useState } from "react";

import { api, type CharacterCard, type TargetView } from "./api";
import { CharacterCreator } from "./CharacterCreator";
import { CharacterShelf } from "./CharacterShelf";
import { useI18n } from "./i18n";
import { TestRoom } from "./TestRoom";
import "./styles.css";
import "./polish.css";

export default function App() {
  const { t } = useI18n();
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
      setError(reason instanceof Error ? reason.message : t("app.openShelfError"));
    }
  }

  useEffect(() => { void load(); }, []);

  if (activeCard) {
    const target = targets.find((item) => item.id === activeCard.target_id);
    if (!target) {
      return (
        <main className="room-page">
          <section className="paper-sheet missing-binding">
            <h1>{t("app.bindingMissingTitle")}</h1>
            <p>{t("app.bindingMissingBody")}</p>
            <button className="paper-button" onClick={() => setActiveCard(null)}>
              {t("app.returnShelf")}
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
