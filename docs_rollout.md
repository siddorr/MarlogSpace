# Rollout

## Prerequisites
- Windows server
- Python installed
- Network share for Excel
- SMTP configuration

## Deployment Steps
1. Create directories
2. Configure environment variables
3. Initialize Excel workbook with required sheets
4. Start service
5. Smoke test

## Recovery
- Restore latest backup if file corrupted
- Ensure exclusive lock is released if stuck

## Acceptance
- Accessible from LAN
- OTP login functional
- Reservations persist
- Backup created on every change

