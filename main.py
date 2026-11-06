import uuid
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from agent.models import Thesis

class RunRequest(BaseModel):
    thesis: Thesis
class SelectRequest(BaseModel):
    company_ids: list[str]

from agent.orchestrator import run_pipeline, run_backtest_pipeline, prepare_memos

load_dotenv()

app = FastAPI(title="VC Diligence Agent")

# Set cache mode on startup
if os.getenv("USE_CACHE", "false").lower() == "true":
    try:
        from crustdata.client import set_cache_mode
        set_cache_mode("only")
        print("Cache mode: ON — all Crustdata calls served from .cache/")
    except ImportError:
        pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store — fine for a hackathon
jobs: dict = {}


@app.post("/run")
async def run(request: RunRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running",
        "progress": {
            "stage": "discovery",
            "companies_found": 0,
            "companies_processed": 0
        },
        "results": None
    }
    background_tasks.add_task(run_pipeline, request.thesis.model_dump(), job_id, jobs)
    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def status(job_id: str):
    if job_id not in jobs:
        return {"error": "job not found"}
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "error": job.get("error"),
    }


@app.get("/results/{job_id}")
async def results(job_id: str):
    if job_id not in jobs:
        return {"error": "job not found"}
    job = jobs[job_id]
    # Results grow while memos are written: the frontend polls this and shows each memo as it lands
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "candidates": job.get("candidates") or [],
        "results": list(job.get("results") or []),
    }


@app.post("/select/{job_id}")
def select(job_id: str, request: SelectRequest, background_tasks: BackgroundTasks):
    """Start memos for the companies the user picked (from /results candidates)."""
    job = jobs.get(job_id)
    if not job or "_ctx" not in job:
        raise HTTPException(404, "job not found or discovery not finished")
    if job["status"] == "running" or job.get("_busy"):
        raise HTTPException(409, "memos are still being prepared or stopping for this job, try again shortly")
    if not request.company_ids:
        raise HTTPException(400, "pick at least one company")
    job.update(status="running", cancel=False, error=None)
    background_tasks.add_task(prepare_memos, job_id, jobs, request.company_ids)
    return {"job_id": job_id, "selected": len(request.company_ids)}


@app.post("/cancel/{job_id}")
def cancel(job_id: str):
    """Stop a job. Takes effect at the next step; a model call already in flight finishes first."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job["cancel"] = True
    if job["status"] in ("running", "awaiting_selection"):
        job["status"] = "cancelled"
    return {"job_id": job_id, "status": job["status"]}


class BacktestRequest(BaseModel):
    thesis: Thesis
    as_of_date: str  # ISO format: "2024-06-01"


@app.post("/backtest")
async def backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running",
        "progress": {
            "stage": "discovery",
            "companies_found": 0,
            "companies_processed": 0
        },
        "results": None,
        "is_backtest": True,
        "as_of_date": request.as_of_date
    }
    background_tasks.add_task(
        run_backtest_pipeline,
        request.thesis.model_dump(),
        job_id,
        jobs,
        request.as_of_date
    )
    return {"job_id": job_id}


@app.post("/webhook")
async def webhook(payload: dict):
    # Receives Crustdata watcher alerts — parse and re-queue affected companies
    try:
        from crustdata.client import parse_watch_event
        events = parse_watch_event(payload)
        for event in events:
            company_id = event.get("company_id")
            if company_id:
                # TODO: look up which job this company belongs to and re-run it
                fields = ", ".join(c.get("field", "?") for c in event.get("changes") or [])
                what = fields or ("test ping" if event.get("is_test") else "unknown change")
                print(f"Watcher triggered for company {company_id} ({event.get('company_name')}): {what}")
    except Exception as e:
        print(f"Webhook parse error: {e}")
    return {"received": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
