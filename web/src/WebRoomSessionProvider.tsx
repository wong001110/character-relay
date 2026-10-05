import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { WebRoomSession } from "./webRoomSession";

const Context = createContext<WebRoomSession | null>(null);
export function WebRoomSessionProvider({children}: {children: ReactNode}) {
  const [session] = useState(() => new WebRoomSession());
  useEffect(() => {
    const cleanup = () => session.suspend();
    const updateOnline = () => session.setOnline(navigator.onLine !== false);
    updateOnline();
    window.addEventListener("pagehide", cleanup);
    window.addEventListener("offline", updateOnline);
    window.addEventListener("online", updateOnline);
    return () => {
      window.removeEventListener("pagehide", cleanup);
      window.removeEventListener("offline", updateOnline);
      window.removeEventListener("online", updateOnline);
      session.dispose();
    };
  }, [session]);
  return <Context.Provider value={session}>{children}</Context.Provider>;
}
export function useWebRoomSession() {
  const session = useContext(Context);
  if (!session) throw new Error("WebRoomSessionProvider required");
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  return {session, state};
}
