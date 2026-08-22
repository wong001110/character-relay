import { useState } from "react";

import {
  Annotation,
  Avatar,
  Button,
  CharacterChip,
  Checkbox,
  ConfirmDialog,
  Divider,
  EmptyState,
  FormField,
  FunctionalIcon,
  IconButton,
  Input,
  InspectorSection,
  Menu,
  MenuItem,
  PageFlag,
  PageFlagGroup,
  PaperCard,
  PaperDrawer,
  PaperModal,
  PaperTab,
  Popover,
  Radio,
  SearchField,
  Select,
  SettingsRow,
  Skeleton,
  Spinner,
  Stamp,
  StatusIndicator,
  StickyLabel,
  StickyNote,
  Switch,
  Textarea,
  Toast,
  Tooltip
} from "./components/ui";
import {
  componentCatalogCanonicalTotal,
  componentCatalogLayers,
  componentCatalogTotal
} from "./componentCatalog";
import {
  NotebookField,
  NotebookInput,
  NotebookSection,
  NotebookSelect,
  NotebookTextarea
} from "./NotebookUI";
import { Pagination } from "./Pagination";
import "./ui-showcase.css";

const flagItems = [["Identity", "lavender"], ["Persona", "peach"], ["Boundaries", "rose"], ["Memory", "yellow"], ["Runtime", "mint"]] as const;
const functionalIcons = [
  "home", "characters", "deployment", "toolbox", "settings", "overview", "behavior",
  "provider", "runtime", "tools", "schedule", "search", "refresh", "chevron", "close",
  "identity", "persona", "voice", "boundaries", "memory", "review", "archive",
  "status-check", "cloud", "warning", "paper-plane", "bell", "sun", "moon"
] as const;

function layerEyebrow(layerId: "ui" | "domain" | "utility"): string {
  if (layerId === "ui") return "FOUNDATION";
  if (layerId === "domain") return "PRODUCT-AWARE";
  return "SHARED UTILITY";
}

