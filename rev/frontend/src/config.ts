/** Where the API lives. Set VITE_API_URL at build time; the default is production. */
export const API_BASE: string = (import.meta.env.VITE_API_URL || "https://api.autorev.postkaro.app").replace(/\/$/, "");
