import { useEffect, useState } from "react";

import { characterPortraitUrl } from "./characterPortraitApi";

interface Props {
  cardId: string;
  version?: number;
  alt?: string;
  className?: string;
}

export function CharacterPortrait({ cardId, version = 0, alt = "", className }: Props) {
  const source = characterPortraitUrl(cardId, version);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [source]);

  return (
    <img
      src={failed ? "/assets/character-silhouette.svg" : source}
      alt={alt}
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
