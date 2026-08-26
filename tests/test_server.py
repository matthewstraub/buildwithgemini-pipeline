"""Unit tests for FastAPI backend server."""

from fastapi.testclient import TestClient
from pipeline.server import app

client = TestClient(app)


def test_get_applications_endpoint():
    response = client.get("/api/applications")
    assert response.status_code == 200
    data = response.json()
    assert "applications" in data
    assert isinstance(data["applications"], list)
    assert len(data["applications"]) > 0


def test_vet_endpoint():
    payload = {
        "sender_email": "sterling.talent.desk@gmail.com",
        "reply_to_email": "sterlingstaffing-careers.example.com",
        "claimed_company": "Sterling Staffing Group",
        "message_text": "We found your resume online. Move to Telegram for check reimbursement."
    }
    response = client.post("/api/vet", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "likely_fraudulent"
    assert data["role_legitimate"] is True
    assert data["channel_safe"] is False


def test_reports_endpoints():
    res_digest = client.get("/api/reports/digest")
    assert res_digest.status_code == 200
    assert "digest" in res_digest.json()

    res_summary = client.get("/api/reports/summary")
    assert res_summary.status_code == 200
    assert "summary" in res_summary.json()
