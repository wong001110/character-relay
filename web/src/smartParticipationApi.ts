export type SmartParticipationStyle = "quiet" | "balanced" | "active";
export type SmartParticipationGroupRole = "primary" | "secondary" | "independent";
export type SmartParticipationFeedbackLabel =
  | "correct"
  | "should_speak"
  | "should_stay_silent";

export interface SmartParticipationProfile {
  character_card_id: string;
  configured: boolean;
  enabled: boolean;
  style: SmartParticipationStyle;
  group_role: SmartParticipationGroupRole;
  topics: string[];
  keywords: string[];
  trigger_phrases: string[];
  avoid_phrases: string[];
  cooldown_seconds: number;
  preferred_follow_up_character_card_id: string;
  follow_up_window_seconds: number;
  created_at: string | null;
  updated_at: string | null;
}

export type SmartParticipationProfileUpdate = Omit<
  SmartParticipationProfile,
  "character_card_id" | "configured" | "created_at" | "updated_at"
>;

export interface SmartParticipationGeneratedProfile
  extends SmartParticipationProfileUpdate {
  preferred_follow_up_character_name: string;
  rationale: string;
  provider_model: string;
  correction_used: boolean;
}

export interface SmartParticipationPreview {
  character_card_id: string;
  decision: "participate" | "silent";
  reason: string;
  score: number;
  minimum_score: number;
  signals: Record<string, number>;
  matched_topics: string[];
  matched_keywords: string[];
  matched_trigger_phrases: string[];
  matched_avoid_phrases: string[];
  follow_up_eligible: boolean;
  follow_up_reason: string;
}

export interface SmartParticipationFeedback {
  id: string;
  character_card_id: string;
  feedback_label: SmartParticipationFeedbackLabel;
  created_at: string;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve raw response below.
  }
  return raw || `Request failed with ${response.status}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const smartParticipationApi = {
  getProfile: (characterCardId: string) =>
    request<SmartParticipationProfile>(
      `/api/smart-participation/profiles/${encodeURIComponent(characterCardId)}`
    ),
  updateProfile: (characterCardId: string, payload: SmartParticipationProfileUpdate) =>
    request<SmartParticipationProfile>(
      `/api/smart-participation/profiles/${encodeURIComponent(characterCardId)}`,
      { method: "PUT", body: JSON.stringify(payload) }
    ),
  generateProfile: (characterCardId: string) =>
    request<SmartParticipationGeneratedProfile>(
      `/api/smart-participation/profiles/${encodeURIComponent(characterCardId)}/generate`,
      { method: "POST" }
    ),
  evaluate: (
    characterCardId: string,
    message: string,
    previousCharacterCardId = "",
    profileOverride?: SmartParticipationProfileUpdate
  ) =>
    request<SmartParticipationPreview>(
      `/api/smart-participation/playground/${encodeURIComponent(characterCardId)}/evaluate`,
      {
        method: "POST",
        body: JSON.stringify({
          message,
          previous_character_card_id: previousCharacterCardId,
          profile_override: profileOverride
        })
      }
    ),
  recordFeedback: (
    characterCardId: string,
    payload: {
      message: string;
      previous_character_card_id: string;
      predicted_decision: "participate" | "silent";
      predicted_reason: string;
      score: number;
      minimum_score: number;
      signals: Record<string, number>;
      feedback_label: SmartParticipationFeedbackLabel;
    }
  ) =>
    request<SmartParticipationFeedback>(
      `/api/smart-participation/feedback/${encodeURIComponent(characterCardId)}`,
      { method: "POST", body: JSON.stringify(payload) }
    )
};
