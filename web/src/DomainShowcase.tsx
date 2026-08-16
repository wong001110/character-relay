import { useState } from "react";

import { Button, StatusIndicator, StickyLabel } from "./components/ui";
import {
  ApiKeyField,
  ModelSelect,
  ParticipantCard,
  ProviderSelect,
  TemporaryRoleNote,
  TopicNote
} from "./components/shared";
import "./domain-showcase.css";

const providers = [
  { value: "deepseek", label: "DeepSeek" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "custom", label: "Custom Provider" }
];

const models = [
  { value: "deepseek-v4-flash", label: "DeepSeek V4 Flash", meta: "Text · Tools" },
  { value: "gemini-flash", label: "Gemini Flash", meta: "Vision · Tools" },
  { value: "custom-model", label: "Custom Model", meta: "Provider-defined" }
];

export function DomainShowcase() {
  const [provider, setProvider] = useState("deepseek");
  const [model, setModel] = useState("deepseek-v4-flash");

  return (
    <section className="domain-showcase">
      <header className="domain-showcase__heading">
        <div>
          <StickyLabel variant="memory">CHARACTER RELAY / SHARED</StickyLabel>
          <h2>Domain compositions</h2>
          <p>
            Reusable product-aware components built on top of the scrapbook primitives. These
            components know Character Relay concepts; the base controls do not.
          </p>
        </div>
        <StatusIndicator tone="success">Shared layer ready</StatusIndicator>
      </header>

      <div className="domain-showcase__grid">
        <article className="domain-showcase__paper">
          <span className="domain-showcase__index">07 / PROVIDER CONFIG</span>
          <div className="domain-showcase__form">
            <ProviderSelect
              value={provider}
              options={providers}
              onChange={(event) => setProvider(event.currentTarget.value)}
              hint="Provider selection stays separate from model and credential configuration."
            />
            <ModelSelect
              value={model}
              options={models}
              onChange={(event) => setModel(event.currentTarget.value)}
              hint="Model metadata belongs in the domain selector, not the base Select primitive."
            />
            <ApiKeyField
              defaultValue="sk-character-relay-demo"
              hint="Credential visibility is a reusable domain behavior."
              status={<StatusIndicator tone="success">Session credential configured</StatusIndicator>}
            />
          </div>
        </article>

        <article className="domain-showcase__paper">
          <span className="domain-showcase__index">08 / CONTEXT NOTES</span>
          <div className="domain-showcase__notes">
            <TopicNote
              topic="Photography"
              confidence={0.87}
              participants="Ann · Ning"
              status="active"
            />
            <TemporaryRoleNote role="Photographer" note="until topic changes" />
          </div>
        </article>

        <article className="domain-showcase__paper domain-showcase__paper--wide">
          <span className="domain-showcase__index">09 / PARTICIPANT</span>
          <div className="domain-showcase__participants">
            <ParticipantCard
              name="Ann"
              status="active"
              subtitle="Calm · observant"
              labels={
                <>
                  <StickyLabel variant="memory">Memory</StickyLabel>
                  <StickyLabel variant="vision">Vision</StickyLabel>
                  <StickyLabel variant="tool">Tools</StickyLabel>
                </>
              }
              runtimeState={<><strong>ACTIVE</strong><small>admitted this turn</small></>}
              actions={<Button variant="secondary" size="sm">Open character file</Button>}
            />
            <ParticipantCard
              name="Ning"
              status="listening"
              subtitle="Quiet · attentive"
              labels={<StickyLabel variant="neutral">Listening</StickyLabel>}
              runtimeState={<><strong>WAITING</strong><small>not admitted yet</small></>}
            />
          </div>
        </article>
      </div>
    </section>
  );
}
