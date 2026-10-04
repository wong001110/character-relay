import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useWebRoomSession } from "./WebRoomSessionProvider";
import { RoomCompanion } from "./RoomCompanion";
import { bindRoomPipLifecycle, DEFAULT_ROOM_PIP_SIZE, isRoomPipSize, readRoomPipSize, requestRoomPip, resizeRoomPip, type RoomPipSize } from "./documentPip";
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
  const preferredSize = useRef<RoomPipSize>({ ...DEFAULT_ROOM_PIP_SIZE });
  const measurement = useRef<{ window: Window; size: RoomPipSize | null; remembering: boolean } | null>(null);
  const [windowSize, setWindowSize] = useState<RoomPipSize>({ ...DEFAULT_ROOM_PIP_SIZE });
  const room = state.rooms.find(item => item.id === state.roomId);
  function observeSize(child: Window, remember = true) {
    if (measurement.current?.window !== child) return;
    const actual = readRoomPipSize(child);
    if (!actual) return;
    const previous = measurement.current.size;
    if (remember && measurement.current.remembering && previous && isRoomPipSize(actual)
      && (actual.width !== previous.width || actual.height !== previous.height)) {
      preferredSize.current = actual;
    }
    measurement.current.size = actual;
    setWindowSize(actual);
  }
  useEffect(() => {
    if (state.authenticated && room?.enabled) return;
    scope.current++;
    preferredSize.current = { ...DEFAULT_ROOM_PIP_SIZE };
    measurement.current = null;
    setWindowSize({ ...DEFAULT_ROOM_PIP_SIZE });
    setFloating(false);
    pip?.close();
    setPip(null);
  }, [state.authenticated, room?.enabled, pip]);
  useEffect(() => {
    if (!pip) return;
    const generation = scope.current;
    let initialObservationDone = false;
    let quietTimer: number | undefined;
    let deadlineTimer: number | undefined;
    const clearInitialTimers = () => {
      pip.clearTimeout(quietTimer);
      pip.clearTimeout(deadlineTimer);
    };
    const finishInitialMeasurement = () => {
      if (generation !== scope.current || measurement.current?.window !== pip || pip.closed) {
        clearInitialTimers();
        return;
      }
      if (!measurement.current.remembering) {
        if (!initialObservationDone) return;
        // requestWindow may report content dimensions before any native bounds.
        // Keep the preference protected until a usable native baseline exists.
        if (!readRoomPipSize(pip) || !Number.isInteger(pip.outerWidth) || pip.outerWidth <= 0
          || !Number.isInteger(pip.outerHeight) || pip.outerHeight <= 0) return;
        observeSize(pip, false);
        measurement.current.remembering = true;
      }
      clearInitialTimers();
    };
    const waitForInitialQuiet = () => {
      pip.clearTimeout(quietTimer);
      quietTimer = pip.setTimeout(finishInitialMeasurement, 100);
    };
    const onResize = () => {
      if (generation !== scope.current) return;
      observeSize(pip);
      if (measurement.current?.remembering) clearInitialTimers();
      else waitForInitialQuiet();
    };
    pip.addEventListener("resize", onResize);
    observeSize(pip, false);
    // Native opening adjustments arrived about 400ms after requestWindow in
    // Chromium/Xfwm4. Observe the full 500ms before remembering manual changes;
    // opening updates Current without replacing the user's selected size.
    waitForInitialQuiet();
    deadlineTimer = pip.setTimeout(() => {
      initialObservationDone = true;
      finishInitialMeasurement();
    }, 500);
    const dispose = bindRoomPipLifecycle(window, pip, () => {
      clearInitialTimers();
      if (generation === scope.current) observeSize(pip);
      if (measurement.current?.window === pip) measurement.current = null;
      setPip(null);
    });
    return () => { clearInitialTimers(); pip.removeEventListener("resize", onResize); dispose(); };
  }, [pip]);
  useEffect(() => () => { scope.current++; pip?.close(); }, [pip]);
  async function openCompanion() {
    if (!room?.enabled || opening.current) return;
    if (pip && !pip.closed) { pip.focus(); return; }
    const generation = scope.current;
    opening.current = true;
    try {
      const child = await requestRoomPip(window, preferredSize.current);
      if (generation !== scope.current) { child.close(); return; }
      const actual = readRoomPipSize(child);
      measurement.current = { window: child, size: actual, remembering: false };
      setWindowSize(actual || preferredSize.current);
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
  function close() {
    if (pip) observeSize(pip);
    scope.current++;
    measurement.current = null;
    setFloating(false);
    pip?.close();
    setPip(null);
  }
  function applySize(size: RoomPipSize): boolean {
    if (!pip || !isRoomPipSize(size) || !resizeRoomPip(pip, size)) return false;
    preferredSize.current = { ...size };
    if (measurement.current?.window === pip) measurement.current.remembering = true;
    observeSize(pip, false);
    return true;
  }
  function openFull() {
    window.focus();
    navigate(`/rooms?${new URLSearchParams({room: state.roomId})}`);
  }
  const companion = <div className={`portal-theme-${theme}`}>
    <RoomCompanion state={state} session={session} onClose={close} onOpenFull={openFull} pip={Boolean(pip)} sizeControls={pip ? { size: windowSize, preferredSize: preferredSize.current, onResize: applySize } : undefined} />
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
