// The ONLY place the frontend talks to the backend.
// To go live: set VITE_USE_MOCK=false in frontend/.env.local (or replace a function body).
// Endpoint paths below are guesses until the agent owner shares the real contract.
import { mockEmails, mockExceptions, mockMemos, mockRun } from "./mock";
import type { ExceptionItem, Memo, OutreachEmail, PipelineRun } from "./types";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

const delay = <T,>(value: T, ms = 300) => new Promise<T>((r) => setTimeout(() => r(value), ms));

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function startRun(thesis: string): Promise<{ runId: string }> {
  return USE_MOCK
    ? delay({ runId: mockRun.runId })
    : http("/runs", { method: "POST", body: JSON.stringify({ thesis }) });
}

export function getRun(runId: string): Promise<PipelineRun> {
  return USE_MOCK ? delay(mockRun) : http(`/runs/${runId}`);
}

export function getMemos(runId: string): Promise<Memo[]> {
  return USE_MOCK ? delay(mockMemos) : http(`/runs/${runId}/memos`);
}

export function getExceptions(runId: string): Promise<ExceptionItem[]> {
  return USE_MOCK ? delay(mockExceptions) : http(`/runs/${runId}/exceptions`);
}

export function getEmails(runId: string): Promise<OutreachEmail[]> {
  return USE_MOCK ? delay(mockEmails) : http(`/runs/${runId}/emails`);
}
