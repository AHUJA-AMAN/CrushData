// Thesis form state and its conversion into the POST /run body.
import { OTHER_SECTOR } from "./data/thesisOptions";
import type { FounderProfileFilter, RunRequest } from "./types";

export type Tri = "any" | "yes" | "no";

export interface SimpleForm {
  sectors: string[];
  sectorOther: string; // description, used when the "Other" sector is selected
  geographies: string[]; // values like "continent:Asia" or "country:India"
  stages: string[];
  keyword: string;
}

export interface AdvancedForm {
  institution: string;
  degreeType: string;
  fieldOfStudy: string;
  institutionTier: string;
  previousCompany: string;
  previousRole: string;
  domainExpertise: string[];
  yearsExperience: string;
  previousStartup: Tri;
  serialFounder: Tri;
  previousExit: Tri;
  nationality: string;
  currentLocation: string;
  ageRange: string;
  acceleratorAlumni: string[];
  notableEmployer: string;
  technicalFounder: Tri;
  research: Tri;
  soloVsCofounded: string; // "any" | "solo" | "cofounded"
  teamSize: string;
}

export const EMPTY_SIMPLE: SimpleForm = { sectors: [], sectorOther: "", geographies: [], stages: [], keyword: "" };

export const EMPTY_ADVANCED: AdvancedForm = {
  institution: "",
  degreeType: "any",
  fieldOfStudy: "",
  institutionTier: "any",
  previousCompany: "",
  previousRole: "",
  domainExpertise: [],
  yearsExperience: "any",
  previousStartup: "any",
  serialFounder: "any",
  previousExit: "any",
  nationality: "",
  currentLocation: "",
  ageRange: "any",
  acceleratorAlumni: [],
  notableEmployer: "",
  technicalFounder: "any",
  research: "any",
  soloVsCofounded: "any",
  teamSize: "any",
};

const text = (s: string) => s.trim();
const picked = (s: string) => (s && s !== "any" ? s : undefined);
const tri = (t: Tri) => (t === "yes" ? true : t === "no" ? false : undefined);

/** Builds founder_profile with only the fields the user actually set. */
export function buildFounderProfile(a: AdvancedForm): FounderProfileFilter {
  const draft: FounderProfileFilter = {
    institution: text(a.institution) || undefined,
    degree_type: picked(a.degreeType),
    field_of_study: text(a.fieldOfStudy) || undefined,
    institution_tier: picked(a.institutionTier),
    previous_company: text(a.previousCompany) || undefined,
    previous_role: text(a.previousRole) || undefined,
    domain_expertise: a.domainExpertise.length ? a.domainExpertise : undefined,
    years_experience: picked(a.yearsExperience),
    previous_startup: tri(a.previousStartup),
    serial_founder: tri(a.serialFounder),
    previous_exit: tri(a.previousExit),
    nationality: text(a.nationality) || undefined,
    current_location: text(a.currentLocation) || undefined,
    age_range: picked(a.ageRange),
    accelerator_alumni: a.acceleratorAlumni.length ? a.acceleratorAlumni : undefined,
    notable_employer_alumni: text(a.notableEmployer) || undefined,
    technical_founder: tri(a.technicalFounder),
    research_publications: tri(a.research),
    solo_vs_cofounded: picked(a.soloVsCofounded),
    team_size: picked(a.teamSize),
  };
  return Object.fromEntries(Object.entries(draft).filter(([, v]) => v !== undefined)) as FounderProfileFilter;
}

/** How many advanced filters are set (shown on the "Advanced" toggle). */
export function countActive(a: AdvancedForm): number {
  return Object.keys(buildFounderProfile(a)).length;
}

const geoLabel = (v: string) => (v.includes(":") ? v.slice(v.indexOf(":") + 1) : v);

/** Multiple selections are sent as one comma-separated string, matching the contract's string fields. */
export function buildRunRequest(simple: SimpleForm, advanced: AdvancedForm): RunRequest {
  const stage = simple.stages.map((s) => s.toLowerCase()).join(", ");
  return {
    thesis: {
      // "Other" is replaced by what the user typed.
      sector: simple.sectors
        .map((s) => (s === OTHER_SECTOR ? text(simple.sectorOther) || "other" : s.toLowerCase()))
        .join(", "),
      geography: simple.geographies.map(geoLabel).join(", "),
      ...(stage ? { stage } : {}),
      ...(text(simple.keyword) ? { founder_keyword: text(simple.keyword) } : {}),
      founder_profile: buildFounderProfile(advanced),
    },
  };
}
