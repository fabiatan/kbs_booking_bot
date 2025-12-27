# KBS Booking Bot

Automated booking bot for KBS (Kementerian Belia dan Sukan) sports facilities.

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/kbs-booking-bot.git
```

### 2. Add GitHub Secrets

Go to **Settings** → **Secrets and variables** → **Actions** and add:

| Secret | Description |
|--------|-------------|
| `KBS_USERNAME` | Your IC number |
| `KBS_PASSWORD` | Your password |

## Usage

### Manual Run (GitHub Actions)

1. Go to **Actions** tab
2. Select **KBS Booking Bot**
3. Click **Run workflow**
4. Enter:
   - Date: `DD/MM/YYYY` (e.g., `07/01/2026`)
   - Start time: `HH:MM:SS` (default: `07:00:00`)
   - End time: `HH:MM:SS` (default: `08:00:00`)

### Local Run

```bash
pip install requests

python kbs_booker_1.py \
  -u "YOUR_IC" \
  -p "YOUR_PASSWORD" \
  -d "07/01/2026" \
  -ts "07:00:00" \
  -te "08:00:00"
```

### Options

| Argument | Description | Default |
|----------|-------------|---------|
| `-u, --username` | IC number | Required |
| `-p, --password` | Password | Required |
| `-d, --date` | Booking date (DD/MM/YYYY) | Required |
| `-ts, --time-start` | Start time | `07:00:00` |
| `-te, --time-end` | End time | `08:00:00` |
| `--poll-timeout` | Max polling seconds | `3600` |
| `--debug` | Enable debug output | `false` |

## Notifications

Bot sends Telegram notifications for:
- Slot available
- Booking success
- Booking failed
- Polling timeout

## Schedule

The workflow runs daily at **8:25 AM MYT** (configured in `.github/workflows/book.yml`).
