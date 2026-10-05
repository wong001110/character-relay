import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CliAuthorize, CliAuthorizationDetails } from "./CliAuthorize";
import { CliGrantSettings } from "./CliGrantSettings";
import type { CliAuthorizationReview } from "./cliAuthApi";
import { I18nProvider } from "./i18n";

const user = { id: "user-1", display_name: "Approval Owner", email: "owner@example.invalid", role: "admin" as const };
const review: CliAuthorizationReview = {
  client_id: "character-relay-cli", client_name: "Official CLI <fixture>",
  account: { user_id: user.id, display_name: user.display_name, email: user.email },
  rooms: [{ id: "room-alpha", name: "Alpha <room>" }, { id: "room-beta", name: "Beta" }],
  scopes: ["identity:read", "rooms:read", "messages:read"],
  device_expires_at: "2026-10-05T10:00:00Z", access_token_ttl_seconds: 900
};

function render(node: React.ReactNode, language = "en") {
  vi.stubGlobal("window", { localStorage: { getItem: () => language } });
  return renderToStaticMarkup(<I18nProvider>{node}</I18nProvider>);
}

describe("CLI approval presentation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("pre-fills a provided code but shows no approval action before review", () => {
    const markup = render(<CliAuthorize user={user} initialCode="ABCD-EFGH" />);
    expect(markup).toContain('value="ABCD-EFGH"');
    expect(markup).toContain("Review request");
    expect(markup).not.toContain("Approve read-only access</button>");
    expect(markup).toContain(user.email);
  });

  it("displays the explicit client, approving account, room IDs, scopes and lifetime", () => {
    const markup = render(<CliAuthorizationDetails review={review} zh={false} />);
    for (const value of [review.client_id, user.email, "room-alpha", "room-beta", "identity:read", "rooms:read", "messages:read", "900 seconds after approval"]) {
      expect(markup).toContain(value);
    }
    expect(markup).toContain("Official CLI &lt;fixture&gt;");
    expect(markup).toContain("Alpha &lt;room&gt;");
    expect(markup).toContain("cannot send messages");
  });

  it("explains authorization in Chinese with the same explicit room limits", () => {
    const markup = render(<CliAuthorizationDetails review={review} zh={true} />, "zh-CN");
    expect(markup).toContain("仅允许以下房间");
    expect(markup).toContain("读取所选房间的最近消息");
    expect(markup).toContain("900 秒，批准后开始计时");
  });

  it("provides no approval or grant management actions for demo and preview modes", () => {
    const authorization = render(<CliAuthorize user={user} disabled initialCode="ABCD-EFGH" />);
    expect(authorization).toContain("cannot approve real CLI access");
    expect(authorization).not.toContain("<form");
    const settings = render(<CliGrantSettings disabled userId={user.id} />);
    expect(settings).toContain("cannot manage real CLI grants");
    expect(settings).not.toContain("<button");
  });
});
