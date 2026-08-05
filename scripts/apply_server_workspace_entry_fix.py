from pathlib import Path

path = Path("web/src/DeploymentCenter.tsx")
text = path.read_text(encoding="utf-8")

old = 'import { useEffect, useMemo, useState, type FormEvent } from "react";\n'
new = 'import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";\n'
if old not in text:
    raise RuntimeError("React import not found")
text = text.replace(old, new, 1)

old = '''  const [selectedServerProfileId, setSelectedServerProfileId] = useState(() =>
    new URLSearchParams(window.location.search).get("server_profile") ?? ""
  );

'''
new = '''  const [selectedServerProfileId, setSelectedServerProfileId] = useState(() =>
    new URLSearchParams(window.location.search).get("server_profile") ?? ""
  );
  const serverSelectionInitialized = useRef(false);

'''
if old not in text:
    raise RuntimeError("Server selection state not found")
text = text.replace(old, new, 1)

old = '''  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedServerProfileId) url.searchParams.set("server_profile", selectedServerProfileId);
    else url.searchParams.delete("server_profile");
    window.history.replaceState({}, "", url);
    setDeploymentOpen(false);
    setEditingDeployment(null);
    setDeploymentPage(1);
  }, [selectedServerProfileId]);
'''
new = '''  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedServerProfileId) url.searchParams.set("server_profile", selectedServerProfileId);
    else url.searchParams.delete("server_profile");
    window.history.replaceState({}, "", url);
    if (serverSelectionInitialized.current) {
      setDeploymentOpen(false);
      setEditingDeployment(null);
    }
    if (selectedServerProfileId) serverSelectionInitialized.current = true;
    setDeploymentPage(1);
  }, [selectedServerProfileId]);
'''
if old not in text:
    raise RuntimeError("Server URL effect not found")
text = text.replace(old, new, 1)

old = '''  const selectedWorkspaceCatalog = selectedWorkspaceProfile
    ? serverCatalog.find(
        (server) =>
          server.connection_id === selectedWorkspaceProfile.connection_id &&
          server.guild_id === selectedWorkspaceProfile.guild_id
      )
    : undefined;
  const selectedConnection = connections.find((item) => item.id === draftConnectionId);
'''
new = '''  const selectedWorkspaceCatalog = selectedWorkspaceProfile
    ? serverCatalog.find(
        (server) =>
          server.connection_id === selectedWorkspaceProfile.connection_id &&
          server.guild_id === selectedWorkspaceProfile.guild_id
      )
    : undefined;

  useEffect(() => {
    if (!selectedWorkspaceProfile || editingDeployment) return;
    setDraftConnectionId(selectedWorkspaceProfile.connection_id);
    setDraftServerProfileId(selectedWorkspaceProfile.id);
  }, [
    editingDeployment,
    selectedWorkspaceProfile?.connection_id,
    selectedWorkspaceProfile?.id
  ]);

  const selectedConnection = connections.find((item) => item.id === draftConnectionId);
'''
if old not in text:
    raise RuntimeError("Selected Server derivation not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
