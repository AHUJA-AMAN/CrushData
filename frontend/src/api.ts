// The ONLY place the frontend talks to the backend.
// Mock mode is on by default. To use the real backend, set VITE_USE_MOCK=false in frontend/.env.local
// (see .env.example). Each function has a mock branch and a real branch, so swapping is one line.
import { mockResults, mockStatus, registerMockJob } from "./mock";
import type { JobResults, JobStatus, RunRequest, RunResponse } from "./types";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

const delay = <T,>(value: T, ms = 300) => new Promise<T>((r) => setTimeout(() => r(value), ms));

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// POST /run
export function startRun(req: RunRequest): Promise<RunResponse> {
  if (USE_MOCK) {
    const job_id = `mock_${Math.random().toString(36).slice(2, 8)}`;
    registerMockJob(job_id);
    return delay({ job_id });
  }
  return http("/run", { method: "POST", body: JSON.stringify(req) });
}

// GET /status/{job_id}
export function getStatus(jobId: string): Promise<JobStatus> {
  return USE_MOCK ? delay(mockStatus(jobId), 150) : http(`/status/${jobId}`);
}

// GET /results/{job_id}
export function getResults(jobId: string): Promise<JobResults> {
  return USE_MOCK ? delay({ ...mockResults, job_id: jobId }) : http(`/results/${jobId}`);
}
