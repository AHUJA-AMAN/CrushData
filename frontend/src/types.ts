// PLACEHOLDER shapes. Replace with the real API contract once the agent owner shares it.

export type Decision = "Meet" | "Pass" | "Watch";

export type RunStatus = "idle" | "running" | "done" | "error";

export interface Citation {
  id: string;
  source: string; // e.g. "Crustdata People API"
  url?: string;
}

export interface Claim {
  text: string;
  citations: string[]; // Citation ids
}

export interface Memo {
  id: string;
  company: string;
  founder: string;
  decision: Decision;
  summary: string;
  claims: Claim[];
  citations: Citation[];
}

export interface PipelineStep {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
  detail?: string;
}

export interface PipelineRun {
  runId: string;
  thesis: string;
  status: RunStatus;
  steps: PipelineStep[];
}

export interface ExceptionItem {
  id: string;
  company: string;
  reason: "conflicting_data" | "ambiguous_identity" | "thin_signals";
  detail: string;
}

export interface OutreachEmail {
  memoId: string;
  to: string;
  subject: string;
  body: string;
}
