# Changelog

All notable changes to the KBS Booking Bot project will be documented in this file.

## [Unreleased] - 2025-12-29

### Added
- **Separate Retry Logic for TJK ID**: Added `--retry-tjk-id` argument to support different slot type IDs for secondary facilities.
- **Enhanced Fallback Notifications**: The bot now sends a "Booking Created" Telegram notification even if the confirmation ID cannot be extracted (handling server-side "ghost cart" errors).
- **Robustness**: Retry logic now correctly swaps both Facility ID and TJK ID when switching to the backup venue.

### Changed
- **Default Parameters Updated**:
  - `venue_id_num` defaulted to `2` (previously `1`) to match the actual venue ID for the Penang complex.
  - `facility_id_num` defaults updated to `114` (Primary) and `202` (Retry) based on latest HAR analysis.
- **CI/CD Schedule**: Updated GitHub Actions workflow frequency to run at 8:15 AM MYT with a refined timeout of 45 minutes (2700s).

### Removed
- **Fast Book Feature**: Completely removed the `--fast-book` logic and argument to simplify the codebase and focus on the reliable polling mechanism.
