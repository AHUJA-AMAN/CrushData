// Mock data in exactly the shape of the backend contract.
// One "meet", one "watch" (with exception), one "pass".
import type { JobResults, JobStatus, PipelineStage } from "./types";

export const mockResults: JobResults = {
  job_id: "mock",
  status: "done",
  results: [
    {
      company_name: "Rocketship AI",
      domain: "rocketship.ai",
      founded: 2023,
      location: "Bangalore, India",
      stage: "seed",
      total_funding: "$500k",
      decision: "meet",
      confidence: "high",
      founders: [
        {
          name: "Priya Sharma",
          current_title: "Co-founder & CEO",
          education: "B.Tech CS, IIT Delhi, 2021",
          past_companies: ["Atlassian", "Razorpay"],
          part_time_flag: false,
        },
        {
          name: "Arjun Mehta",
          current_title: "Co-founder & CTO",
          education: "B.Tech CS, IIT Bombay, 2019",
          past_companies: ["Google", "Postman"],
          part_time_flag: false,
        },
      ],
      memo_sections: {
        summary:
          "Rocketship AI builds a full-stack developer infrastructure platform that lets seed-stage teams ship and scale backend services without a dedicated platform engineer.",
        problem:
          "**Early-stage teams lose weeks to infrastructure work instead of product work.**\n- Teams spend 25-30% of engineering time on deployment and tooling\n- Platform hires cost $120k+ per year in India's top metros\n- 60% of seed-stage outages trace back to misconfigured infrastructure\n- Existing tools target enterprises and are priced out of reach",
        market:
          "Global developer tools market of roughly $50B by 2030, growing at about 17% a year. India has over 5 million developers and the fastest-growing startup base in the region, with infrastructure spend rising as teams move to cloud-native stacks.",
        product: [
          "One-command environment setup and deploys",
          "Auto-scaling with cost guardrails",
          "Built-in observability and alerting",
          "Usage-based pricing for seed-stage teams",
        ],
        competitive_landscape: [
          {
            company: "Rocketship AI",
            founded: 2023,
            focus: "Full-stack dev infra",
            target_market: "Seed-stage startups",
            key_clients: "Stealth",
            funding: "$500k",
          },
          {
            company: "Competitor A",
            founded: 2020,
            focus: "CI/CD tooling",
            target_market: "Enterprise",
            key_clients: "Flipkart, Swiggy",
            funding: "$4M",
          },
        ],
        x_factor:
          "Co-founder Priya led infrastructure at Atlassian, and the team already has paying pilot customers before any institutional round.",
      },
      signals: {
        headcount_now: 12,
        headcount_6m_ago: 5,
        headcount_growth_rate: "140%",
        recent_job_postings: 4,
        hiring_departments: ["engineering", "sales"],
      },
      citations: [
        { claim: "140% headcount growth in 6 months", source: "Crustdata headcount data", confidence: "verified" },
        { claim: "Previously infra lead at Atlassian", source: "Crustdata career history", confidence: "verified" },
        { claim: "$50B market by 2030", source: "Web search", confidence: "web" },
        { claim: "Founders likely aged 26-28", source: "Graduation year 2021 + 22", confidence: "inferred" },
        { claim: "Named enterprise customers", source: "No public source found", confidence: "unavailable" },
      ],
      exception_flag: false,
      exception_reason: null,
      outreach_email:
        "Hi Priya,\n\nI came across Rocketship AI and your background at Atlassian caught my attention. Taking a developer-infrastructure product from zero to paying pilots in under a year is exactly the kind of progress we look for at seed.\n\nI'd love to hear how you're thinking about the next 12 months. Do you have 20 minutes this week or next?\n\nBest,\nAbhiram",
    },
    {
      company_name: "Stackwise",
      domain: "stackwise.dev",
      founded: 2024,
      location: "Pune, India",
      stage: "pre-seed",
      total_funding: "$120k",
      decision: "watch",
      confidence: "medium",
      founders: [
        {
          name: "Rohan Iyer",
          current_title: "Founder",
          education: "MS CS, IIIT Hyderabad, 2020",
          past_companies: ["Microsoft"],
          part_time_flag: true,
        },
      ],
      memo_sections: {
        summary:
          "Stackwise is building a dependency and build-cache tool that shortens CI times for monorepos.",
        problem:
          "**Large monorepos make CI slow and expensive.**\n- Median CI run exceeds 25 minutes for repos over 1M lines\n- Cache misses account for most wasted compute\n- Teams rarely have time to tune build graphs",
        market:
          "CI/CD tooling is a multi-billion dollar segment, though dominated by incumbents with bundled caching.",
        product: ["Remote build cache", "Dependency graph analysis", "GitHub Actions integration"],
        competitive_landscape: [
          {
            company: "Stackwise",
            founded: 2024,
            focus: "Monorepo build cache",
            target_market: "Mid-size engineering teams",
            key_clients: "None disclosed",
            funding: "$120k",
          },
          {
            company: "Competitor B",
            founded: 2019,
            focus: "Build acceleration",
            target_market: "Enterprise",
            key_clients: "Several Fortune 500",
            funding: "$22M",
          },
        ],
        x_factor: "Strong technical background, but signals suggest the founder may still be employed full-time.",
      },
      signals: {
        headcount_now: 2,
        headcount_6m_ago: 1,
        headcount_growth_rate: "100%",
        recent_job_postings: 0,
        hiring_departments: [],
      },
      citations: [
        { claim: "Founder employed at Microsoft until 2024", source: "Crustdata career history", confidence: "verified" },
        { claim: "Possible part-time founder", source: "Overlapping role dates", confidence: "inferred" },
        { claim: "Open-source activity", source: "No public GitHub profile found", confidence: "unavailable" },
      ],
      exception_flag: true,
      exception_reason: "Possible part-time founder, and two profiles match this founder's name.",
      outreach_email: null,
    },
    {
      company_name: "Cloudloop",
      domain: "cloudloop.io",
      founded: 2021,
      location: "Mumbai, India",
      stage: "seed",
      total_funding: "$1.2M",
      decision: "pass",
      confidence: "high",
      founders: [
        {
          name: "Neha Kapoor",
          current_title: "Co-founder & CEO",
          education: "MBA, IIM Ahmedabad, 2016",
          past_companies: ["Deloitte"],
          part_time_flag: false,
        },
      ],
      memo_sections: {
        summary: "Cloudloop offers managed cloud cost reporting for small businesses.",
        problem:
          "**Small businesses overspend on cloud and cannot see why.**\n- Cloud bills are hard to interpret without dedicated finance engineering\n- Existing tools assume large accounts",
        market: "Cloud cost management is crowded, with strong bundled offerings from the major cloud providers.",
        product: ["Monthly cost reports", "Budget alerts"],
        competitive_landscape: [
          {
            company: "Cloudloop",
            founded: 2021,
            focus: "Cloud cost reporting",
            target_market: "Small businesses",
            key_clients: "Local retailers",
            funding: "$1.2M",
          },
          {
            company: "Competitor C",
            founded: 2018,
            focus: "FinOps platform",
            target_market: "Mid-market",
            key_clients: "Several SaaS companies",
            funding: "$30M",
          },
        ],
        x_factor: "No infrastructure engineering background on the team.",
      },
      signals: {
        headcount_now: 6,
        headcount_6m_ago: 7,
        headcount_growth_rate: "-14%",
        recent_job_postings: 0,
        hiring_departments: [],
      },
      citations: [
        { claim: "Headcount down 14% in 6 months", source: "Crustdata headcount data", confidence: "verified" },
        { claim: "Cloud cost management is a crowded market", source: "Web search", confidence: "web" },
      ],
      exception_flag: false,
      exception_reason: null,
      outreach_email: null,
    },
  ],
};

