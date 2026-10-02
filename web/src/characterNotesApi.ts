import { roomRequest } from "./roomHttp";
export interface NoteLocation { connection_id: string; guild_id: string; channel_id: string; thread_id: string; }
export interface NoteInput { subject_ref: string; kind: "note" | "relationship"; text: string; }
export interface CharacterNote extends NoteInput { id: string; character_card_id: string; authored: boolean; scope: NoteLocation | null; actor_id: string; source_message_id: string; version: number; updated_at: string; }
const base = (card: string) => `/api/characters/${encodeURIComponent(card)}/notes`;
export const characterNotesApi = {
  list: (card: string, location: NoteLocation | null) => roomRequest<CharacterNote[]>(base(card) + (location ? `?${new URLSearchParams({ ...location })}` : "")),
  create: (card: string, input: NoteInput, location: NoteLocation | null) => roomRequest<CharacterNote>(base(card), { method: "POST", body: JSON.stringify({ ...input, location }) }),
  update: (card: string, note: CharacterNote, input: NoteInput) => roomRequest<CharacterNote>(`${base(card)}/${encodeURIComponent(note.id)}`, { method: "PATCH", body: JSON.stringify({ ...input, expected_version: note.version }) }),
  forget: (card: string, note: CharacterNote) => roomRequest<void>(`${base(card)}/${encodeURIComponent(note.id)}?expected_version=${note.version}`, { method: "DELETE" })
};
