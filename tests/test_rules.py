from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import (
    AdminDeskUpsert,
    AdminFloorUpsert,
    AdminLocationUpsert,
    AdminUserUpsert,
    BookingCreate,
    ManualReleaseUpsert,
    PreferredPartnerUpsert,
    WhitelistUpsert,
)
from app.repository import SQLiteRepository
from app.security import AuthManager
from app.services import MarlogService


def _next_weekday(target_weekday: int):
    today = datetime.utcnow().date()
    delta = (target_weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def _next_workday():
    today = datetime.utcnow().date()
    for offset in range(0, 7):
        value = today + timedelta(days=offset)
        if value.weekday() in {6, 0, 1, 2, 3}:
            return value
    raise AssertionError("No workday found")


@pytest.fixture()
def service(tmp_path):
    repo = SQLiteRepository(db_file=tmp_path / "marlogspace.db", legacy_excel_file=tmp_path / "missing.xlsx")
    repo.init_storage()
    auth = AuthManager(repo=repo)
    svc = MarlogService(repo=repo, auth=auth)

    admin = repo.upsert_user(
        name="Admin",
        email="admin@company.com",
        enabled=True,
        is_admin=True,
        location="Haifa",
        department="Facilities",
    )
    owner = repo.upsert_user("Owner", "owner@ide-tech.com", enabled=True, is_admin=False)
    alice = repo.upsert_user("Alice", "alice@ide-tech.com", enabled=True, is_admin=False)
    bob = repo.upsert_user("Bob", "bob@ide-tech.com", enabled=True, is_admin=False)
    for user in [admin, owner, alice, bob]:
        repo.upsert_whitelist(user.email, user.user_id, "test")

    location = svc.admin_upsert_location(admin, AdminLocationUpsert(name="Haifa"))
    floor = svc.admin_upsert_floor(admin, AdminFloorUpsert(location_id=location.location_id, name="2"))
    desk1 = svc.admin_upsert_desk(
        admin,
        AdminDeskUpsert(floor_id=floor.floor_id, label="Desk 1", x=10, y=10),
    )
    desk2 = svc.admin_upsert_desk(
        admin,
        AdminDeskUpsert(floor_id=floor.floor_id, label="Desk 2", owner_user_id=owner.user_id, x=40, y=10),
    )

    return {
        "repo": repo,
        "service": svc,
        "admin": admin,
        "owner": owner,
        "alice": alice,
        "bob": bob,
        "location": location,
        "floor": floor,
        "desk1": desk1,
        "desk2": desk2,
    }


def test_reject_non_workday(service):
    friday = _next_weekday(4)
    with pytest.raises(Exception) as exc:
        service["service"].create_booking(
            service["alice"],
            BookingCreate(desk_id=service["desk1"].desk_id, date=friday, slot="AM"),
        )
    assert "Sun-Thu" in str(exc.value)


def test_reject_outside_window(service):
    outside = datetime.utcnow().date() + timedelta(days=7)
    with pytest.raises(Exception) as exc:
        service["service"].create_booking(
            service["alice"],
            BookingCreate(desk_id=service["desk1"].desk_id, date=outside, slot="AM"),
        )
    assert "outside booking window" in str(exc.value)


def test_prevent_desk_double_booking(service):
    day = _next_workday()
    svc = service["service"]
    svc.create_booking(service["alice"], BookingCreate(desk_id=service["desk1"].desk_id, date=day, slot="AM"))
    with pytest.raises(Exception) as exc:
        svc.create_booking(service["bob"], BookingCreate(desk_id=service["desk1"].desk_id, date=day, slot="AM"))
    assert "Desk already reserved" in str(exc.value)


def test_named_desk_release_allows_booking(service):
    day = _next_workday()
    svc = service["service"]
    with pytest.raises(Exception):
        svc.create_booking(service["alice"], BookingCreate(desk_id=service["desk2"].desk_id, date=day, slot="AM"))

    svc.upsert_manual_release(
        service["owner"],
        ManualReleaseUpsert(desk_id=service["desk2"].desk_id, date=day, slot="AM", released=True),
    )
    created = svc.create_booking(service["alice"], BookingCreate(desk_id=service["desk2"].desk_id, date=day, slot="AM"))
    assert created.status == "pending"


def test_preferred_partner_auto_approves(service):
    day = _next_workday()
    svc = service["service"]
    svc.upsert_manual_release(
        service["owner"],
        ManualReleaseUpsert(desk_id=service["desk2"].desk_id, date=day, slot="AM", released=True),
    )
    svc.create_preferred_partner(
        service["owner"],
        PreferredPartnerUpsert(desk_id=service["desk2"].desk_id, partner_user_id=service["alice"].user_id),
    )
    booking = svc.create_booking(service["alice"], BookingCreate(desk_id=service["desk2"].desk_id, date=day, slot="AM"))
    assert booking.status == "approved"


def test_admin_can_create_whitelist_and_desk(service):
    svc = service["service"]
    entry = svc.admin_upsert_user(
        service["admin"],
        AdminUserUpsert(name="Maya", email="maya@ide-tech.com", enabled=True, is_admin=False),
    )
    whitelist = svc.admin_upsert_whitelist(service["admin"], WhitelistUpsert(email="maya@ide-tech.com"))
    assert entry.email == "maya@ide-tech.com"
    assert whitelist.email == "maya@ide-tech.com"


def test_notifications_created_for_pending_request(service):
    day = _next_workday()
    svc = service["service"]
    svc.upsert_manual_release(
        service["owner"],
        ManualReleaseUpsert(desk_id=service["desk2"].desk_id, date=day, slot="AM", released=True),
    )
    svc.create_booking(service["bob"], BookingCreate(desk_id=service["desk2"].desk_id, date=day, slot="AM"))
    notifications = svc.list_notifications(service["owner"])
    assert notifications
