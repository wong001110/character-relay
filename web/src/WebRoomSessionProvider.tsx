import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { WebRoomSession } from "./webRoomSession";

const Context = createContext<WebRoomSession | null>(null);
export function WebRoomSessionProvider({children}: {children: ReactNode}) {
  const [session] = useState(() => new WebRoomSession());
  useEffect(() => {
    const cleanup = () => session.suspend();
    window.addEventListener("pagehide", cleanup);
    return () => { window.removeEventListener("pagehide", cleanup); session.dispose(); };
  }, [session]);
  return <Context.Provider value={session}>{children}</Context.Provider>;
}
export function useWebRoomSession() {
  const session = useContext(Context);
  if (!session) throw new Error("WebRoomSessionProvider required");
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  return {session, state};
}
