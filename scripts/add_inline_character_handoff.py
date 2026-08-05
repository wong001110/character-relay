from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


routing = Path("connectors/discord/src/routing.ts")
text = routing.read_text(encoding="utf-8")
anchor = '''export function resolveBotTagAudience(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string,
  additionalGroupAliases: string[] = []
): AudienceResolution {
  return normalizeBotTagReply(
    candidates,
    text,
    sourceDeploymentId,
    additionalGroupAliases
  ).audience;
}
'''
replacement = r'''interface InlineCharacterTagMatch {
  deployment: DiscordDeployment;
  alias: string;
  start: number;
  end: number;
}

const INLINE_TAG_LEFT_BOUNDARY =
  String.raw`(^|[\s:：,，、.。?？!！;；\-—–&＆/／+(（\[【])`;
const INLINE_TAG_RIGHT_BOUNDARY =
  String.raw`(?=$|[\s:：,，、.。?？!！;；\-—–&＆/／+)）\]】])`;
const SHARED_BOT_TAG_NAME =
  String.raw`[^\s:：,，、.。?？!！;；\-—–&＆/／+()（）\[\]【】<>]+`;

function inlineTagPosition(
  value: string,
  alias: string
): { start: number; end: number } | null {
  const escapedAlias = escapeRegex(alias);
  const direct = new RegExp(
    `${INLINE_TAG_LEFT_BOUNDARY}[@＠]\\s*${escapedAlias}${INLINE_TAG_RIGHT_BOUNDARY}`,
    "iu"
  );
  const sharedBot = new RegExp(
    `${INLINE_TAG_LEFT_BOUNDARY}(?:<@!?\\d+>|[@＠]${SHARED_BOT_TAG_NAME})` +
      `\\s+${escapedAlias}${INLINE_TAG_RIGHT_BOUNDARY}`,
    "iu"
  );
  const matches = [direct.exec(value), sharedBot.exec(value)]
    .filter((item): item is RegExpExecArray => item !== null)
    .map((item) => ({
      start: item.index + (item[1]?.length ?? 0),
      end: item.index + item[0].length
    }))
    .sort((left, right) => left.start - right.start || right.end - left.end);
  return matches[0] ?? null;
}

function inlineTaggedAudience(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string
): AudienceResolution | null {
  const options = [
    ...new Set(
      candidates
        .filter((item) => item.deployment_id !== sourceDeploymentId)
        .map(displayName)
    )
  ];
  const matches: InlineCharacterTagMatch[] = [];
  for (const deployment of candidates) {
    if (deployment.deployment_id === sourceDeploymentId) continue;
    for (const alias of aliases(deployment)) {
      const position = inlineTagPosition(text, alias);
      if (!position) continue;
      matches.push({ deployment, alias, ...position });
    }
  }
  if (!matches.length) return null;

  matches.sort(
    (left, right) =>
      left.start - right.start ||
      right.end - left.end ||
      right.alias.length - left.alias.length
  );
  const selected = new Map<string, InlineCharacterTagMatch>();
  for (const match of matches) {
    if (!selected.has(match.deployment.deployment_id)) {
      selected.set(match.deployment.deployment_id, match);
    }
  }
  const uniqueMatches = [...selected.values()].sort(
    (left, right) => left.start - right.start
  );
  const deployments = uniqueMatches.map((item) => item.deployment);
  const firstTagEnd = uniqueMatches[0]?.end ?? text.length;
  const remainder = stripLeadingPunctuation(text.slice(firstTagEnd));
  return {
    deployments,
    text: remainder || text.trim(),
    reason: deployments.length > 1 ? "selected_multiple" : "selected_alias",
    options
  };
}

export function resolveBotTagAudience(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string,
  additionalGroupAliases: string[] = []
): AudienceResolution {
  const leading = normalizeBotTagReply(
    candidates,
    text,
    sourceDeploymentId,
    additionalGroupAliases
  ).audience;
  if (leading.reason !== "not_found") return leading;
  return inlineTaggedAudience(candidates, text, sourceDeploymentId) ?? leading;
}
'''
if anchor not in text:
    raise SystemExit("Routing handoff anchor not found")
