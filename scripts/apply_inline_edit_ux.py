from pathlib import Path


deployment = Path("web/src/DeploymentCenter.tsx")
text = deployment.read_text(encoding="utf-8")
old = '''    setDeploymentOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
'''
new = '''    setDeploymentOpen(true);
'''
if old not in text:
    raise SystemExit("Deployment scroll-to-top anchor not found")
deployment.write_text(text.replace(old, new, 1), encoding="utf-8")

css_path = Path("web/src/discordServerProfiles.css")
css = css_path.read_text(encoding="utf-8")
addition = '''

.expression-resource-card.is-editing {
  border-color: rgba(112, 86, 158, 0.46);
  background: #f7f1ff;
  box-shadow: 0 7px 18px rgba(75, 57, 94, 0.1);
}

.expression-inline-editor {
  grid-column: 1 / -1;
  margin: -2px 0 10px;
  scroll-margin-block: 24px;
  animation: expression-inline-editor-in 180ms ease both;
}

@keyframes expression-inline-editor-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .expression-inline-editor {
    animation-duration: 1ms;
  }
}
'''
if ".expression-inline-editor" not in css:
    css_path.write_text(css + addition, encoding="utf-8")