// ---------- Simulated pipeline for the mock status endpoint ----------

const startedAt = new Map<string, number>();
export const registerMockJob = (jobId: string) => startedAt.set(jobId, Date.now());

const TOTAL = mockResults.results.length;
const PHASES: { stage: PipelineStage; endsAt: number }[] = [
  { stage: "discovery", endsAt: 1.5 },
  { stage: "verification", endsAt: 4 },
  { stage: "signal_analysis", endsAt: 7 },
  { stage: "memo_generation", endsAt: 10 },
];

export function mockStatus(jobId: string): JobStatus {
  const start = startedAt.get(jobId);
  const t = start === undefined ? 999 : (Date.now() - start) / 1000;

  if (t >= 10) {
    return {
      job_id: jobId,
      status: "done",
      progress: { stage: "done", companies_found: TOTAL, companies_processed: TOTAL },
    };
  }
  let from = 0;
  for (const phase of PHASES) {
    if (t < phase.endsAt) {
      const ratio = (t - from) / (phase.endsAt - from);
      const processed = phase.stage === "discovery" ? 0 : Math.floor(ratio * TOTAL);
      const found = phase.stage === "discovery" ? Math.max(1, Math.round(ratio * TOTAL)) : TOTAL;
      return {
        job_id: jobId,
        status: "running",
        progress: { stage: phase.stage, companies_found: found, companies_processed: processed },
      };
    }
    from = phase.endsAt;
  }
  return { job_id: jobId, status: "running", progress: { stage: "discovery", companies_found: 0, companies_processed: 0 } };
}
