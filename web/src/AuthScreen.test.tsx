import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AuthScreen } from "./AuthScreen";
import { I18nProvider } from "./i18n";

describe("AuthScreen", () => {
  it("renders the primary login action as a form submit button", () => {
    const markup = renderToStaticMarkup(
      createElement(
        I18nProvider,
        null,
        createElement(AuthScreen, {
          config: {
            registration_enabled: false,
            invitation_required: false,
            authentication_required: true
          },
          onAuthenticated: vi.fn()
        })
      )
    );

    expect(markup).toContain('type="submit"');
    expect(markup).toContain("Enter studio");
  });
});
