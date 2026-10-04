import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useWebRoomSession } from "./WebRoomSessionProvider";
import { RoomCompanion } from "./RoomCompanion";
import { bindRoomPipLifecycle, requestRoomPip } from "./documentPip";
import { useI18n } from "./i18n";

const Context = createContext<{openCompanion: () => Promise<void>} | null>(null);
export function useRoomCompanion() {
  const context = useContext(Context);
  if (!context) throw new Error("RoomCompanionHost required");
  return context;
}
export function RoomCompanionHost({children, theme}: {children: ReactNode; theme: "light" | "dark"}) {
  const {state, session} = useWebRoomSession();
  const {language} = useI18n();
  const navigate = useNavigate();
  const [pip, setPip] = useState<Window | null>(null);
  const [floating, setFloating] = useState(false);
  const [fallbackReason, setFallbackReason] = useState("");
  const opening = useRef(false);
  const scope = useRef(0);
  const room = state.rooms.find(item => item.id === state.roomId);
  useEffect(() => {
    if (room?.enabled) return;
    scope.current++;
    setFloating(false);
    pip?.close();
    setPip(null);
  }, [room?.enabled, pip]);
  useEffect(() => {
    if (!pip) return;
    return bindRoomPipLifecycle(window, pip, () => setPip(null));
  }, [pip]);
  useEffect(() => () => { scope.current++; pip?.close(); }, [pip]);
  async function openCompanion() {
    if (!room?.enabled || opening.current) return;
    if (pip && !pip.closed) { pip.focus(); return; }
    const generation = scope.current;
    opening.current = true;
    try {
      const child = await requestRoomPip(window);
      if (generation !== scope.current) { child.close(); return; }
      setFloating(false);
      setPip(child);
    } catch {
      if (generation !== scope.current) return;
      setFallbackReason(language === "zh-CN"
        ? "此浏览器无法打开 Document PiP。浮窗仅在 Character Relay 页面内显示。"
        : "Document PiP could not open in this browser. This companion stays inside Character Relay.");
      setFloating(true);
    } finally { opening.current = false; }
  }
  function close() { scope.current++; setFloating(false); pip?.close(); setPip(null); }
  function openFull() {
    window.focus();
    navigate(`/rooms?${new URLSearchParams({room: state.roomId})}`);
  }
  const companion = <div className={`portal-theme-${theme}`}>
    <RoomCompanion state={state} session={session} onClose={close} onOpenFull={openFull} pip={Boolean(pip)} />
  </div>;
  return <Context.Provider value={{openCompanion}}>
    {children}
    {room?.enabled && pip && !pip.closed && createPortal(companion, pip.document.body)}
    {room?.enabled && floating && <div className="room-companion-floating">
      <p role="status" className="room-companion-fallback-note">{fallbackReason}</p>
      {companion}
    </div>}
  </Context.Provider>;
}
