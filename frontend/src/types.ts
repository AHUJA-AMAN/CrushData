// Types mirror the backend contract (POST /run, GET /status/{job_id}, GET /results/{job_id}).

export type Decision = "meet" | "pass" | "watch";
export type JobState = "running" | "awaiting_selection" | "done" | "failed" | "cancelled";
export type PipelineStage = "discovery" | "verification" | "signal_analysis" | "selection" | "memo_generation" | "done";
export type CitationConfidence = "verified" | "web" | "inferred" | "unavailable";

// ---------- POST /run ----------

// Every field is optional. Fields left on "Any" are omitted from the request.
export interface FounderProfileFilter {
  // Education
  institution?: string;
  degree_type?: string;
  field_of_study?: string;
  institution_tier?: string;
  // Work experience
  previous_company?: string;
  previous_role?: string;
  domain_expertise?: string[];
  years_experience?: string;
  previous_startup?: boolean;
  serial_founder?: boolean;
  previous_exit?: boolean;
  // Demographics
  nationality?: string;
  current_location?: string;
  age_range?: string;
  // Pedigree
  accelerator_alumni?: string[];
  notable_employer_alumni?: string;
  technical_founder?: boolean;
  research_publications?: boolean;
  // Team
  solo_vs_cofounded?: string;
  team_size?: string;
}

export interface RunRequest {
  thesis: {
    sector: string;
    geography: string;
    stage?: string;
    founder_keyword?: string;
    founder_profile: FounderProfileFilter;
  };
}

export interface RunResponse {
  job_id: string;
}

// ---------- GET /status/{job_id} ----------

export interface JobProgress {
  stage: PipelineStage;
  companies_found: number;
  companies_processed: number;
}

export interface JobStatus {
  job_id: string;
  status: JobState;
  progress: JobProgress;
  error?: string | null;
}

// ---------- GET /results/{job_id} ----------

export interface Founder {
  name: string;
  current_title: string;
  education: string;
  past_companies: string[];
  part_time_flag: boolean;
  business_email?: string | null; // listed only, never emailed
  email_status?: string | null;
}

export interface CompetitorRow {
  company: string;
  founded: number;
  focus: string;
  target_market: string;
  key_clients: string;
  funding: string;
}

export interface MemoSections {
  summary: string;
  problem: string;
  market: string;
  product: string[];
  competitive_landscape: CompetitorRow[];
  x_factor: string;
}

export interface Signals {
  headcount_now: number;
  headcount_6m_ago: number;
  headcount_growth_rate: string;
  recent_job_postings: number;
  hiring_departments: string[];
}

export interface Citation {
  claim: string;
  source: string;
  confidence: CitationConfidence;
}

export interface CompanyResult {
  company_name: string;
  domain: string;
  founded: number;
  location: string;
  stage: string;
  total_funding: string;
  decision: Decision;
  confidence: string; // "high" | "medium" | "low"
  founders: Founder[];
  memo_sections: MemoSections;
  signals: Signals;
  citations: Citation[];
  exception_flag: boolean;
  exception_reason: string | null;
  outreach_email: string | null;
}

// A company found by discovery, before any memo is written. The user picks which ones get a memo.
export interface Candidate {
  id: string;
  company_name: string;
  domain: string | null;
  location: string | null;
  founded: number | null;
  stage: string | null;
  total_funding: string | null;
  headcount: number | null;
  description: string | null;
  founders: { name: string; current_title: string | null }[];
}

export interface JobResults {
  job_id: string;
  status: JobState;
  progress?: JobProgress;
  candidates?: Candidate[];
  results: CompanyResult[];
}
