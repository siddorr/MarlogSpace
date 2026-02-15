from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from filelock import FileLock

from app.repository import ExcelRepository
from app.services import ReservationService


def _next_weekday(target_weekday: int):
    today = datetime.utcnow().date()
    delta = (target_weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


@pytest.fixture()
def service(tmp_path):
    repo = ExcelRepository()
    repo.data_file = tmp_path / "reservations.xlsx"
    repo.backup_dir = tmp_path / "backups"
    repo.lock = FileLock(str(tmp_path / "reservations.lock"))
    repo.init_storage()
    svc = ReservationService(repo=repo)

    owner = repo.upsert_user("owner@ide-tech.com", enabled=True, is_admin=False)
    alice = repo.upsert_user("alice@ide-tech.com", enabled=True, is_admin=False)
    bob = repo.upsert_user("bob@ide-tech.com", enabled=True, is_admin=False)

    desk1 = repo.upsert_desk(label="Desk 1", enabled=True, owner_user_id=None, desk_id="d1")
    desk2 = repo.upsert_desk(
        label="Desk 2",
        enabled=True,
        owner_user_id=owner.user_id,
        desk_id="d2",
    )

    return {
        "repo": repo,
        "service": svc,
        "owner": owner,
        "alice": alice,
        "bob": bob,
        "desk1": desk1,
        "desk2": desk2,
    }


def _next_workday():
    today = datetime.utcnow().date()
    for offset in range(0, 7):
        d = today + timedelta(days=offset)
        if d.weekday() in {6, 0, 1, 2, 3}:
            return d
    raise AssertionError("No workday found")


def test_reject_non_workday(service):
    friday = _next_weekday(4)
    with pytest.raises(HTTPException) as exc:
        service["service"].create_reservation(
            user=service["alice"],
            desk_id=service["desk1"].desk_id,
            value_date=friday,
            request_slot="AM",
        )
    assert exc.value.status_code == 400


def test_reject_outside_window(service):
    outside = datetime.utcnow().date() + timedelta(days=7)
    with pytest.raises(HTTPException) as exc:
        service["service"].create_reservation(
            user=service["alice"],
            desk_id=service["desk1"].desk_id,
            value_date=outside,
            request_slot="AM",
        )
    assert exc.value.status_code == 400


def test_prevent_desk_double_booking(service):
    d = _next_workday()
    svc = service["service"]
    svc.create_reservation(service["alice"], service["desk1"].desk_id, d, "AM")

    with pytest.raises(HTTPException) as exc:
        svc.create_reservation(service["bob"], service["desk1"].desk_id, d, "AM")
    assert exc.value.status_code == 409


def test_prevent_user_double_booking(service):
    d = _next_workday()
    svc = service["service"]
    svc.create_reservation(service["alice"], service["desk1"].desk_id, d, "AM")

    with pytest.raises(HTTPException) as exc:
        svc.create_reservation(service["alice"], service["desk2"].desk_id, d, "AM")
    assert exc.value.status_code == 409


def test_named_desk_release_allows_booking(service):
    d = _next_workday()
    svc = service["service"]
    owner = service["owner"]

    with pytest.raises(HTTPException) as exc:
        svc.create_reservation(service["alice"], service["desk2"].desk_id, d, "AM")
    assert exc.value.status_code == 409

    svc.upsert_absence(owner, service["desk2"].desk_id, d, "AM", released=True)
    created = svc.create_reservation(service["alice"], service["desk2"].desk_id, d, "AM")
    assert len(created) == 1


def test_backup_created_on_write(service):
    d = _next_workday()
    svc = service["service"]
    repo = service["repo"]

    svc.create_reservation(service["alice"], service["desk1"].desk_id, d, "AM")
    backups = list(repo.backup_dir.glob("*.xlsx"))
    assert backups
