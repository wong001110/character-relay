from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/echo_masque/api/routes/interactions.py",
    "from echo_masque.api.dependencies import CurrentUserDependency\n",
    "from echo_masque.api.dependencies import (\n"
    "    CurrentUserDependency,\n"
    "    quota_http_exception,\n"
    "    quota_service,\n"
    ")\n",
)
replace_once(
    "src/echo_masque/api/routes/interactions.py",
    "from echo_masque.persistence.interaction_models import (\n",
    "from echo_masque.expression_assistant import (\n"
    "    ExpressionAssistantService,\n"
    "    ExpressionAssistantUnavailable,\n"
    "    ExpressionSuggestionRequest,\n"
    "    ExpressionSuggestionResult,\n"
    ")\n"
    "from echo_masque.persistence.interaction_models import (\n",
)
replace_once(
    "src/echo_masque/api/routes/interactions.py",
    "from echo_masque.persistence.expression_repository import expression_key\n",
    "from echo_masque.persistence.expression_repository import expression_key\n"
    "from echo_masque.providers import ProviderError\n"
    "from echo_masque.security_controls import QuotaExceeded\n",
)

anchor = '''@router.get(
    "/discord/expression-runs",
    response_model=list[ExpressionRunView],
)'''
endpoint = '''@router.post(
    "/discord/expression-dictionary/suggest",
    response_model=ExpressionSuggestionResult,
)
async def suggest_expression_dictionary_entry(
    payload: ExpressionSuggestionRequest,
    request: Request,
    user: CurrentUserDependency,
) -> ExpressionSuggestionResult:
    runtime = request.app.state.authoring_runtime_service
    try:
        quota_service(request).consume_authoring_generation(user.id)
        return await ExpressionAssistantService(runtime).suggest(payload)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except ExpressionAssistantUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


'''
replace_once(
    "src/echo_masque/api/routes/interactions.py",
    anchor,
    endpoint + anchor,
)

replace_once(
    "web/src/interactionApi.ts",
    '''export interface ExpressionRunDetail extends ExpressionRun {
  nodes: ExpressionNode[];
}
''',
    '''export interface ExpressionRunDetail extends ExpressionRun {
  nodes: ExpressionNode[];
}

export interface ExpressionSuggestionRequest {
  resource_type: ExpressionResourceType;
  resource_id: string;
  name: string;
  description: string;
  tags: string[];
  animated: boolean;
  asset_url: string;
  usage_context: string;
  language: "en" | "zh-CN";
}

export interface ExpressionSuggestionResult {
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  aliases: string[];
  situations: string[];
  avoid_when: string[];
  provider_model: string;
  correction_used: boolean;
}
''',
)
replace_once(
    "web/src/interactionApi.ts",
    '''  saveExpression: (payload: ExpressionSemanticCreate) =>
    request<ExpressionSemantic>("/api/discord/expression-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
''',
    '''  saveExpression: (payload: ExpressionSemanticCreate) =>
    request<ExpressionSemantic>("/api/discord/expression-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  suggestExpression: (payload: ExpressionSuggestionRequest) =>
    request<ExpressionSuggestionResult>(
      "/api/discord/expression-dictionary/suggest",
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    ),
''',
)

css = Path("web/src/discordServerProfiles.css")
marker = "/* Expression JSON import and AI assistance */"
if marker not in css.read_text(encoding="utf-8"):
    css.write_text(
        css.read_text(encoding="utf-8")
        + r'''

/* Expression JSON import and AI assistance */
.expression-dictionary-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding: 12px;
  border: 1px dashed rgba(112, 86, 158, 0.2);
  border-radius: 10px;
  background: #fffaf2;
}

.expression-dictionary-toolbar > div {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.expression-dictionary-notice {
  margin: 0;
  color: rgba(41, 35, 48, 0.68);
  font-size: 0.76rem;
}

.expression-ai-assistant {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
  padding: 14px;
  border: 1px dashed rgba(112, 86, 158, 0.24);
  border-radius: 10px;
  background: rgba(233, 225, 250, 0.42);
}

.expression-ai-assistant .notebook-field {
  min-width: 0;
}

.expression-ai-assistant .paper-button {
  min-height: 44px;
  white-space: nowrap;
}

.expression-ai-result-note {
  grid-column: 1 / -1;
  margin: 0;
  color: #5f4b77;
  font-size: 0.74rem;
}

.expression-import-modal {
  width: min(940px, 96vw) !important;
}

.expression-import-summary {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 0;
}

.expression-import-summary span {
  padding: 5px 9px;
  border-radius: 999px;
  background: #e9e1fa;
  font-size: 0.72rem;
  font-weight: 800;
}

.expression-import-list {
  display: grid;
  gap: 8px;
  max-height: 52vh;
  overflow-y: auto;
  padding-right: 5px;
}

.expression-import-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 1px solid rgba(112, 86, 158, 0.15);
  border-radius: 9px;
  background: #fffaf2;
}

.expression-import-item img {
  width: 42px;
  height: 42px;
  object-fit: contain;
}

.expression-import-item > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.expression-import-item small {
  overflow-wrap: anywhere;
  color: rgba(41, 35, 48, 0.62);
}

.expression-import-state {
  padding: 4px 8px;
  border-radius: 999px;
  background: #dff0e8;
  color: #35685a;
  font-size: 0.68rem;
  font-weight: 800;
}

.expression-import-item.is-invalid .expression-import-state {
  background: #f4dfe5;
  color: #844f62;
}

.expression-import-actions {
  display: flex;
  justify-content: flex-end;
  gap: 9px;
  margin-top: 15px;
}

@media (max-width: 760px) {
  .expression-ai-assistant,
  .expression-import-item {
    grid-template-columns: 1fr;
  }

  .expression-ai-assistant .paper-button {
    width: 100%;
  }
}
''',
        encoding="utf-8",
    )
