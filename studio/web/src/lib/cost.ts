import type { ModelPrice, PriceList } from "../api/types";

export type CostInput = {
  media_type: "image" | "video";
  provider: string;
  model: string;
  allowed_models: string[];
  n: number;
  duration_seconds: string | number | null;
};

export type RunCost = {
  /** model cost of one run in US dollars, using the most expensive priced model a run may use */
  usd: number;
  /** the model that sets `usd` */
  model: string;
  /** models a run may use that have no price on file */
  missing: string[];
  /** credits that cover `usd` at the price list's `credit_usd` */
  suggested: number;
};

export function priceOf(prices: PriceList, provider: string, model: string): ModelPrice | undefined {
  return (prices.models ?? []).find((m) => m.provider === provider && m.model === model);
}

function unitsPerRun(price: ModelPrice, t: CostInput): number | null {
  if (price.unit === "second") {
    const s = Number(t.duration_seconds);
    return t.duration_seconds !== null && t.duration_seconds !== "" && s > 0 ? s : null;
  }
  return Math.max(1, Number(t.n) || 1);
}

/** Estimated model cost of one run of a template, or null when no model it may use has a price. */
export function runCost(prices: PriceList, t: CostInput): RunCost | null {
  const models = [...new Set([t.model, ...t.allowed_models].map((m) => m.trim()).filter(Boolean))];
  let best: { usd: number; model: string } | null = null;
  const missing: string[] = [];
  for (const model of models) {
    const price = priceOf(prices, t.provider, model);
    const units = price ? unitsPerRun(price, t) : null;
    if (!price || units === null) {
      missing.push(model);
      continue;
    }
    const usd = price.usd * units;
    if (!best || usd > best.usd) best = { usd, model };
  }
  if (!best) return null;
  return { ...best, missing, suggested: suggestedCredits(best.usd, prices.credit_usd) };
}

export function suggestedCredits(usd: number, creditUsd: number): number {
  if (usd <= 0) return 0;
  return Math.ceil(usd / creditUsd - 1e-9);
}

export function formatUsd(usd: number): string {
  if (usd === 0) return "$0";
  return `$${usd < 0.01 ? usd.toFixed(4) : usd.toFixed(3).replace(/0$/, "")}`;
}
