// Options for the Thesis page dropdowns.
// `group` + `isGroup` let the location list show continents with their countries underneath.

export interface Option {
  value: string;
  label: string;
  group?: string; // continent a country belongs to
  isGroup?: boolean; // true for a continent row (selectable as a whole)
}

const opt = (label: string): Option => ({ value: label, label });

export const STAGE_OPTIONS: Option[] = [
  "Idea / Pre-product",
  "Pre-seed",
  "Seed",
  "Series A",
  "Series B",
  "Series C",
  "Series D+",
  "Growth / Late stage",
].map(opt);

export const SECTOR_OPTIONS: Option[] = [
  "AI / Machine Learning",
  "Developer Tools",
  "Infrastructure / Cloud",
  "Data / Analytics",
  "Cybersecurity",
  "Enterprise SaaS",
  "Fintech",
  "Healthtech",
  "Biotech",
  "Edtech",
  "E-commerce / Retail",
  "Consumer",
  "Climate / Energy",
  "Mobility / Logistics",
  "Robotics / Hardware",
  "Semiconductors",
  "Space / Defense",
  "Web3 / Crypto",
  "Gaming / Media",
  "Agritech / Foodtech",
  "Proptech / Construction",
  "HR / Future of Work",
  "Legal / Compliance",
  "Other",
].map(opt);

// Selecting this sector asks the user to describe it.
export const OTHER_SECTOR = "Other";

const CONTINENTS: Record<string, string[]> = {
  Asia: [
    "India", "China", "Japan", "Singapore", "South Korea", "Indonesia", "Vietnam", "Thailand",
    "Malaysia", "Philippines", "Bangladesh", "Pakistan", "Sri Lanka", "United Arab Emirates",
    "Saudi Arabia", "Israel", "Turkey",
  ],
  Europe: [
    "United Kingdom", "Germany", "France", "Netherlands", "Spain", "Italy", "Sweden", "Switzerland",
    "Ireland", "Poland", "Estonia", "Finland", "Denmark", "Norway", "Portugal", "Lithuania",
  ],
  "North America": ["United States", "Canada", "Mexico"],
  "South America": ["Brazil", "Argentina", "Colombia", "Chile"],
  Africa: ["Nigeria", "Kenya", "South Africa", "Egypt", "Ghana", "Morocco"],
  Oceania: ["Australia", "New Zealand"],
};

// Continent row first, then its countries.
export const LOCATION_OPTIONS: Option[] = Object.entries(CONTINENTS).flatMap(([continent, countries]) => [
  { value: `continent:${continent}`, label: continent, group: continent, isGroup: true },
  ...countries.map((c) => ({ value: `country:${c}`, label: c, group: continent })),
]);

// ---------- Advanced founder profile choices ----------

export interface Choice {
  value: string;
  label: string;
}

const withAny = (items: string[]): Choice[] => [
  { value: "any", label: "Any" },
  ...items.map((i) => ({ value: i, label: i })),
];

export const DEGREE_CHOICES = withAny(["B.Tech", "MS", "MBA", "PhD"]);
export const TIER_CHOICES = withAny(["IIT/IIM", "Ivy League", "Top 50 Global"]);
export const YEARS_CHOICES = withAny(["0-2", "2-5", "5-10", "10+"]);
export const AGE_CHOICES = withAny(["22-28", "28-35", "35+"]);
export const TEAM_SIZE_CHOICES = withAny(["1-3", "4-10", "10+"]);

export const TRI_CHOICES: Choice[] = [
  { value: "any", label: "Any" },
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

export const SOLO_CHOICES: Choice[] = [
  { value: "any", label: "Any" },
  { value: "solo", label: "Solo" },
  { value: "cofounded", label: "Co-founded" },
];

// Chip values are what gets sent to the backend (lowercase).
export const DOMAIN_CHIPS: Choice[] = [
  { value: "infra", label: "Infra" },
  { value: "ml", label: "ML" },
  { value: "fintech", label: "Fintech" },
  { value: "devtools", label: "DevTools" },
  { value: "saas", label: "SaaS" },
  { value: "hardware", label: "Hardware" },
  { value: "other", label: "Other" },
];

export const ACCELERATOR_CHIPS: Choice[] = [
  { value: "yc", label: "YC" },
  { value: "sequoia surge", label: "Sequoia Surge" },
  { value: "antler", label: "Antler" },
  { value: "lightspeed", label: "Lightspeed" },
  { value: "other", label: "Other" },
];