routing.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")


tests = Path("connectors/discord/src/routing.test.ts")
text = tests.read_text(encoding="utf-8")
test_anchor = '''it("does not treat untagged character names as bot conversation triggers", () => {
'''
test_block = r'''it("routes character tags that appear naturally inside a sentence", () => {
  const lili = deployment("mention_and_reply", "", "莉莉 · Lili");
  const mengmeng = deployment("mention_and_reply", "", "梦梦 · Mengmeng", {
    address_aliases: ["梦梦", "Mengmeng"]
  });

  const direct = resolveBotTagAudience(
    [lili, mengmeng],
    "你这个想法听起来很不错，@梦梦，你要不要试试把这些功能加进去？",
    lili.deployment_id
  );
  expect(direct.deployments.map((item) => item.deployment_id)).toEqual([
    mengmeng.deployment_id
  ]);
  expect(direct.text).toBe("你要不要试试把这些功能加进去？");

  const sharedBotName = resolveBotTagAudience(
    [lili, mengmeng],
    "这个方向可行，@CharacterRelayBot 梦梦，你怎么看？",
    lili.deployment_id
  );
  expect(sharedBotName.deployments[0]?.deployment_id).toBe(mengmeng.deployment_id);
  expect(sharedBotName.text).toBe("你怎么看？");

  const rawDiscordMention = resolveBotTagAudience(
    [lili, mengmeng],
    "我先整理方案，<@123456789012345678> 梦梦，接下来交给你。",
    lili.deployment_id
  );
  expect(rawDiscordMention.deployments[0]?.deployment_id).toBe(
    mengmeng.deployment_id
  );
  expect(rawDiscordMention.text).toBe("接下来交给你。");
});

it("routes multiple inline character tags once and still ignores inline self tags", () => {
  const ann = deployment("mention_and_reply", "", "安 · Ann");
  const ning = deployment("mention_and_reply", "", "宁 · Ning");
  const zhi = deployment("mention_and_reply", "", "织 · Zhi");

  const multiple = resolveBotTagAudience(
    [ann, ning, zhi],
    "我先给结论，@宁 负责复核，@织 负责整理。",
    ann.deployment_id
  );
  expect(multiple.deployments.map((item) => item.deployment_id)).toEqual([
    ning.deployment_id,
    zhi.deployment_id
  ]);

  const selfOnly = resolveBotTagAudience(
    [ann, ning],
    "这部分由 @Ann 我自己继续处理。",
    ann.deployment_id
  );
  expect(selfOnly.deployments).toEqual([]);
  expect(selfOnly.reason).toBe("not_found");
});

'''
if test_anchor not in text:
    raise SystemExit("Routing test anchor not found")
tests.write_text(text.replace(test_anchor, test_block + test_anchor, 1), encoding="utf-8")


runtime = Path("src/echo_masque/connector_runtime.py")
text = runtime.read_text(encoding="utf-8")
old_guidance = '''                "To intentionally invite another character to answer, begin your "
                "reply with @ followed by one of the listed character Tags. Tag each "
                f"intended character separately, for example {example}.",
                "The examples name other active characters, never you. Use character "
                "tags sparingly and only when their response adds value. Never tag "
                "yourself. A leading tag may cause another provider call.",
'''
new_guidance = '''                "To intentionally invite another character to answer, you may begin your reply with @ "
                "followed by one of the listed character Tags, or place the same Tag "
                "naturally within a sentence. Tag each intended character separately, "
                f"for example {example}.",
                "The examples name other active characters, never you. Use character "
                "tags sparingly and only when their response adds value. Never tag "
                "yourself. A recognized character Tag may cause another provider call.",
'''
if old_guidance not in text:
    raise SystemExit("Runtime tag guidance anchor not found")
runtime.write_text(text.replace(old_guidance, new_guidance, 1), encoding="utf-8")
