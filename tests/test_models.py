"""Unit tests for Application data models."""

from datetime import date
from pipeline.models import Application, SourceEnum, StageEnum


def test_application_slug_generation():
    app = Application(
        company="Northwind Devices",
        role="Solutions Consultant / Channel",
        stage=StageEnum.APPLIED,
        stage_changed_on=date(2026, 8, 12),
        source=SourceEnum.WARM_INTRO,
    )
    assert app.slug == "northwind-devices-solutions-consultant-channel"


def test_application_serialization():
    app = Application(
        company="Aurora Systems",
        role="Deployment Success Manager",
        applied_on=date(2026, 8, 14),
        stage=StageEnum.APPLIED,
        stage_changed_on=date(2026, 8, 14),
        source=SourceEnum.COLD,
    )
    dumped = app.model_dump(mode="json")
    assert dumped["company"] == "Aurora Systems"
    assert dumped["applied_on"] == "2026-08-14"
    assert dumped["stage"] == "applied"
