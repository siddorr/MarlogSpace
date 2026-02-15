# Testing

## Unit Tests
- Reject non-workdays
- Reject date outside 7-day window
- Prevent desk double-booking
- Prevent user double-booking
- Named desk auto-reservation logic
- Absence releases desk

## Integration Tests
- Write to Excel correctly
- Backup created on every change
- Concurrency: two simultaneous bookings → one success, one conflict

## Manual Checklist
- OTP login works
- Reservation create/edit/cancel works
- Named desk release works
- Admin actions work
- Network share failure handled safely

