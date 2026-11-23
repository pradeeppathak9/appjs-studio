import { createContext, useContext } from "react";
import type { Me } from "../api/types";

export const SessionContext = createContext<Me | null>(null);

/** The signed-in user. Only valid below the auth gate. */
export function useSession(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error("useSession used outside the auth gate");
  return me;
}
