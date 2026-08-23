import type { EpisodeObservation } from "./conversationStructureApi";

export const EPISODE_BOARD_PAGE_SIZE = 12;

export interface EpisodeBoardGroups {
  primary: EpisodeObservation[];
  fragments: EpisodeObservation[];
}

function compact(value: string): string {
  return value
    .replace(/https?:\/\/\S+/giu, "link")
    .replace(/\s+/gu, " ")
    .trim();
}

export function episodeDisplayTitle(episode: EpisodeObservation, maximumLength = 92): string {
  const title = compact(episode.summary);
  if (!title) return `Episode ${episode.id.slice(0, 8) || "—"}`;
  return title.length > maximumLength ? `${title.slice(0, Math.max(1, maximumLength - 1)).trimEnd()}…` : title;
}

export function groupEpisodesForBoard(episodes: EpisodeObservation[]): EpisodeBoardGroups {
  const primary: EpisodeObservation[] = [];
  const fragments: EpisodeObservation[] = [];
  for (const episode of episodes) {
    if (episode.checkpoint_reason === "unresolved_segment" || !episode.conversation_thread_id) {
      fragments.push(episode);
    } else {
      primary.push(episode);
    }
  }
  return { primary, fragments };
}
