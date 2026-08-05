from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_before(path: str, marker: str, addition: str) -> None:
    replace_once(path, marker, addition + marker)


# ---------------------------------------------------------------------------
# Persist explicit per-deployment address aliases without altering old tables.
# ---------------------------------------------------------------------------
append_before(
    "src/echo_masque/persistence/discord_identity_models.py",
    "\n\nclass DiscordWebhookBindingRecord(Base):",
    '''\n\nclass DeploymentMessageAliasRecord(Base):
    """Explicit names that may address one deployed character."""

    __tablename__ = "deployment_message_aliases"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
''',
)

replace_once(
    "src/echo_masque/persistence/__init__.py",
    '''from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
    DiscordMessageRouteRecord,
    DiscordWebhookBindingRecord,
)''',
    '''from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageAliasRecord,
    DeploymentMessageIdentityRecord,
    DiscordMessageRouteRecord,
    DiscordWebhookBindingRecord,
)''',
)
replace_once(
    "src/echo_masque/persistence/__init__.py",
    '    "DeploymentMessageIdentityRecord",\n',
    '    "DeploymentMessageAliasRecord",\n    "DeploymentMessageIdentityRecord",\n',
)

replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
    DiscordMessageRouteRecord,
    DiscordWebhookBindingRecord,
)''',
    '''from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageAliasRecord,
    DeploymentMessageIdentityRecord,
    DiscordMessageRouteRecord,
    DiscordWebhookBindingRecord,
)''',
)
append_before(
    "src/echo_masque/persistence/discord_identity_repository.py",
    "\n\ndef _matches_destination(",
    '''\n\ndef _decode_aliases(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, str) and item.strip()]


