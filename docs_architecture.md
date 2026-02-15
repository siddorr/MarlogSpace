# Architecture

## Stack
- Backend: Python (FastAPI recommended)
- Storage: Excel file on network share
- Email: SMTP for OTP

## Components
- Web UI
- API Layer
- Domain Services
- Excel Repository (single writer with locking)

## Concurrency
All write operations:
1. Acquire exclusive lock
2. Re-read latest Excel
3. Validate
4. Write to temp file
5. Backup previous file
6. Replace main file
7. Release lock

## Performance Targets
- Peak users: 20
- Read P95 < 300 ms
- Write P95 < 800 ms
- Page load < 2 seconds

## Failure Modes
- SMTP unavailable → login blocked
- Network share unavailable → write failure
- File corruption → restore from backup
- Lock stuck → admin intervention required

