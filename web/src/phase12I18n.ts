import { useI18n as useBaseI18n, type LanguageCode } from "./i18n";

type Values = Record<string, string | number>;

const english = {
  "creator.editLabel": "Edit Character Card",
  "creator.editHeading": "Revise this subject.",
  "creator.editHelp": "Update the profile and model configuration in place. Existing trial history and the current provider-key association are retained.",
  "creator.editKeyPreserved": "The existing API key association is preserved. Replace it from the Test Room only when needed.",
  "creator.saveChanges": "Save changes",
  "shelf.admin": "Admin Settings",
  "shelf.filters": "Character Library filters",
  "shelf.search": "Search",
  "shelf.searchPlaceholder": "Name, persona, trait, or tag",
  "shelf.subjectFilter": "Subject type",
  "shelf.allSubjects": "All subjects",
  "shelf.tagFilter": "Tag",
  "shelf.allTags": "All tags",
  "shelf.sort": "Sort",
  "shelf.newest": "Newest first",
  "shelf.oldest": "Oldest first",
  "shelf.nameSort": "Name A–Z",
  "shelf.edit": "Edit",
  "shelf.emptyTitle": "Your Character Library is empty.",
  "shelf.emptyHelp": "Built-in cards are no longer added. Create a real prompt-and-model subject to begin testing.",
  "shelf.noResults": "No matching Character Cards",
  "shelf.noResultsHelp": "Change the search text or filters to show more cards.",
  "shelf.pagination": "Character Library pages",
  "shelf.previous": "Previous",
  "shelf.page": "Page {page} of {pages}",
  "shelf.next": "Next",
  "admin.error": "Admin Runtime could not be updated.",
  "admin.saved": "Admin Runtime saved.",
  "admin.label": "Admin Runtime",
  "admin.heading": "Configure shared evaluation agents.",
  "admin.help": "Adaptive Tester and Semantic Judge are configured once by Admin and reused by every Test Room. Non-secret settings persist in SQLite; production secrets should come from Railway environment variables.",
  "admin.token": "Admin token",
  "admin.tokenPlaceholder": "X-Echo-Admin token",
  "admin.tokenHelp": "Development default: local-admin. Production requires ECHO_MASQUE_ADMIN_TOKEN.",
  "admin.connecting": "Checking…",
  "admin.connect": "Open Admin Settings",
  "admin.adaptiveTitle": "Adaptive Tester",
  "admin.judgeTitle": "Semantic Judge",
  "admin.enabled": "Enable this runtime",
  "admin.systemPrompt": "System prompt",
  "admin.temperature": "Temperature",
  "admin.maxTurns": "Maximum turns",
  "admin.rubricVersion": "Rubric version",
  "admin.defaultJudge": "Default Judge Mode",
  "admin.security": "Raw Adaptive and Judge keys are never written to SQLite, Trial events, reports, or logs. Configure ECHO_MASQUE_ADAPTIVE_API_KEY and ECHO_MASQUE_JUDGE_API_KEY in Railway for persistent production use. Keys entered here last only until the server restarts.",
  "admin.save": "Save Admin Runtime",
  "admin.runtime": "Shared runtime",
  "admin.ready": "Ready",
  "admin.missing": "Not ready",
  "admin.apiKey": "Process-memory API key",
  "admin.apiKeyPlaceholder": "Leave blank to keep the existing environment or memory key",
  "admin.clearMemoryKey": "Clear memory key",
  "judge.rules": "Rules",
  "judge.semantic": "Semantic",
  "judge.hybrid": "Hybrid",
  "judge.rulesHelp": "fast and deterministic",
  "judge.semanticHelp": "independent LLM rubric",
  "judge.hybridHelp": "rules + semantic review",
  "judge.review": "Manual review required",
  "room.adminAdaptiveMissing": "Adaptive Tester is unavailable. Ask Admin to configure and enable the shared runtime.",
  "room.adminJudgeMissing": "Semantic Judge is unavailable. Ask Admin to configure and enable the shared runtime.",
  "room.comparisonUnavailable": "This run cannot be used for the selected regression comparison.",
  "room.judgeMode": "Judge Mode",
  "room.semanticJudge": "Semantic Judge",
  "room.adminManaged": "Configured once by Admin and reused for every run.",
  "room.adminRuntimeMissing": "Admin must provide a provider, model, prompt, and API key.",
  "room.openAdmin": "Open Admin Settings",
  "event.semanticJudging": "Semantic Judge evaluating"
} as const;

type Phase12Key = keyof typeof english;

