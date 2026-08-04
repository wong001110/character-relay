const GROUP_ADDRESS_LOCALE_PACKS = {
  zh: [
    "你们",
    "你們",
    "大家",
    "各位",
    "两位",
    "兩位",
    "所有人",
    "全部人",
    "全员",
    "全員",
    "所有角色",
    "全部角色",
    "一起回答",
    "都来说说",
    "都來說說"
  ],
  en: [
    "all of you",
    "both of you",
    "you all",
    "everyone",
    "everybody",
    "all characters",
    "both"
  ],
  ja: ["みんな", "皆さん", "皆様", "二人とも", "全員"],
  ko: ["여러분", "모두", "두 분", "둘 다"],
  ms: ["kamu semua", "anda semua", "semua orang", "korang"],
  id: ["kalian", "kamu semua", "semuanya", "semua orang"]
} as const;

export const DEFAULT_GROUP_ADDRESS_ALIASES = [
  ...new Set(Object.values(GROUP_ADDRESS_LOCALE_PACKS).flat())
].sort((left, right) => right.length - left.length);

export function groupAddressAliases(additional: string[] = []): string[] {
  return [
    ...new Set([
      ...DEFAULT_GROUP_ADDRESS_ALIASES,
      ...additional.map((item) => item.trim()).filter(Boolean)
    ])
  ].sort((left, right) => right.length - left.length);
}
