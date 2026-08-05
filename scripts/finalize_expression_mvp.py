from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/echo_masque/connector_runtime.py",
    '''        marker = re.search(r"\\[\\[CR_EXPRESSION\\s+(\\{.*?\\})\\s*\\]\\]\\s*$", text, re.DOTALL)
        if marker is None:
            return text.strip(), ExpressionDecision(reason="model_omitted_expression_control")
        clean_text = text[: marker.start()].rstrip()
        try:
            value = json.loads(marker.group(1))''',
    '''        marker = re.search(r"\\[\\[CR_EXPRESSION\\s+(.*?)\\s*\\]\\]\\s*$", text, re.DOTALL)
        if marker is None:
            return text.strip(), ExpressionDecision(reason="model_omitted_expression_control")
        clean_text = text[: marker.start()].rstrip()
        try:
            value = json.loads(marker.group(1))''',
)

replace_once(
    "tests/test_expression_runtime.py",
    '''    assert invalid_text == "Reply\\n[[CR_EXPRESSION not-json]]"
    assert invalid.action == "none"
''',
    '''    assert invalid_text == "Reply"
    assert invalid.action == "none"
    assert invalid.reason == "invalid_expression_control"
''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''      if (deployment.identity_mode === "webhook" && candidate.asset_url) {
        try {
          const extension = candidate.format_type === "gif" ? "gif" : "png";''',
    '''      const normalizedFormat = candidate.format_type.toLowerCase();
      const webhookRenderable = !["3", "lottie"].includes(normalizedFormat);
      if (
        deployment.identity_mode === "webhook" &&
        candidate.asset_url &&
        webhookRenderable
      ) {
        try {
          const extension = ["4", "gif"].includes(normalizedFormat) ? "gif" : "png";''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''  await reportExpressionNode(retrieval.run_id, {
    node_name: "execute_delivery",
    status: "completed",''',
    '''  const expressionApplied = ![
    "invalid_action_to_text",
    "sticker_to_text"
  ].includes(fallback);
  await reportExpressionNode(retrieval.run_id, {
    node_name: "execute_delivery",
    status: "completed",''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''      expression_applied: fallback !== "invalid_action_to_text"
    },''',
    '''      expression_applied: expressionApplied
    },''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''    applied: fallback !== "invalid_action_to_text",
    fallback''',
    '''    applied: expressionApplied,
    fallback''',
)

replace_once(
    "connectors/discord/src/index.ts",
    '''      has_readable_text: Boolean(originalText),
      sticker_count: guildMessage.stickers.size''',
    '''      has_readable_text: Boolean(
        originalText || parseCustomEmojiTokens(guildMessage.content).length
      ),
      custom_emoji_count: parseCustomEmojiTokens(guildMessage.content).length,
      sticker_count: guildMessage.stickers.size''',
)
