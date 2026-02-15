# Desk Reservation Web App — Overview

## Purpose
Provide an internal web app for ~20 employees to reserve desks in an open-space where there are **10 desks**. Support **AM/PM** half-day reservations, **full-day** reservations, and **named (assigned) desks** that are automatically reserved for their owner unless the owner marks absence.

## In Scope
- Email-based login for `@ide-tech.com` users using one-time code (OTP).
- Desk reservation for:
  - AM (08:00–12:30)
  - PM (12:30–17:00)
  - Full day (AM+PM)
- Edit and cancel reservations.
- Recurring reservations: daily on workdays (Sun–Thu).
- Booking window: up to 7 days ahead (including today).
- Desk map UI (fixed layout).
- View all users’ reservations (transparent schedule).
- Admin features:
  - Add/remove (enable/disable) desks
  - Assign/unassign named desk ownership
  - Force-cancel reservations
  - Manage users (create/disable)
  - Basic usage stats
- Persistence in a single Excel file on a network drive with:
  - Server-side file locking (single writer)
  - Versioned backup on every change

## Non-goals
- No push/email notifications for reservations (besides OTP login emails).
- No waitlist.
- No dynamic drag-and-drop map editor.
- No integrations with external systems.
- No public internet exposure requirements.

## Key Rules
- Workdays: Sunday–Thursday only.
- A user may hold at most one desk per slot (AM and/or PM).
- Full day consumes both AM and PM.
- First-come-first-served conflict handling.
- Named desks auto-reserved unless released.

## Acceptance Criteria
- Prevent double-booking per desk/date/slot.
- Prevent user holding two desks in same slot.
- Named desk release enables booking by others.
- All changes persist and create backup.

