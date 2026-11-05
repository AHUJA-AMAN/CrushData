import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startRun } from "../api";
import MultiSelect from "../components/MultiSelect";
import { ChipGroup, Segmented, SelectField, TextField } from "../components/fields";
import {
  ACCELERATOR_CHIPS,
  AGE_CHOICES,
  DEGREE_CHOICES,
  DOMAIN_CHIPS,
  LOCATION_OPTIONS,
  OTHER_SECTOR,
  SECTOR_OPTIONS,
  SOLO_CHOICES,
  STAGE_OPTIONS,
  TEAM_SIZE_CHOICES,
  TIER_CHOICES,
  TRI_CHOICES,
  YEARS_CHOICES,
} from "../data/thesisOptions";
import {
  EMPTY_ADVANCED,
  EMPTY_SIMPLE,
  buildRunRequest,
  countActive,
  type AdvancedForm,
  type SimpleForm,
  type Tri,
} from "../form";
import { setJobId } from "../jobStore";

export default function ThesisInput() {
  const [simple, setSimple] = useState<SimpleForm>(EMPTY_SIMPLE);
  const [adv, setAdv] = useState<AdvancedForm>(EMPTY_ADVANCED);
  const [advOpen, setAdvOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const setS = <K extends keyof SimpleForm>(k: K) => (v: SimpleForm[K]) => setSimple((f) => ({ ...f, [k]: v }));
  const setA = <K extends keyof AdvancedForm>(k: K) => (v: AdvancedForm[K]) => setAdv((f) => ({ ...f, [k]: v }));
  const setTri = (k: keyof AdvancedForm) => (v: string) => setAdv((f) => ({ ...f, [k]: v as Tri }));

  const activeCount = countActive(adv);
  const otherSelected = simple.sectors.includes(OTHER_SECTOR);
  const otherMissing = otherSelected && simple.sectorOther.trim() === "";
  const canRun = simple.sectors.length > 0 && simple.geographies.length > 0 && !otherMissing;

  function reset() {
    setSimple(EMPTY_SIMPLE);
    setAdv(EMPTY_ADVANCED);
    setError(null);
  }

  async function run() {
    if (!canRun) return;
    setBusy(true);
    setError(null);
    try {
      const { job_id } = await startRun(buildRunRequest(simple, adv));
      setJobId(job_id);
      navigate("/status");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>
        Find your next <span className="accent">founder</span>
      </h1>
      <p className="muted lead">Describe your thesis. The agent does the sourcing and diligence.</p>

      <div className="panel">
        <div className="filters">
          <MultiSelect
            label="Sector"
            placeholder="Select sectors"
            options={SECTOR_OPTIONS}
            value={simple.sectors}
            onChange={setS("sectors")}
            searchable
            required
            describe={{
              optionValue: OTHER_SECTOR,
              label: "Describe the sector",
              placeholder: "e.g. Quantum computing tooling",
              value: simple.sectorOther,
              onChange: setS("sectorOther"),
            }}
          />
          <MultiSelect
            label="Geography"
            placeholder="Select countries or continents"
            options={LOCATION_OPTIONS}
            value={simple.geographies}
            onChange={setS("geographies")}
            searchable
            required
          />
          <MultiSelect
            label="Stage"
            placeholder="Any stage"
            options={STAGE_OPTIONS}
            value={simple.stages}
            onChange={setS("stages")}
          />
          <TextField
            label="Founder keyword"
            placeholder="e.g. prior infra experience"
            value={simple.keyword}
            onChange={setS("keyword")}
          />
        </div>

        {/* ---------- Advanced founder profile ---------- */}
        <div className="advanced">
          <button
            type="button"
            className="adv-toggle"
            aria-expanded={advOpen}
            aria-controls="advanced-body"
            onClick={() => setAdvOpen((o) => !o)}
          >
            <span className={`chevron${advOpen ? " up" : ""}`} aria-hidden="true" />
            <span>Advanced founder profile</span>
            <span className={`count${activeCount ? " on" : ""}`}>
              {activeCount === 0 ? "optional" : `${activeCount} ${activeCount === 1 ? "filter" : "filters"} active`}
            </span>
          </button>

          {advOpen && (
            <div className="adv-body" id="advanced-body">
              <h4>Education</h4>
              <div className="adv-grid">
                <TextField label="University / Institution" placeholder="e.g. IIT Bombay" value={adv.institution} onChange={setA("institution")} />
                <SelectField label="Degree type" choices={DEGREE_CHOICES} value={adv.degreeType} onChange={setA("degreeType")} />
                <TextField label="Field of study" placeholder="e.g. Computer Science" value={adv.fieldOfStudy} onChange={setA("fieldOfStudy")} />
                <SelectField label="Institution tier" choices={TIER_CHOICES} value={adv.institutionTier} onChange={setA("institutionTier")} />
              </div>

              <h4>Work experience</h4>
              <div className="adv-grid">
                <TextField label="Previous company" placeholder="e.g. Google" value={adv.previousCompany} onChange={setA("previousCompany")} />
                <TextField label="Previous role" placeholder="e.g. Software Engineer" value={adv.previousRole} onChange={setA("previousRole")} />
                <SelectField label="Years of experience" choices={YEARS_CHOICES} value={adv.yearsExperience} onChange={setA("yearsExperience")} />
                <Segmented label="Previous startup experience" choices={TRI_CHOICES} value={adv.previousStartup} onChange={setTri("previousStartup")} />
                <Segmented label="Serial founder" choices={TRI_CHOICES} value={adv.serialFounder} onChange={setTri("serialFounder")} />
                <Segmented label="Previous exit" choices={TRI_CHOICES} value={adv.previousExit} onChange={setTri("previousExit")} />
              </div>
              <ChipGroup label="Domain expertise" choices={DOMAIN_CHIPS} value={adv.domainExpertise} onChange={setA("domainExpertise")} />

              <h4>Demographics</h4>
              <div className="adv-grid">
                <TextField label="Nationality" placeholder="e.g. Indian" value={adv.nationality} onChange={setA("nationality")} />
                <TextField label="Current location" placeholder="e.g. San Francisco" value={adv.currentLocation} onChange={setA("currentLocation")} />
                <SelectField label="Age range" choices={AGE_CHOICES} value={adv.ageRange} onChange={setA("ageRange")} />
              </div>

              <h4>Pedigree</h4>
              <div className="adv-grid">
                <TextField label="Notable employer alumni" placeholder="e.g. FAANG or YC-backed" value={adv.notableEmployer} onChange={setA("notableEmployer")} />
                <Segmented label="Technical founder" choices={TRI_CHOICES} value={adv.technicalFounder} onChange={setTri("technicalFounder")} />
                <Segmented label="Research / publications" choices={TRI_CHOICES} value={adv.research} onChange={setTri("research")} />
              </div>
              <ChipGroup label="Accelerator alumni" choices={ACCELERATOR_CHIPS} value={adv.acceleratorAlumni} onChange={setA("acceleratorAlumni")} />

              <h4>Team</h4>
              <div className="adv-grid">
                <Segmented label="Solo vs co-founded" choices={SOLO_CHOICES} value={adv.soloVsCofounded} onChange={setA("soloVsCofounded")} />
                <SelectField label="Team size" choices={TEAM_SIZE_CHOICES} value={adv.teamSize} onChange={setA("teamSize")} />
              </div>
            </div>
          )}
        </div>

        <div className="actions">
          <button className="primary" onClick={run} disabled={busy || !canRun}>
            {busy ? "Starting..." : "Run agent"}
          </button>
          <button type="button" className="link" onClick={reset}>
            Reset
          </button>
          {!canRun && (
            <span className="muted hint">
              {otherMissing
                ? "Open Sector and describe \"Other\" to continue."
                : "Pick at least one sector and one geography to run."}
            </span>
          )}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
