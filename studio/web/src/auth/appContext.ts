import { createContext, useContext } from "react";
import type { MyApp } from "../api/types";

export const AppContext = createContext<MyApp | null>(null);

/** The app of the current /apps/:appId page, with the signed-in user's role in it. */
export function useCurrentApp(): MyApp {
  const app = useContext(AppContext);
  if (!app) throw new Error("useCurrentApp used outside /apps/:appId");
  return app;
}
