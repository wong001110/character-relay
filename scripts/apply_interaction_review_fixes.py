from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected snippet not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/echo_masque/connector_runtime.py",
    "            if item.text.strip()\n",
    "            if item.text.strip() or item.stickers\n",
)

index = Path("connectors/discord/src/index.ts")
index_text = index.read_text(encoding="utf-8")
index_text = index_text.replace(
    '''    const interactionClaim = await relay.claimInteraction({
      guild_id: guildMessage.guildId,
      channel_id: location.channelId,
      target_user_id: guildMessage.author.id,
      source_message_id: guildMessage.id
    });
''',
    '''    let interactionClaim: DiscordInteractionClaim = {
      claimed: false,
      run_id: null,
      session: null
    };
    try {
      interactionClaim = await relay.claimInteraction({
        guild_id: guildMessage.guildId,
        channel_id: location.channelId,
        target_user_id: guildMessage.author.id,
        source_message_id: guildMessage.id
      });
    } catch (error) {
      log("Unable to check Interaction Sessions; continuing normal routing.", {
        guildId: guildMessage.guildId,
        channelId: location.channelId,
        sourceMessageId: guildMessage.id,
        error: error instanceof Error ? error.message : String(error)
      });
    }
''',
    1,
)
marker = "async function processInteractionSession("
head, tail = index_text.split(marker, 1)
tail = tail.replace(
    "        const outgoingText = normalizedReply.displayText.trim();\n",
    '''        const outgoingText = (
          normalizedReply.audience.reason === "not_found"
            ? normalizedReply.displayText
            : normalizedReply.audience.text
        ).trim();
''',
    1,
)
index.write_text(head + marker + tail, encoding="utf-8")

panel = Path("web/src/InteractionSessionsPanel.tsx")
panel_text = panel.read_text(encoding="utf-8")
panel_text = panel_text.replace(
    '''            <p>
              {zh
                ? "Roast Session 只在指定 Channel、指定用户与固定轮次内运行。每一轮代表两个角色各回复一次。"
                : "Roast Sessions run only for one target member in one channel. Each round gives both characters one turn."}
            </p>
''',
    '''            <p>
              {zh
                ? "Roast Session 只在指定 Channel、指定用户与固定轮次内运行。每一轮代表两个角色各回复一次。"
                : "Roast Sessions run only for one target member in one channel. Each round gives both characters one turn."}
            </p>
            <small className="interaction-consent-note">
              {zh
                ? "仅用于已明确同意参与的测试成员或你自己的测试账号；Session 可随时暂停或停止。"
                : "Use only with a consenting test member or your own test account. Sessions can be paused or stopped at any time."}
            </small>
''',
    1,
)
panel.write_text(panel_text, encoding="utf-8")

css = Path("web/src/interactionSessions.css")
css_text = css.read_text(encoding="utf-8")
css_text += '''
.interaction-consent-note {
  display: block;
  max-width: 760px;
  margin-top: 8px;
  color: var(--ink-soft, #6f685f);
}
'''
css.write_text(css_text, encoding="utf-8")

# Temporary generation workflows are not product files.
for temporary in (
    Path(".github/workflows/interaction-sticker-generator.yml"),
    Path(".github/workflows/interaction-review-fixes.yml"),
    Path("scripts/apply_interaction_review_fixes.py"),
):
    if temporary.exists():
        temporary.unlink()
