import uuid
import os
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from agent.models import Thesis
from agent.orchestrator import run_pipeline, run_backtest_pipeline

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
async def run(thesis: Thesis, background_tasks: BackgroundTasks):
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
    background_tasks.add_task(run_pipeline, thesis.model_dump(), job_id, jobs)
    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def status(job_id: str):
    if job_id not in jobs:
        return {"error": "job not found"}
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"]
    }


@app.get("/results/{job_id}")
async def results(job_id: str):
    if job_id not in jobs:
        return {"error": "job not found"}
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "results": job.get("results", [])
    }


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
                print(f"Watcher triggered for company {company_id}: {event.get('trigger_type')}")
    except Exception as e:
        print(f"Webhook parse error: {e}")
    return {"received": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
