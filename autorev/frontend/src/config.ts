/** Where the API lives. Set VITE_API_URL at build time. */
export const API_BASE: string = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
