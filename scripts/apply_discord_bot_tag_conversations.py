from pathlib import Path
from textwrap import dedent


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise SystemExit(f"Expected snippet not found in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1))


def replace_section(path: str, start: str, end: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text()
    start_index = text.find(start)
    if start_index < 0:
        raise SystemExit(f"Start marker not found in {path}: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise SystemExit(f"End marker not found in {path}: {end!r}")
    target.write_text(text[:start_index] + replacement + text[end_index:])


# Connector configuration.
replace_once(
    "connectors/discord/src/config.ts",
    """  smartParticipationEnabled: boolean;\n  groupAddressAliases: string[];\n}""",
    """  smartParticipationEnabled: boolean;\n  groupAddressAliases: string[];\n  botTagConversationsEnabled: boolean;\n  botTagMaxDepth: number;\n  botTagMaxResponses: number;\n}""",
)
replace_once(
    "connectors/discord/src/config.ts",
    """function boolean(name: string, fallback = false): boolean {\n""",
    """function boundedInteger(\n  name: string,\n  fallback: number,\n  minimum: number,\n  maximum: number\n): number {\n  const value = integer(name, fallback, minimum);\n  if (value > maximum) {\n    throw new Error(`${name} must be less than or equal to ${maximum}.`);\n  }\n  return value;\n}\n\nfunction boolean(name: string, fallback = false): boolean {\n""",
)
replace_once(
    "connectors/discord/src/config.ts",
    """    smartParticipationEnabled: boolean(\"DISCORD_SMART_PARTICIPATION_ENABLED\", false),\n    groupAddressAliases: stringList(\"DISCORD_GROUP_ADDRESS_ALIASES\")\n""",
    """    smartParticipationEnabled: boolean(\"DISCORD_SMART_PARTICIPATION_ENABLED\", false),\n    groupAddressAliases: stringList(\"DISCORD_GROUP_ADDRESS_ALIASES\"),\n    botTagConversationsEnabled: boolean(\n      \"DISCORD_BOT_TAG_CONVERSATIONS_ENABLED\",\n      true\n    ),\n    botTagMaxDepth: boundedInteger(\"DISCORD_BOT_TAG_MAX_DEPTH\", 4, 1, 12),\n    botTagMaxResponses: boundedInteger(\n      \"DISCORD_BOT_TAG_MAX_RESPONSES\",\n      8,\n      1,\n      30\n    )\n""",
)

# Connector and API request contracts.
replace_once(
    "connectors/discord/src/types.ts",
    """  smart_candidate: boolean;\n  recent_messages: DiscordContextMessage[];\n}""",
    """  smart_candidate: boolean;\n  author_is_bot: boolean;\n  available_characters: string[];\n  recent_messages: DiscordContextMessage[];\n}""",
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    """    smart_candidate: bool = False\n    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)\n""",
    """    smart_candidate: bool = False\n    author_is_bot: bool = False\n    available_characters: list[str] = Field(default_factory=list, max_length=30)\n    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)\n""",
)

# Explicit character-to-character tag routing.
replace_once(
    "connectors/discord/src/routing.ts",
    """function withoutNameAlias(value: string, alias: string): string | null {\n  const pattern = new RegExp(\n    `^${escapeRegex(alias)}(?=$|[\\\\s:：,，、.。?？!！\\\\-—–&＆/／+和与與跟及])`,\n    \"iu\"\n  );\n  const trimmed = value.trimStart();\n  const match = trimmed.match(pattern);\n  if (!match) return null;\n  return trimmed.slice(match[0].length);\n}\n""",
    """function withoutNameAlias(\n  value: string,\n  alias: string,\n  requireTag = false\n): string | null {\n  const pattern = new RegExp(\n    `^${escapeRegex(alias)}(?=$|[\\\\s:：,，、.。?？!！\\\\-—–&＆/／+和与與跟及])`,\n    \"iu\"\n  );\n  let trimmed = value.trimStart();\n  if (requireTag) {\n    const tag = trimmed.match(/^[@＠]\\s*/u);\n    if (!tag) return null;\n    trimmed = trimmed.slice(tag[0].length);\n  }\n  const match = trimmed.match(pattern);\n  if (!match) return null;\n  return trimmed.slice(match[0].length);\n}\n""",
)
replace_once(
    "connectors/discord/src/routing.ts",
    """function matchNamePrefix(\n  candidates: DiscordDeployment[],\n  value: string\n): NameMatch | null {\n""",
    """function matchNamePrefix(\n  candidates: DiscordDeployment[],\n  value: string,\n  requireTag = false\n): NameMatch | null {\n""",
)
replace_once(
    "connectors/discord/src/routing.ts",
    """      const remainder = withoutNameAlias(value, alias);\n""",
    """      const remainder = withoutNameAlias(value, alias, requireTag);\n""",
)
replace_once(
    "connectors/discord/src/routing.ts",
    """function namedAudience(\n  candidates: DiscordDeployment[],\n  text: string,\n  options: string[]\n): AudienceResolution | null {\n""",
    """function namedAudience(\n  candidates: DiscordDeployment[],\n  text: string,\n  options: string[],\n  requireTag = false\n): AudienceResolution | null {\n""",
)
for old, new in (
    ("const match = matchNamePrefix(candidates, remaining);", "const match = matchNamePrefix(candidates, remaining, requireTag);"),
    ("const directNext = matchNamePrefix(candidates, afterPunctuation);", "const directNext = matchNamePrefix(candidates, afterPunctuation, requireTag);"),
    ("      matchNamePrefix(candidates, afterConnector)", "      matchNamePrefix(candidates, afterConnector, requireTag)"),
):
    replace_once("connectors/discord/src/routing.ts", old, new)
replace_once(
    "connectors/discord/src/routing.ts",
    """function namedAudience(\n""",
    """function stripTaggedGroupAddress(\n  value: string,\n  additionalAliases: string[]\n): string | null {\n  const trimmed = value.trimStart();\n  const tag = trimmed.match(/^[@＠]\\s*/u);\n  if (!tag) return null;\n  return stripGroupAddress(trimmed.slice(tag[0].length), additionalAliases);\n}\n\nfunction namedAudience(\n""",
)
replace_once(
    "connectors/discord/src/routing.ts",
    """export interface TriggerState {\n""",
    dedent(
        """
        export function resolveBotTagAudience(
          candidates: DiscordDeployment[],
          text: string,
          sourceDeploymentId: string,
          additionalGroupAliases: string[] = []
        ): AudienceResolution {
          const available = candidates.filter(
            (item) => item.deployment_id !== sourceDeploymentId
          );
          const options = [...new Set(available.map(displayName))];
          if (!available.length) {
            return { deployments: [], text: text.trim(), reason: "not_found", options };
          }

          const groupText = stripTaggedGroupAddress(text, additionalGroupAliases);
          if (groupText !== null) {
            return {
              deployments: available,
              text: groupText,
              reason: "selected_all",
              options
            };
          }

          const named = namedAudience(available, text, options, true);
          if (named) return named;
          return {
            deployments: [],
            text: text.trim(),
            reason: "not_found",
            options
          };
        }

        export interface TriggerState {
        """
    ).lstrip(),
)

# Routing tests.
replace_once(
    "connectors/discord/src/routing.test.ts",
    """  resolveAudience,\n  shouldSubmitMessage,\n""",
    """  resolveAudience,\n  resolveBotTagAudience,\n  shouldSubmitMessage,\n""",
)
replace_once(
    "connectors/discord/src/routing.test.ts",
    """  it(\"applies explicit trigger modes\", () => {\n""",
    dedent(
        """
          it("routes explicit character tags while ignoring self tags", () => {
            const ann = deployment("mention_and_reply", "", "安 · Ann");
            const ning = deployment("mention_and_reply", "", "宁 · Ning");
            const zhi = deployment("mention_and_reply", "", "织 · Zhi");

            const single = resolveBotTagAudience(
              [ann, ning, zhi],
              "@宁，你怎么看？",
              ann.deployment_id
            );
            expect(single.reason).toBe("selected_alias");
            expect(single.deployments.map((item) => item.deployment_id)).toEqual([
              ning.deployment_id
            ]);
            expect(single.text).toBe("你怎么看？");

            const multiple = resolveBotTagAudience(
              [ann, ning, zhi],
              "@Ning and @Zhi, can you check this?",
              ann.deployment_id
            );
            expect(multiple.reason).toBe("selected_multiple");
            expect(multiple.deployments.map((item) => item.deployment_id)).toEqual([
              ning.deployment_id,
              zhi.deployment_id
            ]);
            expect(multiple.text).toBe("can you check this?");

            const self = resolveBotTagAudience(
              [ann, ning],
              "@Ann, I should not trigger myself.",
              ann.deployment_id
            );
            expect(self.deployments).toEqual([]);
            expect(self.reason).toBe("not_found");
          });

          it("routes tagged group aliases to every other character", () => {
            const ann = deployment("mention_and_reply", "", "Ann");
            const ning = deployment("mention_and_reply", "", "宁 · Ning");
            const zhi = deployment("mention_and_reply", "", "织 · Zhi");

            const group = resolveBotTagAudience(
              [ann, ning, zhi],
              "@你们，这件事怎么看？",
              ann.deployment_id
            );
            expect(group.reason).toBe("selected_all");
            expect(group.deployments.map((item) => item.deployment_id)).toEqual([
              ning.deployment_id,
              zhi.deployment_id
            ]);
            expect(group.text).toBe("这件事怎么看？");

            const custom = resolveBotTagAudience(
              [ann, ning, zhi],
              "@companions, hello",
              ann.deployment_id,
              ["companions"]
            );
            expect(custom.deployments).toHaveLength(2);
            expect(custom.text).toBe("hello");
          });

          it("does not treat untagged character names as bot conversation triggers", () => {
            const ann = deployment("mention_and_reply", "", "Ann");
            const ning = deployment("mention_and_reply", "", "Ning");
            const result = resolveBotTagAudience(
              [ann, ning],
              "Ning, this is ordinary narration.",
              ann.deployment_id
            );
            expect(result.deployments).toEqual([]);
          });

          it("applies explicit trigger modes", () => {
        """
    ).lstrip(),
)

# Runtime prompt and participant metadata.
runtime_path = Path("src/echo_masque/connector_runtime.py")
runtime_text = runtime_path.read_text()
runtime_marker = "    @staticmethod\n    def _social_prompt(\n"
runtime_index = runtime_text.find(runtime_marker)
if runtime_index < 0:
    raise SystemExit("Discord social prompt method was not found.")
runtime_method = dedent(
    '''
        @staticmethod
        def _social_prompt(
            *,
            character_name: str,
            payload: DiscordInboundMessage,
        ) -> str:
            messages = list(payload.recent_messages)
            if not any(item.message_id == payload.message_id for item in messages):
                messages.append(
                    DiscordContextMessage(
                        message_id=payload.message_id,
                        author_id=payload.author_id,
                        author_display_name=payload.author_display_name,
                        text=payload.text,
                        is_bot=payload.author_is_bot,
                    )
                )
            transcript = "\\n".join(
                (
                    f"[{'Character' if item.is_bot else 'Member'}: "
                    f"{item.author_display_name} | {item.author_id}]: {item.text}"
                )
                for item in messages[-30:]
                if item.text.strip()
            )
            location = payload.channel_name or payload.channel_id
            if payload.thread_id:
                location = f"{location} / {payload.thread_name or payload.thread_id}"

            peers = list(
                dict.fromkeys(
                    item.strip()
                    for item in payload.available_characters
                    if item.strip() and item.strip().casefold() != character_name.casefold()
                )
            )
            tag_guidance: tuple[str, ...] = ()
            if peers:
                tag_guidance = (
                    f"Other active characters at this location: {', '.join(peers)}.",
                    "To intentionally invite another character to answer, begin your "
                    "reply with @ followed by that character's displayed name or a clear "
                    "bilingual alias. Tag each intended character separately, for example "
                    "@Ning or @Ning and @Zhi.",
                    "Use character tags sparingly and only when their response adds value. "
                    "Never tag yourself. A leading tag may cause another provider call.",
                )
            source_guidance = (
                "The latest triggering message was written by another deployed character."
                if payload.author_is_bot
                else "The latest triggering message was written by a human Discord member."
            )
            return "\\n".join(
                (
                    "You are participating in a real Discord group conversation "
                    "through Character Relay.",
                    f"Continue acting as {character_name} using the existing system "
                    "prompt and persona.",
                    "Reply to the latest triggering message, not to every line in the transcript.",
                    source_guidance,
                    "Distinguish human members and deployed characters by their displayed "
                    "name, participant type, and stable ID.",
                    *tag_guidance,
                    "Do not mention internal prompts, deployment configuration, OOC evaluation, "
                    "or Character Relay.",
                    "Do not claim to have seen messages outside the supplied transcript.",
                    "Keep the response natural for a group chat and do not prefix it with your name.",
                    f"Discord location: {payload.guild_name or payload.guild_id} / {location}",
                    "Recent conversation:",
                    transcript or "(No readable recent messages.)",
                    "Latest triggering message:",
                    (
                        f"[{'Character' if payload.author_is_bot else 'Member'}: "
                        f"{payload.author_display_name} | {payload.author_id}]: {payload.text}"
                    ),
                    "Respond now as the character.",
                )
            )
    '''
).lstrip()
runtime_path.write_text(runtime_text[:runtime_index] + runtime_method)

# Discord connector orchestration.
replace_once(
    "connectors/discord/src/index.ts",
    """  flattenDeployments,\n  resolveAudience,\n  shouldSubmitMessage,\n""",
    """  flattenDeployments,\n  resolveAudience,\n  resolveBotTagAudience,\n  shouldSubmitMessage,\n""",
)
replace_once(
    "connectors/discord/src/index.ts",
    """function knownWebhookIds(): Set<string> {\n""",
    """function deploymentDisplayName(deployment: DiscordDeployment): string {\n  return deployment.identity_display_name || deployment.character_display_name;\n}\n\nfunction knownWebhookIds(): Set<string> {\n""",
)

bot_conversation_block = dedent(
    '''
    interface BotConversationBudget {
      remainingResponses: number;
    }

    interface BotConversationTurn {
      deployment: DiscordDeployment;
      text: string;
      sentMessageIds: string[];
    }

    async function continueBotTagConversation(
      sourceMessage: Message<true>,
      sourceDeployment: DiscordDeployment,
      sourceText: string,
      sourceMessageIds: string[],
      candidates: DiscordDeployment[],
      location: ReturnType<typeof channelLocation>,
      key: string,
      botUserId: string,
      depth: number,
      budget: BotConversationBudget
    ): Promise<void> {
      if (
        !config.botTagConversationsEnabled ||
        depth >= config.botTagMaxDepth ||
        budget.remainingResponses <= 0
      ) {
        return;
      }

      const audience = resolveBotTagAudience(
        candidates,
        sourceText,
        sourceDeployment.deployment_id,
        config.groupAddressAliases
      );
      if (!audience.deployments.length) return;

      const eligible = audience.deployments.filter((deployment) =>
        shouldSubmitMessage(
          deployment,
          {
            mentionedBot: true,
            repliedToBot: false,
            hasReadableText: Boolean(audience.text || sourceText)
          },
          config.smartParticipationEnabled
        )
      );
      if (!eligible.length) return;

      const sourceDisplayName = deploymentDisplayName(sourceDeployment);
      const sourceDiscordMessageId = sourceMessageIds[0] ?? sourceMessage.id;
      const nextTurns: BotConversationTurn[] = [];

      for (const [responseIndex, baseDeployment] of eligible.entries()) {
        if (budget.remainingResponses <= 0) break;
        budget.remainingResponses -= 1;
        const deployment = resolveDeploymentLocation(baseDeployment, location);
        await sourceMessage.channel.sendTyping();
        const reply = await relay.processMessage({
          deployment_id: deployment.deployment_id,
          message_id: sourceDiscordMessageId,
          guild_id: sourceMessage.guildId,
          guild_name: sourceMessage.guild.name,
          channel_id: location.channelId,
          channel_name: location.channelName,
          category_id: location.categoryId,
          thread_id: location.threadId,
          thread_name: location.threadName,
          author_id: `character:${sourceDeployment.character_card_id}`,
          author_display_name: sourceDisplayName,
          text:
            audience.text ||
            `${sourceDisplayName} tagged this character without additional readable text.`,
          mentioned_bot: true,
          replied_to_bot: false,
          smart_candidate: false,
          author_is_bot: true,
          available_characters: candidates
            .filter((item) => item.deployment_id !== deployment.deployment_id)
            .map(deploymentDisplayName),
          recent_messages: context.get(key)
        });
        if (reply.action !== "reply" || !reply.text) continue;

        const sentMessageIds = await sendCharacterReply(
          sourceMessage,
          deployment,
          reply.text,
          botUserId
        );
        await rememberSentMessages(deployment, sentMessageIds, sourceMessage.guildId);
        context.push(key, {
          message_id: sentMessageIds[0] ?? `relay-bot-tag-${Date.now()}`,
          author_id: `character:${deployment.character_card_id}`,
          author_display_name: deploymentDisplayName(deployment),
          text: reply.text,
          created_at: new Date().toISOString(),
          is_bot: true
        });
        nextTurns.push({ deployment, text: reply.text, sentMessageIds });
        log("Character tag reply sent to Discord.", {
          deploymentId: deployment.deployment_id,
          characterId: deployment.character_card_id,
          sourceDeploymentId: sourceDeployment.deployment_id,
          tagDepth: depth + 1,
          responseIndex: responseIndex + 1,
          responseCount: eligible.length,
          remainingResponseBudget: budget.remainingResponses,
          guildId: sourceMessage.guildId,
          channelId: location.channelId,
          threadId: location.threadId || null,
          sourceMessageId: sourceDiscordMessageId,
          sentMessageIds,
          latencyMs: reply.latency_ms ?? null
        });
      }

      for (const turn of nextTurns) {
        await continueBotTagConversation(
          sourceMessage,
          turn.deployment,
          turn.text,
          turn.sentMessageIds,
          candidates,
          location,
          key,
          botUserId,
          depth + 1,
          budget
        );
      }
    }

    '''
).lstrip()
replace_once(
    "connectors/discord/src/index.ts",
    """async function processMessage(message: Message): Promise<void> {\n""",
    bot_conversation_block + "async function processMessage(message: Message): Promise<void> {\n",
)

process_message = dedent(
    '''
    async function processMessage(message: Message): Promise<void> {
      const botUser = client.user;
      if (!message.inGuild() || message.author.bot || !botUser) return;
      if (processedMessages.has(message.id)) return;
      processedMessages.set(message.id, Date.now());

      const guildMessage = message;
      const location = channelLocation(guildMessage);
      if (!location.channelId) return;
      const candidates = deploymentsFor(
        deployments,
        location.channelId,
        location.threadId,
        guildMessage.guildId,
        location.categoryId
      );
      if (!candidates.length) return;

      const originalText = normalizedText(guildMessage, botUser.id);
      const mentionedBot = guildMessage.mentions.users.has(botUser.id);
      const key = destinationKey(location.channelId, location.threadId);
      const authorDisplayName =
        guildMessage.member?.displayName ??
        guildMessage.author.globalName ??
        guildMessage.author.username;
      const contextMessage: DiscordContextMessage = {
        message_id: guildMessage.id,
        author_id: guildMessage.author.id,
        author_display_name: authorDisplayName,
        text: originalText,
        created_at: guildMessage.createdAt.toISOString(),
        is_bot: false
      };

      enqueue(key, async () => {
        context.push(key, contextMessage);

        const replyTarget = await resolveReplyTarget(
          guildMessage,
          candidates,
          botUser.id,
          location.channelId,
          location.threadId
        );
        const audience = resolveAudience(
          candidates,
          originalText,
          replyTarget.deploymentId,
          config.groupAddressAliases
        );
        if (!audience.deployments.length) {
          if (
            audience.reason === "ambiguous" &&
            (mentionedBot || replyTarget.characterMessage)
          ) {
            await sendSelectionHelp(guildMessage, audience.options);
          }
          return;
        }

        const isReplyToCharacter = audience.reason === "selected_reply";
        const eligibleDeployments = audience.deployments.filter((deployment) =>
          shouldSubmitMessage(
            deployment,
            {
              mentionedBot,
              repliedToBot: isReplyToCharacter,
              hasReadableText: Boolean(audience.text || originalText)
            },
            config.smartParticipationEnabled
          )
        );
        if (!eligibleDeployments.length) return;

        const addressedToMultiple = audience.deployments.length > 1;
        const botConversationBudget: BotConversationBudget = {
          remainingResponses: config.botTagMaxResponses
        };
        for (const [responseIndex, baseDeployment] of eligibleDeployments.entries()) {
          const deployment = resolveDeploymentLocation(baseDeployment, location);
          await guildMessage.channel.sendTyping();
          const reply = await relay.processMessage({
            deployment_id: deployment.deployment_id,
            message_id: guildMessage.id,
            guild_id: guildMessage.guildId,
            guild_name: guildMessage.guild.name,
            channel_id: location.channelId,
            channel_name: location.channelName,
            category_id: location.categoryId,
            thread_id: location.threadId,
            thread_name: location.threadName,
            author_id: guildMessage.author.id,
            author_display_name: authorDisplayName,
            text:
              (addressedToMultiple ? originalText : audience.text) ||
              "The user addressed the character without additional readable text.",
            mentioned_bot: mentionedBot,
            replied_to_bot: isReplyToCharacter,
            smart_candidate:
              deployment.participation_mode === "smart" &&
              config.smartParticipationEnabled,
            author_is_bot: false,
            available_characters: candidates
              .filter((item) => item.deployment_id !== deployment.deployment_id)
              .map(deploymentDisplayName),
            recent_messages: context.get(key)
          });
          if (reply.action !== "reply" || !reply.text) continue;

          const sentMessageIds = await sendCharacterReply(
            guildMessage,
            deployment,
            reply.text,
            botUser.id
          );
          await rememberSentMessages(
            deployment,
            sentMessageIds,
            guildMessage.guildId
          );
          context.push(key, {
            message_id: sentMessageIds[0] ?? `relay-${Date.now()}`,
            author_id: `character:${deployment.character_card_id}`,
            author_display_name: deploymentDisplayName(deployment),
            text: reply.text,
            created_at: new Date().toISOString(),
            is_bot: true
          });
          log("Character reply sent to Discord.", {
            deploymentId: reply.deployment_id,
            characterId: deployment.character_card_id,
            audienceReason: audience.reason,
            audienceSize: audience.deployments.length,
            responseIndex: responseIndex + 1,
            responseCount: eligibleDeployments.length,
            identityMode: deployment.identity_mode,
            webhookStatus: deployment.webhook_status,
            serverProfileId: deployment.server_profile_id || null,
            guildId: guildMessage.guildId,
            channelId: location.channelId,
            categoryId: location.categoryId || null,
            threadId: location.threadId || null,
            sourceMessageId: guildMessage.id,
            sentMessageIds,
            latencyMs: reply.latency_ms ?? null
          });
          await continueBotTagConversation(
            guildMessage,
            deployment,
            reply.text,
            sentMessageIds,
            candidates,
            location,
            key,
            botUser.id,
            0,
            botConversationBudget
          );
        }
      });
    }

    '''
).lstrip()
replace_section(
    "connectors/discord/src/index.ts",
    "async function processMessage(message: Message): Promise<void> {\n",
    "const healthServer = createServer((request, response) => {\n",
    process_message,
)
replace_once(
    "connectors/discord/src/index.ts",
    """      smart_participation_enabled: config.smartParticipationEnabled,\n      custom_group_address_aliases: config.groupAddressAliases.length,\n""",
    """      smart_participation_enabled: config.smartParticipationEnabled,\n      bot_tag_conversations_enabled: config.botTagConversationsEnabled,\n      bot_tag_max_depth: config.botTagMaxDepth,\n      bot_tag_max_responses: config.botTagMaxResponses,\n      custom_group_address_aliases: config.groupAddressAliases.length,\n""",
)

# Documentation and deployment defaults.
replace_once(
    "connectors/discord/.env.example",
    "DISCORD_GROUP_ADDRESS_ALIASES=",
    "DISCORD_GROUP_ADDRESS_ALIASES=\nDISCORD_BOT_TAG_CONVERSATIONS_ENABLED=true\nDISCORD_BOT_TAG_MAX_DEPTH=4\nDISCORD_BOT_TAG_MAX_RESPONSES=8",
)
replace_once(
    "connectors/discord/README.md",
    """- Explicit group addresses route to every character in the destination.\n""",
    """- Explicit group addresses route to every character in the destination.\n- Character replies can explicitly Tag other deployed characters and continue a bounded Bot-to-Bot conversation.\n""",
)
replace_once(
    "connectors/discord/README.md",
    """## Context behavior\n""",
    dedent(
        """
        ## Character-to-character Tag conversations

        A deployed character may intentionally invite another deployed character to answer by
        beginning its generated reply with an explicit textual Tag:

        ```text
        @Ning，你怎么看？
        @宁 and @Zhi, can you check this?
        @你们，这件事有什么遗漏？
        ```

        Character Relay treats only a **leading** `@CharacterName` or `@group` expression as a
        Bot-to-Bot trigger. Ordinary narration that merely contains another character's name does
        not trigger a Provider call. A character cannot trigger itself.

        Bot Tag conversations are bounded per human trigger. Defaults are:

        ```text
        DISCORD_BOT_TAG_CONVERSATIONS_ENABLED=true
        DISCORD_BOT_TAG_MAX_DEPTH=4
        DISCORD_BOT_TAG_MAX_RESPONSES=8
        ```

        `MAX_DEPTH` limits chained Tag hops. `MAX_RESPONSES` is a shared budget across all branches
        created by the original human message, preventing exponential group loops. Participation
        modes still apply: an internal Tag counts as a Mention, so a `reply_only` deployment remains
        silent unless its mode is changed.

        The runtime prompt lists other active characters at the current destination and explains the
        Tag contract, while instructing characters to use it sparingly because every successful Tag
        may create another Provider call.

        ## Context behavior
        """
    ).lstrip(),
)
replace_once(
    "connectors/discord/README.md",
    """DISCORD_GROUP_ADDRESS_ALIASES=\n""",
    """DISCORD_GROUP_ADDRESS_ALIASES=\nDISCORD_BOT_TAG_CONVERSATIONS_ENABLED=true\nDISCORD_BOT_TAG_MAX_DEPTH=4\nDISCORD_BOT_TAG_MAX_RESPONSES=8\n""",
)
replace_once(
    "connectors/discord/README.md",
    """The worker exposes `/health` and reports active deployments, destinations, multi-character destinations, cached reply routes, webhook readiness, custom group-alias count, the last deployment refresh, and the last Connector error.\n""",
    """The worker exposes `/health` and reports active deployments, destinations, multi-character destinations, cached reply routes, webhook readiness, Bot Tag limits, custom group-alias count, the last deployment refresh, and the last Connector error.\n""",
)
replace_once(
    "connectors/discord/README.md",
    """Smart Participation remains experimental. Multi-character autonomous participation is not enabled by this Mention + Reply work.\n""",
    """Smart Participation remains experimental. Bot Tag conversations are explicit and bounded; they do not enable unrestricted autonomous channel participation.\n""",
)

# Focused runtime prompt regression coverage.
Path("tests/test_discord_bot_tag_runtime.py").write_text(
    dedent(
        '''
        from echo_masque.api.connector_schemas import (
            DiscordContextMessage,
            DiscordInboundMessage,
        )
        from echo_masque.connector_runtime import DiscordConnectorRuntime


        def payload(*, author_is_bot: bool) -> DiscordInboundMessage:
            return DiscordInboundMessage(
                connection_id="connection-1",
                deployment_id="deployment-ning",
                message_id="message-1",
                guild_id="guild-1",
                guild_name="Companion Guild",
                channel_id="channel-1",
                channel_name="companions",
                author_id="character:ann" if author_is_bot else "user-1",
                author_display_name="Ann" if author_is_bot else "Juen",
                text="你怎么看？",
                mentioned_bot=True,
                author_is_bot=author_is_bot,
                available_characters=["Ann", "织 · Zhi"],
                recent_messages=[
                    DiscordContextMessage(
                        message_id="context-1",
                        author_id="character:ann",
                        author_display_name="Ann",
                        text="@宁，你怎么看？",
                        is_bot=True,
                    )
                ],
            )


        def test_social_prompt_exposes_bounded_character_tag_contract() -> None:
            prompt = DiscordConnectorRuntime._social_prompt(
                character_name="宁 · Ning",
                payload=payload(author_is_bot=True),
            )

            assert "Other active characters at this location: Ann, 织 · Zhi." in prompt
            assert "begin your reply with @" in prompt
            assert "Use character tags sparingly" in prompt
            assert "Never tag yourself" in prompt
            assert "another deployed character" in prompt
            assert "[Character: Ann | character:ann]" in prompt


        def test_social_prompt_distinguishes_human_trigger_from_character_context() -> None:
            prompt = DiscordConnectorRuntime._social_prompt(
                character_name="宁 · Ning",
                payload=payload(author_is_bot=False),
            )

            assert "human Discord member" in prompt
            assert "[Member: Juen | user-1]" in prompt
        '''
    ).lstrip()
)

Path(__file__).unlink()
