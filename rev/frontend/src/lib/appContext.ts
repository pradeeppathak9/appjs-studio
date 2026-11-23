import { useOutletContext } from "react-router";
import type { App } from "../api/types";

/** What every page under /apps/:appId receives (the legacy pages read the same shape). */
export type AppContext = { app: App; setApp: (app: App) => void };

export function useAppContext() {
  return useOutletContext<AppContext>();
}
