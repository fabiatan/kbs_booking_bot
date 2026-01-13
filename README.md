# KBS Booking Bot

Automated booking bot for KBS sports facilities.

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
| `TELEGRAM_BOT_TOKEN` | (Optional) Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | (Optional) Telegram chat ID for notifications |

## How It Works

The bot automatically books **weekday slots only** (Mon-Fri) based on the KBS booking release pattern:

- **Release Pattern**: Slots open at 12:00am daily
- **Booking Window**: 61 days ahead (8 weeks + 5 days)
- **Schedule**: Runs Wed-Sun at 11:58 PM MYT
- **Target**: Books one weekday slot per run

## Manual Run (GitHub Actions)

1. Go to **Actions** tab
2. Select **KBS Booking Bot**
3. Click **Run workflow**
4. Configure (optional):
   - **date**: Specific date to book (DD/MM/YYYY), leave empty for auto
   - **days_ahead**: Number of days ahead (default: 61)
   - **poll_timeout**: Max seconds to poll (default: 1800)

## Command-Line Options

| Argument | Description | Default |
|----------|-------------|---------|
| `-u, --username` | IC number | Required |
| `-p, --password` | Password | Required |
| `-d, --date` | Booking date (DD/MM/YYYY) | Auto-calculated (61 days ahead) |
| `-ts, --time-start` | Start time | Day-specific (19:00-20:00 Mon-Thu, 20:00-22:00 Fri) |
| `-te, --time-end` | End time | Day-specific |
| `--days-ahead` | Days ahead to book | `61` |
| `--poll-timeout` | Max polling seconds | `1800` |
| `--debug` | Enable debug output | `false` |

## Automated Schedule

The workflow runs **Wed-Sun at 11:58 PM MYT** to book weekday slots only:

- Wed + 61 days = Mon ✓
- Thu + 61 days = Tue ✓
- Fri + 61 days = Wed ✓
- Sat + 61 days = Thu ✓
- Sun + 61 days = Fri ✓

Runs are skipped on Mon-Tue to avoid targeting weekend slots.

## Notifications

Bot sends Telegram notifications for:

- Booking success (with court details)
- Booking failed
