declare global {
  interface Window {
    RESTYLE_CONFIG?: { appKey?: string };
  }
}

/** The Studio app key: from /config.js at runtime (Docker), else VITE_APP_KEY (development). */
export function appKey(): string {
  return window.RESTYLE_CONFIG?.appKey || import.meta.env.VITE_APP_KEY || "";
}