def _normalize_aliases(values: list[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        alias = value.strip()[:80]
        normalized = alias.casefold()
        if not alias or normalized in seen:
            continue
        seen.add(normalized)
        aliases.append(alias)
        if len(aliases) >= 20:
            break
    return aliases
''',
)
append_before(
    "src/echo_masque/persistence/discord_identity_repository.py",
    "\n    def upsert_identity(\n",
    '''\n    def get_address_aliases(self, deployment_id: str, owner_id: str) -> list[str]:
        with self.database.session() as session:
            record = session.get(DeploymentMessageAliasRecord, deployment_id)
            if record is None or record.owner_id != owner_id:
                return []
            return _decode_aliases(record.aliases_json)
''',
)
replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''        mode: str,
        display_name: str,
        avatar_url: str,
    ) -> DeploymentMessageIdentityRecord:''',
    '''        mode: str,
        display_name: str,
        avatar_url: str,
        address_aliases: list[str] | None = None,
    ) -> DeploymentMessageIdentityRecord:''',
)
replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''                elif record.webhook_status == "not_required":
                    record.webhook_status = "pending"
            session.commit()''',
    '''                elif record.webhook_status == "not_required":
                    record.webhook_status = "pending"
            if address_aliases is not None:
                aliases = _normalize_aliases(address_aliases)
                alias_record = session.get(DeploymentMessageAliasRecord, deployment_id)
                if aliases:
                    if alias_record is None:
                        alias_record = DeploymentMessageAliasRecord(
                            deployment_id=deployment_id,
                            owner_id=owner_id,
                            aliases_json=json.dumps(aliases, ensure_ascii=False),
                        )
                        session.add(alias_record)
                    else:
                        alias_record.aliases_json = json.dumps(
                            aliases,
                            ensure_ascii=False,
                        )
                elif alias_record is not None:
                    session.delete(alias_record)
            session.commit()''',
)
replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''            session.execute(
                delete(DiscordMessageRouteRecord).where(
                    DiscordMessageRouteRecord.owner_id == owner_id,
                    DiscordMessageRouteRecord.deployment_id == deployment_id,
                )
            )
            session.delete(record)''',
    '''            session.execute(
                delete(DiscordMessageRouteRecord).where(
                    DiscordMessageRouteRecord.owner_id == owner_id,
                    DiscordMessageRouteRecord.deployment_id == deployment_id,
                )
            )
            session.execute(
                delete(DeploymentMessageAliasRecord).where(
                    DeploymentMessageAliasRecord.owner_id == owner_id,
                    DeploymentMessageAliasRecord.deployment_id == deployment_id,
                )
            )
            session.delete(record)''',
)
replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''            identity_result = session.execute(
                delete(DeploymentMessageIdentityRecord).where(
                    DeploymentMessageIdentityRecord.owner_id == owner_id
                )
            )
            binding_result = session.execute(''',
    '''            identity_result = session.execute(
                delete(DeploymentMessageIdentityRecord).where(
                    DeploymentMessageIdentityRecord.owner_id == owner_id
                )
            )
            alias_result = session.execute(
                delete(DeploymentMessageAliasRecord).where(
                    DeploymentMessageAliasRecord.owner_id == owner_id
                )
            )
            binding_result = session.execute(''',
)
replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''            "deployment_identities": int(
                getattr(identity_result, "rowcount", 0) or 0
            ),
            "discord_webhooks":''',
    '''            "deployment_identities": int(
                getattr(identity_result, "rowcount", 0) or 0
            ),
            "deployment_aliases": int(getattr(alias_result, "rowcount", 0) or 0),
            "discord_webhooks":''',
)
replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''            identity_result = session.execute(
                update(DeploymentMessageIdentityRecord)
                .where(DeploymentMessageIdentityRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            binding_result = session.execute(''',
    '''            identity_result = session.execute(
                update(DeploymentMessageIdentityRecord)
                .where(DeploymentMessageIdentityRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            alias_result = session.execute(
                update(DeploymentMessageAliasRecord)
                .where(DeploymentMessageAliasRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            binding_result = session.execute(''',
)
# The same return block occurs in delete_owner and claim_owner; replace the remaining one.
replace_once(
    "src/echo_masque/persistence/discord_identity_repository.py",
    '''            "deployment_identities": int(
                getattr(identity_result, "rowcount", 0) or 0
            ),
            "discord_webhooks":''',
    '''            "deployment_identities": int(
                getattr(identity_result, "rowcount", 0) or 0
            ),
            "deployment_aliases": int(getattr(alias_result, "rowcount", 0) or 0),
            "discord_webhooks":''',
)

# ---------------------------------------------------------------------------
# Owner API and connector payloads expose the aliases.
# ---------------------------------------------------------------------------
replace_once(
    "src/echo_masque/api/discord_identity_schemas.py",
    '''class DeploymentMessageIdentityUpdate(BaseModel):
    mode: IdentityMode = "webhook"
    display_name: str = Field(min_length=1, max_length=80)
    avatar_url: HttpUrl | None = None''',
    '''class DeploymentMessageIdentityUpdate(BaseModel):
    mode: IdentityMode = "webhook"
    display_name: str = Field(min_length=1, max_length=80)
    avatar_url: HttpUrl | None = None
    address_aliases: list[str] = Field(default_factory=list, max_length=20)''',
)
replace_once(
    "src/echo_masque/api/discord_identity_schemas.py",
    '''    display_name: str
    avatar_url: str
    webhook_status: WebhookStatus''',
    '''    display_name: str
    avatar_url: str
    address_aliases: list[str] = Field(default_factory=list)
    webhook_status: WebhookStatus''',
)
replace_once(
    "src/echo_masque/api/discord_identity_schemas.py",
    '''        record: DeploymentMessageIdentityRecord,
    ) -> "DeploymentMessageIdentityView":''',
    '''        record: DeploymentMessageIdentityRecord,
        *,
        address_aliases: list[str] | None = None,
    ) -> "DeploymentMessageIdentityView":''',
)
replace_once(
    "src/echo_masque/api/discord_identity_schemas.py",
    '''            display_name=record.display_name,
            avatar_url=record.avatar_url,
            webhook_status=''',
    '''            display_name=record.display_name,
            avatar_url=record.avatar_url,
            address_aliases=address_aliases or [],
            webhook_status=''',
)

replace_once(
    "src/echo_masque/api/routes/discord_identities.py",
    '''    return [
        DeploymentMessageIdentityView.from_record(item)
        for item in identity_repository(request).list_identities(user.id)
    ]''',
    '''    repository = identity_repository(request)
    return [
        DeploymentMessageIdentityView.from_record(
            item,
            address_aliases=repository.get_address_aliases(item.deployment_id, user.id),
        )
        for item in repository.list_identities(user.id)
    ]''',
)
replace_once(
    "src/echo_masque/api/routes/discord_identities.py",
    '''            display_name=payload.display_name,
            avatar_url=str(payload.avatar_url) if payload.avatar_url is not None else "",
        )''',
    '''            display_name=payload.display_name,
            avatar_url=str(payload.avatar_url) if payload.avatar_url is not None else "",
            address_aliases=payload.address_aliases,
        )''',
)
replace_once(
    "src/echo_masque/api/routes/discord_identities.py",
    '''    return DeploymentMessageIdentityView.from_record(record)''',
    '''    return DeploymentMessageIdentityView.from_record(
        record,
        address_aliases=identity_repository(request).get_address_aliases(
            deployment_id,
            user.id,
        ),
    )''',
)

replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''    identity_display_name: str
    identity_avatar_url: str = ""
    webhook_status:''',
    '''    identity_display_name: str
    identity_avatar_url: str = ""
    address_aliases: list[str] = Field(default_factory=list, max_length=20)
    webhook_status:''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''                identity_display_name=identity_name,
                identity_avatar_url=identity_avatar,
                webhook_status=webhook_status,''',
    '''                identity_display_name=identity_name,
                identity_avatar_url=identity_avatar,
                address_aliases=identities.get_address_aliases(record.id, record.owner_id),
                webhook_status=webhook_status,''',
)

# ---------------------------------------------------------------------------
# Portal editor for explicit aliases.
# ---------------------------------------------------------------------------
replace_once(
    "web/src/discordIdentityApi.ts",
    '''  display_name: string;
  avatar_url: string;
  webhook_status:''',
    '''  display_name: string;
  avatar_url: string;
  address_aliases: string[];
  webhook_status:''',
)
replace_once(
    "web/src/discordIdentityApi.ts",
    '''  display_name: string;
  avatar_url: string | null;
}''',
    '''  display_name: string;
  avatar_url: string | null;
  address_aliases: string[];
}''',
)

replace_once(
    "web/src/DeploymentCenter.tsx",
    '''    display_name: deployment.character_display_name,
    avatar_url: "",
    webhook_status:''',
    '''    display_name: deployment.character_display_name,
    avatar_url: "",
    address_aliases: inferredAddressAliases(deployment.character_display_name),
    webhook_status:''',
)
append_before(
    "web/src/DeploymentCenter.tsx",
    "\nfunction channelGroups(",
    '''\nfunction inferredAddressAliases(...values: string[]): string[] {
  const aliases: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const full = value.trim();
    if (!full) continue;
    const normalized = full
      .replaceAll(/[（(]/gu, " · ")
      .replaceAll(/[）)]/gu, "");
    for (const candidate of [
      full,
      ...normalized.split(/\\s*(?:·|•|・|／|\\/|\\||｜)\\s*|\\s+(?:-|—|–)\\s+/u)
    ]) {
      const alias = candidate.trim();
      const key = alias.toLocaleLowerCase();
      if (!alias || seen.has(key)) continue;
      seen.add(key);
      aliases.push(alias);
    }
  }
  return aliases.slice(0, 20);
}
''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''        const avatarUrl = String(data.get("identity_avatar_url") ?? "").trim();
        await discordIdentityApi.update(saved.id, {
          mode,
          display_name: displayName,
          avatar_url: avatarUrl || null
        });''',
    '''        const avatarUrl = String(data.get("identity_avatar_url") ?? "").trim();
        const addressAliases = String(data.get("identity_address_aliases") ?? "")
          .split(/\\r?\\n|,/u)
          .map((item) => item.trim())
          .filter(Boolean);
        await discordIdentityApi.update(saved.id, {
          mode,
          display_name: displayName,
          avatar_url: avatarUrl || null,
          address_aliases: addressAliases
        });''',
)
replace_once(
    "web/src/DeploymentCenter.tsx",
    '''                    <label className="deployment-form-wide">
                      {zh ? "头像公开 URL（可选）" : "Public avatar URL (optional)"}''',
    '''                    <label className="deployment-form-wide">
                      {zh ? "角色称呼 Alias" : "Character address aliases"}
                      <input
                        name="identity_address_aliases"
                        defaultValue={(
                          formIdentity?.address_aliases.length
                            ? formIdentity.address_aliases
                            : inferredAddressAliases(
                                formIdentity?.display_name ?? "",
                                cards.find((card) => card.id === draftCharacterId)?.display_name ?? ""
                              )
                        ).join(", ")}
                        placeholder={zh ? "安, Ann" : "Ann, 安"}
                      />
                      <small>
                        {zh
                          ? "用逗号分隔。路由会优先使用这些明确称呼，不再依赖显示名称格式。"
                          : "Comma-separated explicit routing names, independent of display-name formatting."}
                      </small>
                    </label>
                    <label className="deployment-form-wide">
                      {zh ? "头像公开 URL（可选）" : "Public avatar URL (optional)"}''',
)

# ---------------------------------------------------------------------------
# Connector payload and routing logic.
# ---------------------------------------------------------------------------
replace_once(
    "connectors/discord/src/types.ts",
    '''  identity_display_name: string;
  identity_avatar_url: string;
  webhook_status:''',
    '''  identity_display_name: string;
  identity_avatar_url: string;
  address_aliases?: string[];
  webhook_status:''',
)
replace_once(
    "connectors/discord/src/routing.ts",
    '''      ...nameAliases(deployment.identity_display_name),
      ...nameAliases(deployment.character_display_name)''',
    '''      ...(deployment.address_aliases ?? []).flatMap(nameAliases),
      ...nameAliases(deployment.identity_display_name),
      ...nameAliases(deployment.character_display_name)''',
)
replace_once(
    "connectors/discord/src/routing.ts",
    '''interface NameMatch {
  deployments: DiscordDeployment[];
  remainder: string;
}''',
    '''interface NameMatch {
  matches: Array<{ deployment: DiscordDeployment; alias: string }>;
  deployments: DiscordDeployment[];
  remainder: string;
}''',
)
replace_once(
    "connectors/discord/src/routing.ts",
    '''  const deployments = [
    ...new Map(top.map((item) => [item.deployment.deployment_id, item.deployment])).values()
  ];
  return {
    deployments,
    remainder: top[0]?.remainder ?? value
  };''',
    '''  const uniqueMatches = new Map<
    string,
    { deployment: DiscordDeployment; alias: string }
  >();
  for (const item of top) {
    if (!uniqueMatches.has(item.deployment.deployment_id)) {
      uniqueMatches.set(item.deployment.deployment_id, {
        deployment: item.deployment,
        alias: item.alias
      });
    }
  }
  const selected = [...uniqueMatches.values()];
  return {
    matches: selected,
    deployments: selected.map((item) => item.deployment),
    remainder: top[0]?.remainder ?? value
  };''',
)

# Replace the old Bot Tag resolver with deterministic normalization + resolver.
start_marker = "export function resolveBotTagAudience("
end_marker = "\n\nexport interface TriggerState {"
routing_path = ROOT / "connectors/discord/src/routing.ts"
routing_text = routing_path.read_text(encoding="utf-8")
start = routing_text.index(start_marker)
end = routing_text.index(end_marker, start)
new_bot_tag_block = '''interface TaggedNameSequence {
  matches: Array<{ deployment: DiscordDeployment; alias: string }>;
  remainder: string;
  ambiguous: boolean;
}

function taggedNameSequence(
  candidates: DiscordDeployment[],
  text: string
): TaggedNameSequence {
  const selected = new Map<
    string,
    { deployment: DiscordDeployment; alias: string }
  >();
  let remaining = text.trim();

  while (remaining) {
    const match = matchNamePrefix(candidates, remaining, true);
    if (!match) break;
    if (match.matches.length !== 1) {
      return { matches: [], remainder: text.trim(), ambiguous: true };
    }
    const selectedMatch = match.matches[0];
    if (!selectedMatch) break;
    selected.set(selectedMatch.deployment.deployment_id, selectedMatch);

    const afterPunctuation = stripLeadingPunctuation(match.remainder);
    if (matchNamePrefix(candidates, afterPunctuation, true)) {
      remaining = afterPunctuation;
      continue;
    }
    const afterConnector = stripLeadingNameConnector(afterPunctuation);
    if (
      afterConnector !== afterPunctuation &&
      matchNamePrefix(candidates, afterConnector, true)
    ) {
      remaining = afterConnector;
      continue;
    }
    remaining = afterPunctuation;
    break;
  }

  return {
    matches: [...selected.values()],
    remainder: remaining.trim(),
    ambiguous: false
  };
}

export interface BotTagNormalization {
  displayText: string;
  audience: AudienceResolution;
  removedSelfTag: boolean;
}

export function normalizeBotTagReply(
  candidates: DiscordDeployment[],
  text: string,
  sourceDeploymentId: string,
  additionalGroupAliases: string[] = []
): BotTagNormalization {
  const available = candidates.filter(
    (item) => item.deployment_id !== sourceDeploymentId
  );
  const options = [...new Set(available.map(displayName))];
  const original = text.trim();

  const groupText = stripTaggedGroupAddress(original, additionalGroupAliases);
  if (groupText !== null) {
    return {
      displayText: original,
      audience: {
        deployments: available,
        text: groupText,
        reason: available.length ? "selected_all" : "not_found",
        options
      },
      removedSelfTag: false
    };
  }

  const sequence = taggedNameSequence(candidates, original);
  if (sequence.ambiguous) {
    return {
      displayText: original,
      audience: {
        deployments: [],
        text: original,
        reason: "ambiguous",
        options
      },
      removedSelfTag: false
    };
  }
  if (!sequence.matches.length) {
    return {
      displayText: original,
      audience: {
        deployments: [],
        text: original,
        reason: "not_found",
        options
      },
      removedSelfTag: false
    };
  }

  const removedSelfTag = sequence.matches.some(
    (item) => item.deployment.deployment_id === sourceDeploymentId
  );
  const targetMatches = sequence.matches.filter(
    (item) => item.deployment.deployment_id !== sourceDeploymentId
  );
  const targetDeployments = targetMatches.map((item) => item.deployment);
  const visibleTags = targetMatches.map((item) => `@${item.alias}`).join(" and ");
  const displayText = [visibleTags, sequence.remainder].filter(Boolean).join(" ").trim();

  return {
    displayText,
    audience: {
      deployments: targetDeployments,
      text: sequence.remainder,
      reason:
        targetDeployments.length > 1
          ? "selected_multiple"
          : targetDeployments.length === 1
            ? "selected_alias"
            : "not_found",
      options
    },
    removedSelfTag
  };
}

export function resolveBotTagAudience(
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
}'''
routing_path.write_text(
    routing_text[:start] + new_bot_tag_block + routing_text[end:],
    encoding="utf-8",
)

# Index: import normalizer, prefer explicit aliases in prompts, sanitize before sending.
replace_once(
    "connectors/discord/src/index.ts",
    '''  flattenDeployments,
  resolveAudience,
  resolveBotTagAudience,''',
    '''  flattenDeployments,
  normalizeBotTagReply,
  resolveAudience,
  resolveBotTagAudience,''',
)
append_before(
    "connectors/discord/src/index.ts",
    "\nfunction knownWebhookIds(): Set<string> {",
    '''\nfunction deploymentAddressAlias(deployment: DiscordDeployment): string {
  return deployment.address_aliases?.[0] ?? deploymentDisplayName(deployment);
}
''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      available_characters: candidates
        .filter((item) => item.deployment_id !== deployment.deployment_id)
        .map(deploymentDisplayName),''',
    '''      available_characters: candidates
        .filter((item) => item.deployment_id !== deployment.deployment_id)
        .map(deploymentAddressAlias),''',
)
# Replace both generated-reply send blocks by targeting their unique lead-ins.
replace_once(
    "connectors/discord/src/index.ts",
    '''    if (reply.action !== "reply" || !reply.text) continue;

    const sentMessageIds = await sendCharacterReply(
      sourceMessage,
      deployment,
      reply.text,
      botUserId
    );''',
    '''    if (reply.action !== "reply" || !reply.text) continue;
    const normalizedReply = normalizeBotTagReply(
      candidates,
      reply.text,
      deployment.deployment_id,
      config.groupAddressAliases
    );
    const outgoingText = normalizedReply.displayText.trim();
    if (!outgoingText) {
      log("Suppressed an empty character reply after removing a self Tag.", {
        deploymentId: deployment.deployment_id,
        sourceDeploymentId: sourceDeployment.deployment_id
      });
      continue;
    }

    const sentMessageIds = await sendCharacterReply(
      sourceMessage,
      deployment,
      outgoingText,
      botUserId
    );''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      text: reply.text,
      created_at: new Date().toISOString(),
      is_bot: true
    });
    nextTurns.push({ deployment, text: reply.text, sentMessageIds });''',
    '''      text: outgoingText,
      created_at: new Date().toISOString(),
      is_bot: true
    });
    nextTurns.push({ deployment, text: outgoingText, sentMessageIds });''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''        available_characters: candidates
          .filter((item) => item.deployment_id !== deployment.deployment_id)
          .map(deploymentDisplayName),''',
    '''        available_characters: candidates
          .filter((item) => item.deployment_id !== deployment.deployment_id)
          .map(deploymentAddressAlias),''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''      if (reply.action !== "reply" || !reply.text) continue;

      const sentMessageIds = await sendCharacterReply(
        guildMessage,
        deployment,
        reply.text,
        botUser.id
      );''',
    '''      if (reply.action !== "reply" || !reply.text) continue;
      const normalizedReply = normalizeBotTagReply(
        candidates,
        reply.text,
        deployment.deployment_id,
        config.groupAddressAliases
      );
      const outgoingText = normalizedReply.displayText.trim();
      if (!outgoingText) {
        log("Suppressed an empty character reply after removing a self Tag.", {
          deploymentId: deployment.deployment_id,
          sourceMessageId: guildMessage.id
        });
        continue;
      }

      const sentMessageIds = await sendCharacterReply(
        guildMessage,
        deployment,
        outgoingText,
        botUser.id
      );''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''        text: reply.text,
        created_at: new Date().toISOString(),
        is_bot: true
      });''',
    '''        text: outgoingText,
        created_at: new Date().toISOString(),
        is_bot: true
      });''',
)
replace_once(
    "connectors/discord/src/index.ts",
    '''        reply.text,
        sentMessageIds,
        candidates,''',
    '''        outgoingText,
        sentMessageIds,
        candidates,''',
)

# Dynamic prompt examples must never hard-code the current character's name.
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''        tag_guidance: tuple[str, ...] = ()
        if peers:
            tag_guidance = (
                f"Other active characters at this location: {', '.join(peers)}.",
                "To intentionally invite another character to answer, begin your "
                "reply with @ followed by that character's displayed name or a clear "
                "bilingual alias. Tag each intended character separately, for example "
                "@Ning or @Ning and @Zhi.",
                "Use character tags sparingly and only when their response adds value. "
                "Never tag yourself. A leading tag may cause another provider call.",
            )''',
    '''        tag_guidance: tuple[str, ...] = ()
        if peers:
            example = f"@{peers[0]}"
            if len(peers) > 1:
                example = f"{example} and @{peers[1]}"
            tag_guidance = (
                f"Other active character Tags at this location: {', '.join(peers)}.",
                "To intentionally invite another character to answer, begin your "
                "reply with @ followed by one of the listed character Tags. Tag each "
                f"intended character separately, for example {example}.",
                "The examples name other active characters, never you. Use character "
                "tags sparingly and only when their response adds value. Never tag "
                "yourself. A leading tag may cause another provider call.",
            )''',
)

# ---------------------------------------------------------------------------
# Regression tests.
# ---------------------------------------------------------------------------
replace_once(
    "connectors/discord/src/routing.test.ts",
    '''  findDeployment,
  resolveAudience,
  resolveBotTagAudience,''',
    '''  findDeployment,
  normalizeBotTagReply,
  resolveAudience,
  resolveBotTagAudience,''',
)
replace_once(
    "connectors/discord/src/routing.test.ts",
    '''    identity_display_name: name,
    identity_avatar_url: `https://example.com/${name}.png`,
    webhook_status:''',
    '''    identity_display_name: name,
    identity_avatar_url: `https://example.com/${name}.png`,
    address_aliases: [],
    webhook_status:''',
)
append_before(
    "connectors/discord/src/routing.test.ts",
    '''\nit("routes tagged group aliases to every other character", () => {''',
    '''\nit("uses explicit aliases independently of the Discord display name", () => {
  const ann = deployment("mention_and_reply", "", "安", {
    address_aliases: ["安", "Ann"]
  });
  const ning = deployment("mention_and_reply", "", "宁", {
    address_aliases: ["宁", "Ning"]
  });

  const selected = resolveAudience([ann, ning], "Ann ping");
  expect(selected.deployments[0]?.deployment_id).toBe(ann.deployment_id);
  expect(selected.text).toBe("ping");
});

it("removes self Tags before display and preserves other tagged characters", () => {
  const ann = deployment("mention_and_reply", "", "安・Ann", {
    address_aliases: ["安", "Ann"]
  });
  const ning = deployment("mention_and_reply", "", "宁・Ning", {
    address_aliases: ["宁", "Ning"]
  });

  const selfOnly = normalizeBotTagReply(
    [ann, ning],
    "@Ning 刚才的话题没有需要补充的。",
    ning.deployment_id
  );
  expect(selfOnly.displayText).toBe("刚才的话题没有需要补充的。");
  expect(selfOnly.audience.deployments).toEqual([]);
  expect(selfOnly.removedSelfTag).toBe(true);

  const mixed = normalizeBotTagReply(
    [ann, ning],
    "@Ning and @Ann 这部分交给你。",
    ning.deployment_id
  );
  expect(mixed.displayText).toBe("@Ann 这部分交给你。");
  expect(mixed.audience.deployments.map((item) => item.deployment_id)).toEqual([
    ann.deployment_id
  ]);
  expect(mixed.audience.text).toBe("这部分交给你。");
});
''',
)

# Existing connector API test snapshots now include explicit aliases.
replace_once(
    "tests/test_discord_connector.py",
    '''    avatar_url: str = "",
) -> dict[str, object]:''',
    '''    avatar_url: str = "",
    address_aliases: list[str] | None = None,
) -> dict[str, object]:''',
)
replace_once(
    "tests/test_discord_connector.py",
    '''        "identity_avatar_url": avatar_url,
        "webhook_status": webhook_status,''',
    '''        "identity_avatar_url": avatar_url,
        "address_aliases": address_aliases or [],
        "webhook_status": webhook_status,''',
)
replace_once(
    "tests/test_discord_connector.py",
    '''            "display_name": "Ann in Discord",
            "avatar_url": "https://example.com/ann.png",
        },''',
    '''            "display_name": "Ann in Discord",
            "avatar_url": "https://example.com/ann.png",
            "address_aliases": ["安", "Ann"],
        },''',
)
replace_once(
    "tests/test_discord_connector.py",
    '''            identity_name="Ann in Discord",
            avatar_url="https://example.com/ann.png",
        )''',
    '''            identity_name="Ann in Discord",
            avatar_url="https://example.com/ann.png",
            address_aliases=["安", "Ann"],
        )''',
)
replace_once(
    "tests/test_discord_connector.py",
    '''    assert public_payload["display_name"] == "Ann in Discord"
    assert "webhook_token" not in public_payload''',
    '''    assert public_payload["display_name"] == "Ann in Discord"
    assert public_payload["address_aliases"] == ["安", "Ann"]
    assert "webhook_token" not in public_payload''',
)

replace_once(
    "tests/test_discord_bot_tag_runtime.py",
    '''    assert "Other active characters at this location: Ann, 织 · Zhi." in prompt
    assert "begin your reply with @" in prompt''',
    '''    assert "Other active character Tags at this location: Ann, 织 · Zhi." in prompt
    assert "for example @Ann and @织 · Zhi." in prompt
    assert "@Ning or @Ning" not in prompt
    assert "begin your reply with @" in prompt''',
)

# Remove this one-shot generator from the feature branch before committing.
Path(__file__).unlink()
