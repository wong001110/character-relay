export type PromptExportFormat = "raw" | "text" | "markdown" | "json" | "openai";

export interface PromptMessageView {
  role: "system";
  content: string;
}

export interface CharacterPromptView {
  character_card_id: string;
  display_name: string;
  target_id: string;
  runtime_kind: "prompt_model";
  provider: string;
  base_url: string;
  model: string;
  temperature: number;
  raw_system_prompt: string;
  compiled_system_prompt: string;
  system_prompt: string;
  messages: PromptMessageView[];
  compiler_version: string;
  compiled_prompt_hash: string;
  prompt_version_id: string | null;
  prompt_version: number | null;
  prompt_version_label: string | null;
  config_hash: string | null;
}

async function detail(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const value = JSON.parse(raw) as { detail?: unknown };
    if (typeof value.detail === "string") return value.detail;
  } catch {
    // Preserve the raw response below.
  }
  return raw || `Request failed with ${response.status}`;
}

export const promptApi = {
  inspect: async (cardId: string): Promise<CharacterPromptView> => {
    const response = await fetch(`/api/characters/${encodeURIComponent(cardId)}/prompt`);
    if (!response.ok) throw new Error(await detail(response));
    return response.json() as Promise<CharacterPromptView>;
  },
  exportUrl: (cardId: string, format: PromptExportFormat): string =>
    `/api/characters/${encodeURIComponent(cardId)}/prompt/export?format=${encodeURIComponent(format)}`
};
