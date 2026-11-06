from pydantic import BaseModel, field_validator
from typing import Optional, List, Any, Union
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
    # LLM/Crustdata often send numbers for text fields (e.g. funding 12000000); accept them as text
    model_config = {"coerce_numbers_to_str": True}

    claim: str
    source: str
    confidence: Confidence


class Founder(BaseModel):
    # LLM/Crustdata often send numbers for text fields (e.g. funding 12000000); accept them as text
    model_config = {"coerce_numbers_to_str": True}

    name: str
    current_title: Optional[str] = None
    education: Optional[str] = None
    past_companies: List[str] = []
    part_time_flag: bool = False
    business_email: Optional[str] = None   # listed in the UI only; outreach goes to demo inboxes
    email_status: Optional[str] = None


class CompetitorRow(BaseModel):
    # LLM/Crustdata often send numbers for text fields (e.g. funding 12000000); accept them as text
    model_config = {"coerce_numbers_to_str": True}

    company: str
    founded: Optional[Union[int, str]] = None  # frontend expects a year number
    focus: Optional[str] = None
    target_market: Optional[str] = None
    key_clients: Optional[str] = None
    funding: Optional[str] = None


class MemoSections(BaseModel):
    # LLM/Crustdata often send numbers for text fields (e.g. funding 12000000); accept them as text
    model_config = {"coerce_numbers_to_str": True}

    summary: str
    problem: str
    market: str
    product: List[str]
    competitive_landscape: List[CompetitorRow]
    x_factor: str

    # Gemini sometimes answers a text section with a list of bullets (or product with one string).
    # Reshape instead of failing the whole memo; the frontend renders "- " lines as bullets.
    @field_validator("summary", "problem", "market", "x_factor", mode="before")
    @classmethod
    def _join_bullets(cls, v):
        if isinstance(v, list):
            return "\n".join(f"- {x}" for x in v if x not in (None, ""))
        return "" if v is None else v

    @field_validator("product", mode="before")
    @classmethod
    def _wrap_product(cls, v):
        if v is None:
            return []
        return [v] if isinstance(v, str) else v


class Signals(BaseModel):
    # LLM/Crustdata often send numbers for text fields (e.g. funding 12000000); accept them as text
    model_config = {"coerce_numbers_to_str": True}

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
    # LLM/Crustdata often send numbers for text fields (e.g. funding 12000000); accept them as text
    model_config = {"coerce_numbers_to_str": True}

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