export function UIShowcase() {
  const [flag, setFlag] = useState("Identity");
  const [tab, setTab] = useState<"source" | "runtime">("runtime");
  const [switchOn, setSwitchOn] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [utilityPage, setUtilityPage] = useState(1);
  const [annChipVisible, setAnnChipVisible] = useState(true);

  return (
    <main className="ui-showcase-page">
      <section className="component-library-overview" aria-labelledby="component-library-title">
        <header className="component-library-overview__header">
          <div>
            <StickyLabel variant="warning">SUPER ADMIN / LIVING CATALOG</StickyLabel>
            <h1 id="component-library-title">{componentCatalogTotal} reusable components</h1>
            <p>
              {componentCatalogCanonicalTotal} formal library exports plus{" "}
              {componentCatalogTotal - componentCatalogCanonicalTotal} reusable notebook and
              pagination utilities. Feature-only page components are not included.
            </p>
          </div>
          <a className="cr-button cr-button--secondary cr-control--md" href="/">
            <FunctionalIcon name="chevron" size={15} /> Back to Character Relay
          </a>
        </header>
        <div className="component-library-overview__layers">
          {componentCatalogLayers.map((layer) => (
            <article key={layer.id} className="component-library-layer-card">
              <span>{layerEyebrow(layer.id)}</span>
              <strong>{layer.components.length}</strong>
              <h2>{layer.label}</h2>
              <p>{layer.description}</p>
              <details>
                <summary>View {layer.components.length} component names</summary>
                <div className="component-library-layer-card__names">
                  {layer.components.map((component) => (
                    <code key={component}>{component}</code>
                  ))}
                </div>
              </details>
            </article>
          ))}
        </div>
      </section>

      <header className="ui-showcase-hero">
        <div><StickyLabel variant="link">DESIGN SYSTEM / VISUAL STATES</StickyLabel><h1>Character Relay Scrapbook UI</h1><p>Shared controls, stationery objects, technical inspector patterns, and the interaction language used by Character Relay web surfaces.</p></div>
        <StickyNote variant="note" size="lg" pinned><strong>Interaction language</strong><p>Write · Stick · Flip · Rewrite · Rearrange · Annotate</p><Annotation>Function stays predictable. Material carries the personality.</Annotation></StickyNote>
      </header>

      <section className="ui-showcase-grid">
        <PaperCard className="ui-showcase-panel">
          <div className="ui-showcase-panel-heading"><span>01 / ACTIONS</span><h2>Buttons & status</h2></div>
          <div className="ui-showcase-row"><Button variant="primary">Save character</Button><Button variant="secondary">Open file</Button><Button variant="ghost">Cancel</Button><Button variant="danger">Delete</Button><IconButton aria-label="Refresh component state"><FunctionalIcon name="refresh" size={16} /></IconButton></div>
          <div className="ui-showcase-row"><StatusIndicator tone="success">Connected</StatusIndicator><StatusIndicator tone="info" pulse>Running</StatusIndicator><StatusIndicator tone="warning">Needs review</StatusIndicator><StatusIndicator tone="danger">Failed</StatusIndicator></div>
          <div className="ui-showcase-row"><Stamp variant="success">SAVED</Stamp><Stamp variant="danger">OOC</Stamp><Stamp variant="info">INSPECTED</Stamp><StickyLabel variant="vision">Vision</StickyLabel><StickyLabel variant="memory">Memory</StickyLabel><StickyLabel variant="tool">Tool</StickyLabel></div>
        </PaperCard>

        <PaperCard className="ui-showcase-panel">
          <div className="ui-showcase-panel-heading"><span>02 / WRITE</span><h2>Form controls</h2></div>
          <div className="ui-showcase-form-grid"><FormField label="Character name" hint="Shown in the shelf and runtime."><Input defaultValue="Ann" /></FormField><FormField label="Provider"><Select defaultValue="deepseek"><option value="deepseek">DeepSeek</option><option value="openrouter">OpenRouter</option><option value="custom">Custom</option></Select></FormField><FormField className="ui-showcase-wide" label="Persona note"><Textarea rows={4} defaultValue="Calm, observant, and careful about shared memory." /></FormField><SearchField className="ui-showcase-wide" placeholder="Search character, topic, or evidence…" /></div>
          <div className="ui-showcase-controls"><Checkbox label="Allow media understanding" defaultChecked /><Radio name="showcase-radio" label="Benchmark" defaultChecked /><Radio name="showcase-radio" label="Adaptive" /><Switch checked={switchOn} onChange={(event) => setSwitchOn(event.currentTarget.checked)} label="Smart Participation" /></div>
        </PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide">
          <div className="ui-showcase-panel-heading"><span>03 / FLIP</span><h2>Page flags & paper tabs</h2></div>
          <div className="ui-showcase-navigation-demo"><PageFlagGroup orientation="vertical" label="Character file sections">{flagItems.map(([item, tone]) => <PageFlag key={item} tone={tone} active={flag === item} onClick={() => setFlag(item)}>{item}</PageFlag>)}</PageFlagGroup><div className="ui-showcase-page-sheet"><StickyLabel variant="neutral">CURRENT PAGE</StickyLabel><h3>{flag}</h3><p>PageFlags mark navigation and classification. They do not carry temporary content; StickyNotes do that job.</p><div className="ui-showcase-tabs"><PaperTab tone="yellow" active={tab === "source"} onClick={() => setTab("source")}>Source prompt</PaperTab><PaperTab tone="blue" active={tab === "runtime"} onClick={() => setTab("runtime")}>Runtime prompt</PaperTab></div></div></div>
        </PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide"><div className="ui-showcase-panel-heading"><span>04 / STICK & ANNOTATE</span><h2>Scrapbook objects</h2></div><div className="ui-showcase-notes"><StickyNote variant="topic" pinned><strong>Current topic</strong><p>Photography</p><small>confidence · 0.87</small></StickyNote><StickyNote variant="temporary"><strong>Temporary role</strong><p>Photographer</p></StickyNote><StickyNote variant="character"><strong>AI observation</strong><p>Ann noticed a black cat beside the window.</p></StickyNote><StickyNote variant="warning"><strong>Judge note</strong><p>Relationship boundary may need review.</p></StickyNote></div></PaperCard>

        <InspectorSection className="ui-showcase-panel ui-showcase-panel--wide" eyebrow="Technical evidence" title="Inspector section" description="Dense technical views use the same paper system with lower decoration intensity." actions={<StatusIndicator tone="success">Runtime healthy</StatusIndicator>}><div className="ui-showcase-inspector-grid"><div><span>Provider</span><strong>DeepSeek</strong></div><div><span>Model</span><strong>deepseek-v4-flash</strong></div><div><span>Latency</span><strong>182 ms</strong></div><div><span>Decision</span><strong>CONTINUE</strong></div></div></InspectorSection>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide"><div className="ui-showcase-panel-heading"><span>05 / EMPTY STATE</span><h2>Illustration-safe surface</h2></div><EmptyState illustration={<div className="ui-showcase-placeholder-art" aria-hidden="true">✦ ᓚᘏᗢ ✦</div>} title="Nothing filed here yet" description="This illustration slot may use generated raster artwork when organic anime scrapbook art is more appropriate than SVG." action={<Button variant="primary">Add note</Button>} /></PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide"><div className="ui-showcase-panel-heading"><span>06 / CHARACTER IDENTITY</span><h2>Avatar & character chips</h2></div><div className="ui-showcase-avatars"><Avatar name="Ann" size="lg" status="active" /><Avatar name="Ning" size="lg" status="listening" /><Avatar name="Zhi" size="lg" status="thinking" />{annChipVisible ? <CharacterChip name="Ann" onRemove={() => setAnnChipVisible(false)} /> : <Button size="sm" variant="ghost" onClick={() => setAnnChipVisible(true)}>Restore Ann chip</Button>}<CharacterChip name="Ning" /></div><SettingsRow title="Media understanding" description="Allow this character to inspect images when the runtime requires it." control={<Switch defaultChecked aria-label="Media understanding" />} /></PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide">
          <div className="ui-showcase-panel-heading"><span>07 / FEEDBACK & LAYERS</span><h2>Tooltip, popover, menu, confirm & loading</h2></div>
          <div className="ui-showcase-feedback-row"><Tooltip content="Small annotations can explain a control without changing its layout."><Button variant="secondary">Hover / focus me</Button></Tooltip><Popover label="Runtime note" trigger={<span>Open runtime note</span>} align="start"><StickyLabel variant="tool">TECHNICAL NOTE</StickyLabel><p>Popover content behaves like a small attached sheet, while critical actions stay normal controls.</p></Popover><Menu label="File actions" trigger={<Button variant="secondary">File actions</Button>}><MenuItem>Duplicate</MenuItem><MenuItem>Export</MenuItem><MenuItem destructive onClick={() => setConfirmOpen(true)}>Delete</MenuItem></Menu><Button variant="secondary" onClick={() => setDrawerOpen(true)}>Paper drawer</Button><Button variant="secondary" onClick={() => setModalOpen(true)}>Paper modal</Button><Button variant="danger" onClick={() => setConfirmOpen(true)}>Confirm dialog</Button><Spinner label="Loading runtime" /></div>
          <Divider label="loading surfaces" /><div className="ui-showcase-loading-grid"><Skeleton variant="circle" /><div><Skeleton width="42%" /><Skeleton width="78%" /><Skeleton width="61%" /></div><Skeleton variant="block" /></div><Divider label="feedback" /><div className="ui-showcase-toast-grid"><Toast tone="success" title="Saved">Character settings were filed successfully.</Toast><Toast tone="warning" title="Review suggested">The judge found a boundary worth checking.</Toast><Toast tone="danger" title="Provider failed">The request did not complete. No result was applied.</Toast></div>
        </PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide"><div className="ui-showcase-panel-heading"><span>08 / FUNCTIONAL SVG</span><h2>Deterministic icon set</h2></div><p className="ui-showcase-icon-note">Functional controls use code/SVG. Generated raster images are reserved for organic illustration, paper texture, collage, and anime artwork.</p><div className="ui-showcase-icon-grid">{functionalIcons.map((name) => <div key={name}><FunctionalIcon name={name} size={21} /><span>{name}</span></div>)}</div></PaperCard>

        <PaperCard className="ui-showcase-panel ui-showcase-panel--wide">
          <div className="ui-showcase-panel-heading"><span>09 / NOTEBOOK BRIDGE</span><h2>Production utilities</h2></div>
          <NotebookSection label="UTILITY" title="Notebook controls" guide="Compatibility controls that remain reusable while feature pages migrate into the canonical UI barrel." accent="mint">
            <div className="ui-showcase-utility-grid">
              <NotebookField label="Notebook input" guide="Single line"><NotebookInput defaultValue="Character Relay" /></NotebookField>
              <NotebookField label="Notebook select"><NotebookSelect defaultValue="ready"><option value="ready">Ready</option><option value="review">Needs review</option></NotebookSelect></NotebookField>
              <NotebookField className="ui-showcase-wide" label="Notebook textarea"><NotebookTextarea rows={3} defaultValue="Reusable compatibility surface." /></NotebookField>
            </div>
          </NotebookSection>
          <Pagination page={utilityPage} pages={3} total={componentCatalogTotal} onPage={setUtilityPage} />
        </PaperCard>
      </section>

      <ConfirmDialog open={confirmOpen} title="Delete this character file?" description="This is a destructive example shown only in the component library." confirmLabel="Delete" tone="danger" onCancel={() => setConfirmOpen(false)} onConfirm={() => setConfirmOpen(false)} />
      {drawerOpen && <PaperDrawer ariaLabel="Paper Drawer example" onClose={() => setDrawerOpen(false)}><div className="ui-showcase-overlay-demo"><h2>Attached side page</h2><p>Drawers keep editing context attached to the current notebook.</p><Button variant="primary" onClick={() => setDrawerOpen(false)}>Done</Button></div></PaperDrawer>}
      {modalOpen && <PaperModal ariaLabel="Paper Modal example" onClose={() => setModalOpen(false)}><div className="ui-showcase-overlay-demo"><h2>Focused paper modal</h2><p>Modals isolate a short decision without replacing the whole workspace.</p><Button variant="primary" onClick={() => setModalOpen(false)}>Done</Button></div></PaperModal>}
    </main>
  );
}
