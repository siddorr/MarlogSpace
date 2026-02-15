# Interfaces

## Authentication
POST /api/auth/request-otp
POST /api/auth/verify-otp
POST /api/auth/logout

OTP: 6 digits, TTL 10 minutes, max 5 attempts.

## Reservations
POST /api/reservations
PATCH /api/reservations/{id}
DELETE /api/reservations/{id}
GET /api/reservations

Validation:
- Date within 7 days
- Sun–Thu only
- No desk double-booking
- No user double-booking

## Named Desk Absence
PUT /api/named-desk/absences

## Admin
Manage desks, users, named desk assignments, force cancel, stats.

## Slots
AM: 08:00–12:30
PM: 12:30–17:00
FULL = AM + PM

