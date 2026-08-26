"""FastAPI backend server for Job Pipeline Agent Web Dashboard."""

from datetime import date
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.cadence import compute_next_action
from pipeline.cli import load_all_applications, save_application, STATE_DIR
from pipeline.digest import build_daily_digest, build_monday_summary
from pipeline.drafting import generate_followup_draft
from pipeline.holidays import count_business_days_between
from pipeline.models import Application, VettingInput
from pipeline.vetting import vet_recruiter_message

app = FastAPI(title="Job Pipeline Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent.parent.parent / "web"


class UpdateStagePayload(BaseModel):
    stage: str
    notes: Optional[str] = None


@app.get("/api/applications")
def get_applications():
    """Return all applications with computed cadence, quiet business days, and slug."""
    apps = load_all_applications()
    today = date.today()

    result = []
    for a in apps:
        a = compute_next_action(a, today=today)
        ref_date = a.stage_changed_on
        if a.last_contact and a.last_contact.date > ref_date:
            ref_date = a.last_contact.date
        quiet_bd = count_business_days_between(ref_date, today)

        data = a.model_dump(exclude_none=True, mode="json")
        data["slug"] = a.slug
        data["quiet_bd"] = quiet_bd
        data["needs_attention"] = bool(a.next_action and ("Draft" in a.next_action or "nudge" in a.next_action.lower()))
        result.append(data)

    return {"applications": result, "today": today.isoformat()}


@app.post("/api/applications")
def create_application(app_data: Dict[str, Any]):
    """Create or update an application record."""
    try:
        if "stage_changed_on" not in app_data or not app_data["stage_changed_on"]:
            app_data["stage_changed_on"] = date.today().isoformat()
        application = Application(**app_data)
        save_application(application)
        return {"status": "success", "slug": application.slug}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/applications/{slug}/stage")
def update_application_stage(slug: str, payload: UpdateStagePayload):
    """Update application stage."""
    apps = load_all_applications()
    target = None
    for a in apps:
        if a.slug == slug:
            target = a
            break

    if not target:
        raise HTTPException(status_code=404, detail="Application not found")

    target.stage = payload.stage
    target.stage_changed_on = date.today()
    if payload.notes:
        target.notes = payload.notes

    save_application(target)
    return {"status": "success", "application": target.model_dump(mode="json")}


@app.post("/api/vet")
def vet_message(v_input: VettingInput):
    """Run recruiter vetting analysis."""
    res = vet_recruiter_message(v_input)
    return res.model_dump(mode="json")


@app.post("/api/draft/{slug}")
def generate_draft(slug: str, payload: Optional[Dict[str, Any]] = None):
    """Generate or retrieve follow-up draft for application."""
    apps = load_all_applications()
    target = None
    for a in apps:
        if a.slug == slug:
            target = a
            break

    if not target:
        raise HTTPException(status_code=404, detail="Application not found")

    context = payload.get("context") if payload else None
    draft_file = generate_followup_draft(target, thread_context=context)

    draft_content = draft_file.read_text(encoding="utf-8")
    return {"status": "success", "draft_file": str(draft_file), "content": draft_content}


@app.get("/api/drafts/{slug}")
def get_draft(slug: str):
    """Get existing draft content if present."""
    draft_file = Path("out/drafts") / f"{slug}-followup.md"
    if not draft_file.exists():
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"content": draft_file.read_text(encoding="utf-8")}


@app.get("/api/reports/digest")
def get_digest():
    """Get daily digest text."""
    apps = load_all_applications()
    text, _ = build_daily_digest(apps)
    return {"digest": text}


@app.get("/api/reports/summary")
def get_summary():
    """Get Monday summary text."""
    apps = load_all_applications()
    text = build_monday_summary(apps)
    return {"summary": text}


# Serve static web frontend
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def read_root():
        index_path = WEB_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "Job Pipeline Agent API is running."}


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start uvicorn server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
