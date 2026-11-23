/** The signed-in session and this browser's device id, kept in localStorage. Components subscribe
 * with `useSession()`; storage failures (private mode, blocked storage) fall back to memory. */
import { useSyncExternalStore } from "react";
import type { Account } from "./api";

const TOKEN = "restyle.token";
const USER = "restyle.user";
const DEVICE = "restyle.device";

const memory = new Map<string, string>();
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return memory.get(key) ?? null;
  }
}
function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    if (value === null) memory.delete(key);
    else memory.set(key, value);
  }
}

const listeners = new Set<() => void>();
let snapshot: { token: string | null; user: Account | null } = load();

function load() {
  const token = read(TOKEN);
  let user: Account | null;
  try {
    user = token ? JSON.parse(read(USER) ?? "null") : null;
  } catch {
    user = null;
  }
  return { token, user };
}

function changed() {
  snapshot = load();
  listeners.forEach((l) => l());
}

export const session = {
  token: () => snapshot.token,
  deviceId(): string {
    let id = read(DEVICE);
    if (!id) {
      id = "web-" + crypto.randomUUID();
      write(DEVICE, id);
    }
    return id;
  },
  signIn(token: string, user: Account) {
    write(TOKEN, token);
    write(USER, JSON.stringify(user));
    changed();
  },
  setUser(user: Account) {
    if (!snapshot.token) return;
    write(USER, JSON.stringify(user));
    changed();
  },
  clear() {
    write(TOKEN, null);
    write(USER, null);
    changed();
  },
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

export function useSession() {
  return useSyncExternalStore(session.subscribe, () => snapshot);
}
