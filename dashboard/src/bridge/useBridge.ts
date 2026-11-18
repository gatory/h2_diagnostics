import { createContext, useContext, useSyncExternalStore } from "react";
import type { BridgeClient, BridgeState } from "./BridgeClient";

/** The one BridgeClient, provided by <App>; components get it with useBridgeClient(). */
export const BridgeContext = createContext<BridgeClient | null>(null);

export function useBridgeClient(): BridgeClient {
  const client = useContext(BridgeContext);
  if (!client) throw new Error("useBridgeClient() outside <BridgeContext.Provider>");
  return client;
}

/**
 * Re-renders the calling component on every change (each snapshot, ~25/s).
 * Fine for text panels; the 3D view reads client.latest per frame instead.
 */
export function useBridge(): BridgeState {
  const client = useBridgeClient();
  return useSyncExternalStore(client.subscribe, client.getState);
}