const chinese: Record<Phase12Key, string> = {
  "creator.editLabel": "编辑角色卡",
  "creator.editHeading": "修改这个受测角色。",
  "creator.editHelp": "原地更新角色资料与模型配置。既有测试历史和当前 Provider Key 关联会保留。",
  "creator.editKeyPreserved": "现有 API Key 关联会保留。只有需要更换时才从测试房间重新配置。",
  "creator.saveChanges": "保存修改",
  "shelf.admin": "Admin 设置",
  "shelf.filters": "角色库筛选",
  "shelf.search": "搜索",
  "shelf.searchPlaceholder": "名称、角色设定、特质或标签",
  "shelf.subjectFilter": "受测类型",
  "shelf.allSubjects": "全部类型",
  "shelf.tagFilter": "标签",
  "shelf.allTags": "全部标签",
  "shelf.sort": "排序",
  "shelf.newest": "最新优先",
  "shelf.oldest": "最早优先",
  "shelf.nameSort": "名称 A–Z",
  "shelf.edit": "编辑",
  "shelf.emptyTitle": "角色库目前为空。",
  "shelf.emptyHelp": "系统不再自动加入 built-in 角色卡。创建一个真实的 Prompt + Model 角色后即可开始测试。",
  "shelf.noResults": "找不到符合条件的角色卡",
  "shelf.noResultsHelp": "修改搜索文字或筛选条件以显示更多角色卡。",
  "shelf.pagination": "角色库分页",
  "shelf.previous": "上一页",
  "shelf.page": "第 {page} / {pages} 页",
  "shelf.next": "下一页",
  "admin.error": "无法更新 Admin Runtime。",
  "admin.saved": "Admin Runtime 已保存。",
  "admin.label": "Admin Runtime",
  "admin.heading": "配置共用评估 Agent。",
  "admin.help": "Adaptive Tester 与 Semantic Judge 由 Admin 配置一次，之后供所有测试房间复用。非敏感设置保存在 SQLite；生产环境密钥应由 Railway 环境变量提供。",
  "admin.token": "Admin Token",
  "admin.tokenPlaceholder": "X-Echo-Admin Token",
  "admin.tokenHelp": "开发环境默认值为 local-admin。生产环境必须设置 ECHO_MASQUE_ADMIN_TOKEN。",
  "admin.connecting": "检查中…",
  "admin.connect": "打开 Admin 设置",
  "admin.adaptiveTitle": "Adaptive Tester",
  "admin.judgeTitle": "Semantic Judge",
  "admin.enabled": "启用这个 Runtime",
  "admin.systemPrompt": "System Prompt",
  "admin.temperature": "Temperature",
  "admin.maxTurns": "最大轮数",
  "admin.rubricVersion": "Rubric 版本",
  "admin.defaultJudge": "默认 Judge Mode",
  "admin.security": "Adaptive 与 Judge 的原始 Key 不会写入 SQLite、Trial 事件、报告或日志。生产环境请在 Railway 配置 ECHO_MASQUE_ADAPTIVE_API_KEY 与 ECHO_MASQUE_JUDGE_API_KEY。这里输入的 Key 只保留到服务器重启。",
  "admin.save": "保存 Admin Runtime",
  "admin.runtime": "共用 Runtime",
  "admin.ready": "已就绪",
  "admin.missing": "未就绪",
  "admin.apiKey": "进程内存 API Key",
  "admin.apiKeyPlaceholder": "留空以保留现有环境变量或内存 Key",
  "admin.clearMemoryKey": "清除内存 Key",
  "judge.rules": "Rules",
  "judge.semantic": "Semantic",
  "judge.hybrid": "Hybrid",
  "judge.rulesHelp": "快速且可重复",
  "judge.semanticHelp": "独立 LLM Rubric",
  "judge.hybridHelp": "规则 + 语义复核",
  "judge.review": "需要人工复核",
  "room.adminAdaptiveMissing": "Adaptive Tester 尚不可用。请让 Admin 配置并启用共用 Runtime。",
  "room.adminJudgeMissing": "Semantic Judge 尚不可用。请让 Admin 配置并启用共用 Runtime。",
  "room.comparisonUnavailable": "这个 Run 不能用于当前选择的 Regression 比较。",
  "room.judgeMode": "Judge Mode",
  "room.semanticJudge": "Semantic Judge",
  "room.adminManaged": "由 Admin 配置一次，之后每次运行都会复用。",
  "room.adminRuntimeMissing": "Admin 必须提供 Provider、Model、Prompt 与 API Key。",
  "room.openAdmin": "打开 Admin 设置",
  "event.semanticJudging": "Semantic Judge 正在评估"
};

const dictionaries: Record<LanguageCode, Record<Phase12Key, string>> = {
  en: english,
  "zh-CN": chinese
};

function interpolate(template: string, values?: Values): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
  );
}

function isPhase12Key(key: string): key is Phase12Key {
  return Object.prototype.hasOwnProperty.call(english, key);
}

export function useProductI18n() {
  const base = useBaseI18n();
  function t(key: string, values?: Values): string {
    if (isPhase12Key(key)) return interpolate(dictionaries[base.language][key], values);
    return base.t(
      key as Parameters<typeof base.t>[0],
      values as Parameters<typeof base.t>[1]
    );
  }
  return { ...base, t };
}
