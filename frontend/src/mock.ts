// Mock data. Swap for real calls in api.ts (flip USE_MOCK or replace the function body).
import type { ExceptionItem, Memo, OutreachEmail, PipelineRun } from "./types";

export const mockRun: PipelineRun = {
  runId: "run_mock_1",
  thesis: "Seed-stage Indian dev-tools founders with prior infra experience",
  status: "running",
  steps: [
    { id: "search", label: "Search people and company graph", status: "done", detail: "42 candidates" },
    { id: "verify", label: "Verify identity and background", status: "running", detail: "18 of 42" },
    { id: "memo", label: "Generate memos", status: "pending" },
    { id: "escalate", label: "Escalate exceptions", status: "pending" },
    { id: "outreach", label: "Draft outreach for Meet decisions", status: "pending" },
  ],
};

export const mockMemos: Memo[] = [
  {
    id: "m1",
    company: "Example Co A",
    founder: "Founder One",
    decision: "Meet",
    summary: "Placeholder memo summary.",
    claims: [{ text: "Placeholder claim.", citations: ["c1"] }],
    citations: [{ id: "c1", source: "Crustdata People API" }],
  },
  {
    id: "m2",
    company: "Example Co B",
    founder: "Founder Two",
    decision: "Watch",
    summary: "Placeholder memo summary.",
    claims: [{ text: "Placeholder claim.", citations: ["c1"] }],
    citations: [{ id: "c1", source: "Crustdata Company API" }],
  },
  {
    id: "m3",
    company: "Example Co C",
    founder: "Founder Three",
    decision: "Pass",
    summary: "Placeholder memo summary.",
    claims: [{ text: "Placeholder claim.", citations: ["c1"] }],
    citations: [{ id: "c1", source: "Crustdata Company API" }],
  },
];

export const mockExceptions: ExceptionItem[] = [
  { id: "e1", company: "Example Co D", reason: "ambiguous_identity", detail: "Two profiles match this founder." },
  { id: "e2", company: "Example Co E", reason: "thin_signals", detail: "Not enough hiring or growth data." },
];

export const mockEmails: OutreachEmail[] = [
  {
    memoId: "m1",
    to: "founder.one@example.com",
    subject: "Placeholder subject",
    body: "Placeholder email body.",
  },
];
