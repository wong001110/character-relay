import { useEffect, useState } from "react";

import { AdminSettings } from "./AdminSettings";
import {
  api,
  type AdminRuntimeView,
  type CharacterCard,
  type RuntimeStatus,
  type TargetView
} from "./api";
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
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [activeCard, setActiveCard] = useState<CharacterCard | null>(null);
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [editingCard, setEditingCard] = useState<CharacterCard | null>(null);
  const [adminOpen, setAdminOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [nextCards, nextTargets, nextRuntime] = await Promise.all([
        api.listCharacters(),
        api.listTargets(),
        api.getRuntimeStatus()
      ]);
      setCards(nextCards);
      setTargets(nextTargets);
      setRuntime(nextRuntime);
      setActiveCard((current) =>
        current ? nextCards.find((item) => item.id === current.id) ?? null : null
      );
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("app.openShelfError"));
    }
  }

  useEffect(() => { void load(); }, []);

  function saved(card: CharacterCard) {
    setCreatorOpen(false);
    setEditingCard(null);
    setCards((current) => {
      const exists = current.some((item) => item.id === card.id);
      return exists
        ? current.map((item) => (item.id === card.id ? card : item))
        : [card, ...current];
    });
    setActiveCard((current) => (current?.id === card.id ? card : current));
    void load();
  }

  function runtimeUpdated(view: AdminRuntimeView) {
    setRuntime(view.status);
  }

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
    return (
      <>
        <TestRoom
          card={activeCard}
          target={target}
          runtime={runtime}
          onBack={() => setActiveCard(null)}
          onAdmin={() => setAdminOpen(true)}
        />
        {adminOpen && (
          <AdminSettings
            onClose={() => setAdminOpen(false)}
            onUpdated={runtimeUpdated}
          />
        )}
      </>
    );
  }

  const editingTarget = editingCard
    ? targets.find((item) => item.id === editingCard.target_id) ?? null
    : null;

  return (
    <>
      <CharacterShelf
        cards={cards}
        error={error}
        onCreate={() => {
          setEditingCard(null);
          setCreatorOpen(true);
        }}
        onEdit={(card) => {
          setEditingCard(card);
          setCreatorOpen(true);
        }}
        onEnter={setActiveCard}
        onAdmin={() => setAdminOpen(true)}
      />
      {creatorOpen && (
        <CharacterCreator
          targets={targets}
          card={editingCard}
          target={editingTarget}
          onClose={() => {
            setCreatorOpen(false);
            setEditingCard(null);
          }}
          onSaved={saved}
        />
      )}
      {adminOpen && (
        <AdminSettings
          onClose={() => setAdminOpen(false)}
          onUpdated={runtimeUpdated}
        />
      )}
    </>
  );
}
