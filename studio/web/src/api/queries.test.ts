import { describe, expect, it } from "vitest";
import { isTerminal, jobListRefetchInterval, jobRefetchInterval } from "./queries";
import type { Job, JobStatus } from "./types";

const job = (status: JobStatus) => ({ id: status, status }) as Job;

describe("job polling", () => {
  it("polls a job every 1.5 s until it succeeds or fails", () => {
    expect(jobRefetchInterval(undefined)).toBe(1500);
    expect(jobRefetchInterval(job("queued"))).toBe(1500);
    expect(jobRefetchInterval(job("running"))).toBe(1500);
    expect(jobRefetchInterval(job("succeeded"))).toBe(false);
    expect(jobRefetchInterval(job("failed"))).toBe(false);
    expect(isTerminal(job("failed"))).toBe(true);
  });

  it("polls the list fast only while something is in flight", () => {
    expect(jobListRefetchInterval([job("succeeded"), job("running")])).toBe(2000);
    expect(jobListRefetchInterval([job("succeeded"), job("failed")])).toBe(15000);
    expect(jobListRefetchInterval(undefined)).toBe(15000);
  });
});
