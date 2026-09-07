export type TurnControl =
  | { kind: "cancel"; audienceText: string }
  | { kind: "replace"; audienceText: string; replacementText: string };

/**
 * Accept only anchored control forms.  The caller must still require a Bot mention,
 * an exact reply to the caller's original human request, and a resolved deployment.
 * Natural-language substrings are deliberately not treated as cancellation.
 */
export function parseTurnControl(text: string): TurnControl | null {
  const normalized = text.replace(/\s+/gu, " ").trim();
  const cancel = /^(?<audience>.+?)\s+(?:cancel|stop|取消|停止)$/iu.exec(normalized);
  if (cancel?.groups?.audience?.trim()) {
    return { kind: "cancel", audienceText: cancel.groups.audience.trim() };
  }
  const replace = /^(?<audience>.+?)\s+(?:replace|替換|改成)\s*:\s*(?<text>.+)$/iu.exec(
    normalized
  );
  if (replace?.groups?.audience?.trim() && replace.groups.text?.trim()) {
    return {
      kind: "replace",
      audienceText: replace.groups.audience.trim(),
      replacementText: replace.groups.text.trim()
    };
  }
  return null;
}
