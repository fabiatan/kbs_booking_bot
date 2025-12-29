# Changelog

All notable changes to the KBS Booking Bot project will be documented in this file.

## [Unreleased] - 2025-12-29

### Added
- **Weekly Booking Mode (`--book-week`)**: New flag to book all 5 weekday slots (Mon-Fri) in a single run. Designed for Monday execution when the week's slots open.
- **Separate Retry Logic for TJK ID**: Added `--retry-tjk-id` argument to support different slot type IDs for secondary facilities.
- **Court Name Tracking**: The bot now tracks which court was booked (Court 1 or Court 2) and includes this in the Telegram summary.
- **Weekly Booking Summary**: Detailed Telegram notification at the end of weekly booking with all days, times, and court names.
- **Enhanced Fallback Notifications**: The bot now sends a "Booking Created" Telegram notification even if the confirmation ID cannot be extracted.

### Changed
- **Default Parameters Updated**:
  - `venue_id_num` defaulted to `2` to match the actual venue ID for the Penang complex.
  - `facility_id_num` defaults updated to `114` (Primary) and `202` (Retry) based on HAR analysis.
  - `tjk_id` defaults updated to `624` (Primary) and `625` (Retry).
- **CI/CD Schedule**: Workflow now runs only on **Monday** at 7:15 AM MYT with `--book-week` flag.
- **Return Type**: `run()` method now returns `{"success": bool, "court_name": str}` for better tracking.

### Removed
- **Fast Book Feature**: Completely removed the `--fast-book` logic and argument to simplify the codebase.
