from pydantic import BaseModel
from typing import Optional, List, Any
from enum import Enum


class Stage(str, Enum):
    pre_seed = "pre-seed"
    seed = "seed"
    series_a = "series-a"
    any = "any"


class FounderProfile(BaseModel):
    model_config = {"extra": "ignore"}

    domain_expertise: Optional[List[str]] = None
    previous_startup: Optional[bool] = None
    serial_founder: Optional[bool] = None
    previous_exit: Optional[bool] = None
    technical_founder: Optional[bool] = None
    institution: Optional[str] = None
    degree_type: Optional[str] = None
    field_of_study: Optional[str] = None
    institution_tier: Optional[str] = None
    previous_company: Optional[str] = None
    previous_role: Optional[str] = None
    years_of_experience: Optional[str] = None
    years_experience: Optional[str] = None        # frontend alias
    nationality: Optional[str] = None
    current_location: Optional[str] = None
    age_range: Optional[str] = None
    accelerator_alumni: Optional[List[str]] = None
    notable_employer: Optional[str] = None
    notable_employer_alumni: Optional[str] = None  # frontend alias
    solo_or_cofounded: Optional[str] = None
    solo_vs_cofounded: Optional[str] = None        # frontend alias
    research_publications: Optional[bool] = None   # frontend sends this
    team_size: Optional[str] = None


class Thesis(BaseModel):
    sector: str
    geography: str
    stage: Optional[str] = "any"           # accept any string, comma-separated ok
    founder_keyword: Optional[str] = None
    founder_profile: Optional[FounderProfile] = None

    model_config = {"extra": "ignore"}     # ignore unknown fields from frontend


class Confidence(str, Enum):
    verified = "verified"
    web = "web"
    inferred = "inferred"
    unavailable = "unavailable"


class Citation(BaseModel):
    claim: str
    source: str
    confidence: Confidence


class Founder(BaseModel):
    name: str
    current_title: Optional[str] = None
    education: Optional[str] = None
    past_companies: List[str] = []
    part_time_flag: bool = False


class CompetitorRow(BaseModel):
    company: str
    founded: Optional[str] = None
    focus: Optional[str] = None
    target_market: Optional[str] = None
    key_clients: Optional[str] = None
    funding: Optional[str] = None


class MemoSections(BaseModel):
    summary: str
    problem: str
    market: str | List[str]
    product: List[str]
    competitive_landscape: List[CompetitorRow]
    x_factor: str


class Signals(BaseModel):
    headcount_now: Optional[int] = None
    headcount_6m_ago: Optional[int] = None
    headcount_growth_rate: Optional[str] = None
    recent_job_postings: Optional[int] = None
    hiring_departments: List[str] = []


class Decision(str, Enum):
    meet = "meet"
    pass_ = "pass"
    watch = "watch"


class CompanyResult(BaseModel):
    company_name: str
    domain: Optional[str] = None
    founded: Optional[int] = None
    location: Optional[str] = None
    stage: Optional[str] = None
    total_funding: Optional[str] = None
    decision: Decision
    confidence: str
    founders: List[Founder] = []
    memo_sections: MemoSections
    signals: Signals
    citations: List[Citation] = []
    exception_flag: bool = False
    exception_reason: Optional[str] = None
    outreach_email: Optional[str] = None
