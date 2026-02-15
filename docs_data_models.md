# Data Models

## Sheets
- users
- desks
- reservations
- absences
- meta

## User
user_id, email, enabled, is_admin, created_at

## Desk
desk_id, label, enabled, owner_user_id

## Reservation
reservation_id, user_id, desk_id, date, slot (AM|PM), created_at, updated_at

Full day stored as two rows (AM and PM).

Constraints:
- Unique (desk_id, date, slot)
- Unique (user_id, date, slot)

## Absence
absence_id, owner_user_id, desk_id, date, slot, created_at

Absence only valid for named desk owners and within booking window.

## Backups
Create versioned backup on every change.

