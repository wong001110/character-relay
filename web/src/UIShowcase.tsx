import { useState } from "react";

import {
  Annotation,
  Avatar,
  Button,
  Checkbox,
  EmptyState,
  FormField,
  Input,
  InspectorSection,
  PageFlag,
  PageFlagGroup,
  PaperCard,
  PaperTab,
  Radio,
  SearchField,
  Select,
  SettingsRow,
  Stamp,
  StatusIndicator,
  StickyLabel,
  StickyNote,
  Switch,
  Textarea
} from "./components/ui";
import "./ui-showcase.css";

const flagItems = [
  ["Identity", "lavender"],
  ["Persona", "peach"],
  ["Boundaries", "rose"],
  ["Memory", "yellow"],
  ["Runtime", "mint"]
] as const;

export function UIShowcase() {
  const [flag, setFlag] = useState("Identity");
  const [tab, setTab] = useState<"source" | "runtime">("runtime");
  const [switchOn, setSwitchOn] = useState(true);

  return (
    <main className="ui-showcase-page">
      <header className="ui-showcase-hero">
        <div>
          <StickyLabel variant="link">DESIGN SYSTEM / DEV</StickyLabel>
          <h1>Character Relay Scrapbook UI</h1>
          <p>
            Shared controls, stationery objects, technical inspector patterns, and the
            interaction language used by Character Relay web surfaces.
          </p>
        </div>
        <StickyNote variant="note" size="lg" pinned>
          <strong>Interaction language</strong>
          <p>Write · Stick · Flip · Rewrite · Rearrange · Annotate</p>
          <Annotation>Function stays predictable. Material carries the personality.</Annotation>
        </StickyNote>
      </header>

      <section className="ui-showcase-grid">
        <PaperCard className="ui-showcase-panel">
          <div className="ui-showcase-panel-heading">
            <span>01 / ACTIONS</span>
            <h2>Buttons & status</h2>
          </div>
          <div className="ui-showcase-row">
            <Button variant="primary">Save character</Button>
            <Button variant="secondary">Open file</Button>
            <Button variant="ghost">Cancel</Button>
            <Button variant="danger">Delete</Button>
          </div>
          <div className="ui-showcase-row">
            <StatusIndicator tone="success">Connected</StatusIndicator>
            <StatusIndicator tone="info" pulse>Running</StatusIndicator>
            <StatusIndicator tone="warning">Needs review</StatusIndicator>
            <StatusIndicator tone="danger">Failed</StatusIndicator>
          </div>
          <div className="ui-showcase-row">
            <Stamp variant="success">SAVED</Stamp>
            <Stamp variant="danger">OOC</Stamp>
            <Stamp variant="info">INSPECTED</Stamp>
            <StickyLabel variant="vision">Vision</StickyLabel>
            <StickyLabel variant="memory">Memory</StickyLabel>
            <StickyLabel variant="tool">Tool</StickyLabel>
          </div>
        </PaperCard>

        <PaperCard className="ui-showcase-panel">
          <div className="ui-showcase-panel-heading">
            <span>02 / WRITE</span>
            <h2>Form controls</h2>
          </div>
          <div className="ui-showcase-form-grid">
            <FormField label="Character name" hint="Shown in the shelf and runtime.">
              <Input defaultValue="Ann" />
            </FormField>
            <FormField label="Provider">
              <Select defaultValue="deepseek">
                <option value="deepseek">DeepSeek</option>
                <option value="openrouter">OpenRouter</option>
                <option value="custom">Custom</option>
              </Select>
            </FormField>
            <FormField className="ui-showcase-wide" label="Persona note">
              <Textarea rows={4} defaultValue="Calm, observant, and careful about shared memory." />
            </FormField>
            <SearchField className="ui-showcase-wide" placeholder="Search character, topic, or evidence…" />
          </div>
          <div className="ui-showcase-controls">
            <Checkbox label="Allow media understanding" defaultChecked />
            <Radio name="showcase-radio" label="Benchmark" defaultChecked />
            <Radio name="showcase-radio" label="Adaptive" />
            <Switch
              checked={switchOn}
              onChange={(event) => setSwitchOn(event.currentTarget.checked)}
              label="Smart Participation"
            />
          </div>
        </PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide">
          <div className="ui-showcase-panel-heading">
            <span>03 / FLIP</span>
            <h2>Page flags & paper tabs</h2>
          </div>
          <div className="ui-showcase-navigation-demo">
            <PageFlagGroup orientation="vertical" label="Character file sections">
              {flagItems.map(([item, tone]) => (
                <PageFlag key={item} tone={tone} active={flag === item} onClick={() => setFlag(item)}>
                  {item}
                </PageFlag>
              ))}
            </PageFlagGroup>
            <div className="ui-showcase-page-sheet">
              <StickyLabel variant="neutral">CURRENT PAGE</StickyLabel>
              <h3>{flag}</h3>
              <p>
                PageFlags mark navigation and classification. They do not carry temporary content;
                StickyNotes do that job.
              </p>
              <div className="ui-showcase-tabs">
                <PaperTab tone="yellow" active={tab === "source"} onClick={() => setTab("source")}>Source prompt</PaperTab>
                <PaperTab tone="blue" active={tab === "runtime"} onClick={() => setTab("runtime")}>Runtime prompt</PaperTab>
              </div>
            </div>
          </div>
        </PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide">
          <div className="ui-showcase-panel-heading">
            <span>04 / STICK & ANNOTATE</span>
            <h2>Scrapbook objects</h2>
          </div>
          <div className="ui-showcase-notes">
            <StickyNote variant="topic" pinned>
              <strong>Current topic</strong>
              <p>Photography</p>
              <small>confidence · 0.87</small>
            </StickyNote>
            <StickyNote variant="temporary">
              <strong>Temporary role</strong>
              <p>Photographer</p>
            </StickyNote>
            <StickyNote variant="character">
              <strong>AI observation</strong>
              <p>Ann noticed a black cat beside the window.</p>
            </StickyNote>
            <StickyNote variant="warning">
              <strong>Judge note</strong>
              <p>Relationship boundary may need review.</p>
            </StickyNote>
          </div>
        </PaperCard>

        <InspectorSection
          className="ui-showcase-panel ui-showcase-panel--wide"
          eyebrow="Technical evidence"
          title="Inspector section"
          description="Dense technical views use the same paper system with lower decoration intensity."
          actions={<StatusIndicator tone="success">Runtime healthy</StatusIndicator>}
        >
          <div className="ui-showcase-inspector-grid">
            <div><span>Provider</span><strong>DeepSeek</strong></div>
            <div><span>Model</span><strong>deepseek-v4-flash</strong></div>
            <div><span>Latency</span><strong>182 ms</strong></div>
            <div><span>Decision</span><strong>CONTINUE</strong></div>
          </div>
        </InspectorSection>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide">
          <div className="ui-showcase-panel-heading">
            <span>05 / EMPTY STATE</span>
            <h2>Illustration-safe surface</h2>
          </div>
          <EmptyState
            illustration={<div className="ui-showcase-placeholder-art" aria-hidden="true">✦ ᓚᘏᗢ ✦</div>}
            title="Nothing filed here yet"
            description="This illustration slot may use generated raster artwork when organic anime scrapbook art is more appropriate than SVG."
            action={<Button variant="primary">Add note</Button>}
          />
        </PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide">
          <div className="ui-showcase-panel-heading">
            <span>06 / CHARACTER IDENTITY</span>
            <h2>Avatar treatment</h2>
          </div>
          <div className="ui-showcase-avatars">
            <Avatar name="Ann" size="lg" status="active" />
            <Avatar name="Ning" size="lg" status="listening" />
            <Avatar name="Zhi" size="lg" status="thinking" />
          </div>
          <SettingsRow
            title="Media understanding"
            description="Allow this character to inspect images when the runtime requires it."
            control={<Switch defaultChecked aria-label="Media understanding" />}
          />
        </PaperCard>
      </section>
    </main>
  );
}
