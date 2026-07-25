export type ProviderId = "deepseek" | "openai" | "openrouter" | "custom";

export interface ProviderPreset {
  id: ProviderId;
  label: string;
  baseUrl: string;
  defaultModel: string;
  note: string;
}

export const providerPresets: ProviderPreset[] = [
  {
    id: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com",
    defaultModel: "deepseek-v4-flash",
    note: "OpenAI-compatible DeepSeek endpoint."
  },
  {
    id: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com",
    defaultModel: "",
    note: "Enter the exact model ID available to your OpenAI project."
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "",
    note: "Enter an OpenRouter model slug such as provider/model."
  },
  {
    id: "custom",
    label: "Custom compatible endpoint",
    baseUrl: "",
    defaultModel: "",
    note: "Any service exposing an OpenAI-compatible chat-completions API."
  }
];

export function getProviderPreset(id: ProviderId): ProviderPreset {
  return providerPresets.find((item) => item.id === id) ?? providerPresets[3];
}
