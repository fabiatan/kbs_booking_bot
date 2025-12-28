#!/usr/bin/env python3
"""
KBS Sports Facility Booking Bot
Automates slot booking at stf.kbs.gov.my

Endpoints (from HAR analysis):
- POST /ks_user/login_handler.php - Login
- POST /check.php - Validate slot availability  
- POST /t_tempahan/tempahan_addhandler.php - Submit booking

Login requires:
- usrid: IC number
- password: password
- key: hidden form field (CSRF token)
- value: hidden form field (session token)
"""

import requests
import re
import time
from datetime import datetime, timedelta
import argparse


def get_booking_target():
    """
    Calculate booking target: 8 weeks from today with day-specific time slots.

    Time slots:
    - Monday-Thursday: 7-9pm (19:00-21:00)
    - Friday: 8-10pm (20:00-22:00)

    Returns:
        tuple: (date_str in DD/MM/YYYY, time_start, time_end) or None if weekend
    """
    today = datetime.now()
    target_date = today + timedelta(weeks=8)

    day_of_week = target_date.weekday()

    time_slots = {
        0: ("19:00:00", "21:00:00"),  # Monday: 7-9pm
        1: ("19:00:00", "21:00:00"),  # Tuesday: 7-9pm
        2: ("19:00:00", "21:00:00"),  # Wednesday: 7-9pm
        3: ("19:00:00", "21:00:00"),  # Thursday: 7-9pm
        4: ("20:00:00", "22:00:00"),  # Friday: 8-10pm
    }

    if day_of_week not in time_slots:
        return None  # Weekend - no booking

    time_start, time_end = time_slots[day_of_week]
    date_str = target_date.strftime("%d/%m/%Y")

    return (date_str, time_start, time_end)


class KBSBooker:
    BASE_URL = "https://stf.kbs.gov.my"

    # Telegram notification config
    TELEGRAM_BOT_TOKEN = "8121976263:AAHq5we2Nkj1EUkVbNwqvLEtCwUSquyHPHI"
    TELEGRAM_CHAT_ID = "1491443704"

    def __init__(self, username: str, password: str, debug: bool = False):
        self.username = username
        self.password = password
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        })
        self.ks_token = None
    
    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] {msg}")

    def send_telegram(self, message: str):
        """Send notification via Telegram bot"""
        url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": self.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            self.log(f"Telegram notification failed: {e}")
    
    def login(self) -> bool:
        """
        Login to KBS system
        
        Flow:
        1. GET login page to extract hidden 'key' and 'value' fields
        2. POST credentials with tokens to login_handler.php
        """
        login_page_url = f"{self.BASE_URL}/ks_user/login.php"
        login_handler_url = f"{self.BASE_URL}/ks_user/login_handler.php"
        
        # Step 1: Get login page to extract tokens
        self.log("Fetching login page...")
        resp = self.session.get(login_page_url)
        
        if self.debug:
            self.log(f"Login page status: {resp.status_code}")
        
        # Extract hidden fields 'key' and 'value'
        key_match = re.search(r'name=["\']key["\'][^>]*value=["\']([^"\']+)["\']', resp.text)
        if not key_match:
            key_match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']key["\']', resp.text)
        
        value_match = re.search(r'name=["\']value["\'][^>]*value=["\']([^"\']+)["\']', resp.text)
        if not value_match:
            value_match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']value["\']', resp.text)
        
        if not key_match or not value_match:
            self.log("ERROR: Could not extract login tokens from page")
            if self.debug:
                # Try to find any hidden inputs
                hidden_inputs = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', resp.text)
                self.log(f"Hidden inputs found: {hidden_inputs}")
            return False
        
        key_token = key_match.group(1)
        value_token = value_match.group(1)
        
        if self.debug:
            self.log(f"Extracted key: {key_token}")
            self.log(f"Extracted value: {value_token}")
        
        # Step 2: POST login credentials
        login_data = {
            "usrid": self.username,
            "password": self.password,
            "key": key_token,
            "value": value_token,
            "red": ""
        }
        
        self.log("Submitting login...")
        resp = self.session.post(login_handler_url, data=login_data, allow_redirects=True)
        
        # Check if logged in - successful login redirects to home.php
        logged_in = (
            "home.php" in resp.url or 
            "logout" in resp.text.lower() or 
            "log keluar" in resp.text.lower() or
            "selamat datang" in resp.text.lower()
        )
        
        if self.debug:
            self.log(f"Login response URL: {resp.url}")
            self.log(f"Login status: {resp.status_code}, logged_in: {logged_in}")
            if not logged_in:
                self.log(f"Response snippet: {resp.text[:500]}")
        
        return logged_in
    
    def get_facility_list(self, venue_id: str, neg: str = "07") -> list:
        """
        Get list of available facilities from the venue page.
        Returns list of dicts with facility info including fresh encoded IDs.
        
        Args:
            venue_id: Encoded venue ID
            neg: State code
        """
        # First visit tempahan home
        self.session.get(f"{self.BASE_URL}/t_tempahan/tempahan_home.php")
        
        # Get facility list page
        list_url = f"{self.BASE_URL}/t_tempahan/tempahan_listfasiliti.php"
        params = {"id": venue_id, "neg": neg}
        resp = self.session.get(list_url, params=params)
        
        if self.debug:
            self.log(f"Facility list page status: {resp.status_code}")
        
        # Extract facility links - look for tempahan_addcal.php links
        # Pattern: tempahan_addcal.php?id=XXX&idf=YYY&neg=ZZ
        facilities = []
        pattern = r'tempahan_addcal\.php\?id=([^&]+)&idf=([^&"\']+)&neg=(\d+)'
        matches = re.findall(pattern, resp.text)
        
        for match in matches:
            facilities.append({
                "venue_id": match[0],
                "facility_id_encoded": match[1],
                "neg": match[2]
            })
        
        # Also try to extract facility names and numeric IDs if visible
        # Look for onclick handlers or data attributes
        numeric_pattern = r'idfasiliti["\s:=]+["\']?(\d+)'
        numeric_ids = re.findall(numeric_pattern, resp.text)
        
        if self.debug:
            self.log(f"Found {len(facilities)} facility links")
            self.log(f"Found numeric IDs: {numeric_ids[:5]}")
            if facilities:
                self.log(f"First facility: {facilities[0]}")
        
        return facilities
    
    def get_calendar_page(self, venue_id: str, facility_id: str, neg: str = "07") -> str:
        """
        Navigate to calendar page to extract ks_token
        
        Must follow proper navigation path:
        1. tempahan_home.php
        2. tempahan_listfasiliti.php (sets session/referrer)
        3. tempahan_addcal.php (contains ks_token)
        
        Args:
            venue_id: Encoded venue ID (e.g., 'GxqArR56DGE8ZKkBI2f9')
            facility_id: Encoded facility ID (e.g., 'GxqArR56DGE8AQp3sR5Knm0=')
            neg: State code (e.g., '07')
        """
        # Step 1: Visit tempahan home
        self.log("Navigating to tempahan home...")
        resp = self.session.get(f"{self.BASE_URL}/t_tempahan/tempahan_home.php")
        if self.debug:
            self.log(f"tempahan_home.php status: {resp.status_code}")
        
        # Step 2: Visit facility list page (sets referrer context)
        self.log("Navigating to facility list...")
        list_url = f"{self.BASE_URL}/t_tempahan/tempahan_listfasiliti.php"
        list_params = {"id": venue_id, "neg": neg}
        resp = self.session.get(list_url, params=list_params)
        if self.debug:
            self.log(f"tempahan_listfasiliti.php status: {resp.status_code}")
        
        # Step 3: Get calendar page with proper referrer
        self.log("Fetching calendar page...")
        cal_url = f"{self.BASE_URL}/t_tempahan/tempahan_addcal.php"
        cal_params = {
            "id": venue_id,
            "idf": facility_id,
            "neg": neg
        }
        
        # Set referrer header
        headers = {
            "Referer": f"{self.BASE_URL}/t_tempahan/tempahan_listfasiliti.php?id={venue_id}&neg={neg}"
        }
        
        resp = self.session.get(cal_url, params=cal_params, headers=headers)
        
        if self.debug:
            self.log(f"tempahan_addcal.php status: {resp.status_code}")
            self.log(f"Response length: {len(resp.text)}")
        
        # Extract ks_token from hidden input - try multiple patterns
        patterns = [
            r'name=["\']ks_token["\'][^>]*value=["\']([a-f0-9]+)["\']',
            r'value=["\']([a-f0-9]+)["\'][^>]*name=["\']ks_token["\']',
            r'id=["\']ks_token["\'][^>]*value=["\']([a-f0-9]+)["\']',
            r'ks_token["\s:]+["\']([a-f0-9]{32})["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, resp.text, re.IGNORECASE)
            if match:
                self.ks_token = match.group(1)
                self.log(f"Got ks_token: {self.ks_token}")
                break
        
        if not self.ks_token:
            self.log("WARNING: Could not extract ks_token from page")
            if self.debug:
                # Look for any token-like hidden fields
                tokens = re.findall(r'<input[^>]*name=["\']ks_[^"\']+["\'][^>]*>', resp.text)
                self.log(f"KS inputs found: {tokens}")
                # Also dump some of the page for debugging
                self.log(f"Page sample: {resp.text[:1000]}")
        
        return resp.text
    
    def check_slot(self, facility_id: int, tjk_id: int, date: str, 
                   time_start: str, time_end: str) -> dict:
        """
        Check if slot is available via check.php
        
        Args:
            facility_id: Numeric facility ID (e.g., 477)
            tjk_id: Slot type ID (e.g., 528)
            date: Date in DD/MM/YYYY format
            time_start: Start time HH:MM:SS
            time_end: End time HH:MM:SS
        
        Returns:
            dict with 'available' boolean and raw response
        """
        url = f"{self.BASE_URL}/check.php"
        data = {
            "jmula": time_start,
            "jtamat": time_end,
            "idfasiliti": facility_id,
            "tjkid": tjk_id,
            "tarikhmula": date
        }
        
        resp = self.session.post(url, data=data)
        
        # Determine availability from response
        # Empty or "0" typically means available, "1" or message means taken
        text = resp.text.strip().lower()
        available = text in ["", "0", "ok", "available"] or "tiada" not in text
        
        if self.debug:
            self.log(f"check.php response: '{resp.text[:100]}' -> available: {available}")
        
        return {
            "status": resp.status_code,
            "available": available,
            "text": resp.text
        }
    
    def book_slot(self, config: dict) -> dict:
        """
        Submit booking via tempahan_addhandler.php
        
        Args:
            config: Booking configuration dict with all required fields
        """
        url = f"{self.BASE_URL}/t_tempahan/tempahan_addhandler.php"
        
        # Calculate hours
        try:
            start = datetime.strptime(config["time_start"], "%H:%M:%S")
            end = datetime.strptime(config["time_end"], "%H:%M:%S")
            hours = int((end - start).seconds / 3600)
        except:
            hours = 1
        
        # Build form data based on HAR capture
        data = {
            "tt_jeniskadar": config.get("jeniskadar", "1"),
            "tt_tarikh_mula": config["date"],
            "date-picker1": "",
            "date-picker2": "",
            "masa_mula": config["time_start"],
            "masa_tamat": config["time_end"],
            "tt_jumlah_jam": str(hours),
            "tt_jumlah_hari": "",
            "tt_jumlah": config.get("total_price", "12"),
            "jamsiang": config.get("rate_day", "12.00"),
            "jammalam": config.get("rate_night", "12.00"),
            "jamsiangbw": config.get("rate_day_bw", "12.00"),
            "jammalambw": config.get("rate_night_bw", "12.00"),
            "sehari": config.get("rate_daily", "288.00"),
            "seharibw": config.get("rate_daily_bw", "288.00"),
            "warga": config.get("warga", "1"),
            "tt_jum_pengguna": config.get("num_users", "4"),
            "tt_tujuan": config.get("purpose", "4"),
            "ks_token": self.ks_token,
            "ks_scriptname": "tempahan_addcal",
            "red": "",
            "idvanue": config.get("venue_id_num", "1"),
            "idfasiliti": config["facility_id"],
            "tjkid": config["tjk_id"],
            "kodneg": config.get("neg", "07"),
            "btnsubmit": ""
        }
        
        self.log(f"Submitting booking: {config['date']} {config['time_start']}-{config['time_end']}")
        
        resp = self.session.post(url, data=data, allow_redirects=True)
        
        success = "added" in resp.url or "msg=added" in resp.url or "berjaya" in resp.text.lower()
        
        # Extract booking ID from redirect URL for confirmation step
        booking_id = None
        if success:
            # The redirect URL contains encoded booking ID, need to parse the list page
            # to get the numeric idp value
            booking_id = self._extract_booking_id(resp.text, resp.url)
        
        if self.debug:
            self.log(f"Booking response URL: {resp.url}")
            self.log(f"Booking ID extracted: {booking_id}")
            self.log(f"Booking response: {resp.text[:300]}")
        
        return {
            "status": resp.status_code,
            "success": success,
            "url": resp.url,
            "booking_id": booking_id,
            "text": resp.text[:500] if self.debug else ""
        }
    
    def _extract_booking_id(self, html: str, url: str) -> str:
        """Extract the numeric booking ID (idp) from the bookings list page"""
        # Look for modifyhandler2.php links with idp parameter
        # Get the highest/newest idp value
        matches = re.findall(r'modifyhandler2\.php\?idp=(\d+)', html)
        if matches:
            # Return the highest ID (most recent booking)
            return max(matches, key=int)
        return None
    
    def confirm_booking(self, booking_id: str, total_price: str = "12") -> dict:
        """
        Confirm the booking via prosestempahan_modifyhandler2.php
        
        Args:
            booking_id: The numeric booking ID (idp)
            total_price: Total price (tot parameter)
        """
        url = f"{self.BASE_URL}/t_tempahan/prosestempahan_modifyhandler2.php"
        params = {
            "idp": booking_id,
            "idv": "1",  # Verification flag
            "tot": total_price
        }
        
        self.log(f"Confirming booking ID: {booking_id}")
        resp = self.session.get(url, params=params, allow_redirects=True)
        
        success = "verified" in resp.url.lower() or resp.status_code == 200
        
        if self.debug:
            self.log(f"Confirmation response URL: {resp.url}")
            self.log(f"Confirmation status: {resp.status_code}")
        
        return {
            "status": resp.status_code,
            "success": success,
            "url": resp.url
        }
    
    def run(self, config: dict, poll_timeout: int = 3600, check_interval: float = 1.0):
        """
        Main booking flow - polls for availability and books when slot opens

        Args:
            config: Booking configuration
            poll_timeout: Max seconds to poll
            check_interval: Seconds between availability checks
        """
        self.log("=" * 50)
        self.log("KBS Booking Bot Started")
        self.log("=" * 50)
        
        # Step 1: Login
        self.log("Step 1: Logging in...")
        if not self.login():
            self.log("ERROR: Login failed!")
            return False
        self.log("Login successful!")
        
        # Step 2: Get fresh facility IDs from the list page
        self.log("Step 2: Fetching facility list for fresh IDs...")
        facilities = self.get_facility_list(
            venue_id=config["venue_id"],
            neg=config.get("neg", "07")
        )
        
        if not facilities:
            self.log("ERROR: Could not find any facilities!")
            return False
        
        # Use the facility index if specified, otherwise first one
        facility_index = config.get("facility_index", 0)
        if facility_index >= len(facilities):
            self.log(f"WARNING: facility_index {facility_index} out of range, using 0")
            facility_index = 0
        
        selected_facility = facilities[facility_index]
        self.log(f"Selected facility: {selected_facility}")
        
        # Update config with fresh encoded ID
        fresh_facility_id = selected_facility["facility_id_encoded"]
        
        # Step 3: Get calendar page for ks_token
        self.log("Step 3: Fetching calendar page for token...")
        self.get_calendar_page(
            venue_id=config["venue_id"],
            facility_id=fresh_facility_id,  # Use fresh ID from facility list
            neg=config.get("neg", "07")
        )
        
        if not self.ks_token:
            self.log("ERROR: Could not get ks_token!")
            return False
        
        # Step 4: Poll for availability
        self.log(f"Step 4: Polling for availability (timeout: {poll_timeout}s, interval: {check_interval}s)...")

        start_time = datetime.now()
        check_count = 0
        slot_available_notified = False

        while True:
            check_count += 1
            elapsed = (datetime.now() - start_time).total_seconds()

            # Check timeout
            if elapsed > poll_timeout:
                self.log(f"Timeout after {poll_timeout}s ({check_count} checks)")
                self.send_telegram(f"❌ Booking failed - timeout after {poll_timeout}s")
                return False

            # Check availability
            avail = self.check_slot(
                facility_id=config["facility_id"],
                tjk_id=config["tjk_id"],
                date=config["date"],
                time_start=config["time_start"],
                time_end=config["time_end"]
            )

            if avail["available"]:
                self.log(f"SLOT AVAILABLE! Detected after {elapsed:.1f}s ({check_count} checks)")
                # Calculate booking duration and day name
                t_start = datetime.strptime(config["time_start"], "%H:%M:%S")
                t_end = datetime.strptime(config["time_end"], "%H:%M:%S")
                hours = int((t_end - t_start).seconds / 3600)
                booking_date = datetime.strptime(config["date"], "%d/%m/%Y")
                day_name = booking_date.strftime("%A")
                if not slot_available_notified:
                    self.send_telegram(
                        f"🎯 Slot available! Attempting to book...\n"
                        f"Location: Kompleks Sukan KBS\n"
                        f"Date: {config['date']} ({day_name})\n"
                        f"Time: {config['time_start']}-{config['time_end']} ({hours}-hours)"
                    )
                    slot_available_notified = True

                # Refresh token before booking (session may have aged)
                if elapsed > 2400:  # Refresh if waited more than 40 mins
                    self.log("Refreshing session token...")
                    self.get_calendar_page(
                        venue_id=config["venue_id"],
                        facility_id=fresh_facility_id,
                        neg=config.get("neg", "07")
                    )

                # Immediately book
                self.log("Step 5: Booking slot...")
                result = self.book_slot(config)

                if result["success"]:
                    self.log(f"SUCCESS! Booking created: {result['url']}")

                    # Confirm booking
                    if result.get("booking_id"):
                        self.log("Step 6: Confirming booking...")
                        confirm_result = self.confirm_booking(
                            booking_id=result["booking_id"],
                            total_price=config.get("total_price", "12")
                        )
                        if confirm_result["success"]:
                            self.log(f"CONFIRMED! {confirm_result['url']}")
                            self.send_telegram(
                                f"✅ <b>SUCCESS!</b>\n"
                                f"Location: Kompleks Sukan KBS\n"
                                f"Date: {config['date']} ({day_name})\n"
                                f"Time: {config['time_start']}-{config['time_end']} ({hours}-hours)"
                            )
                        else:
                            self.log("WARNING: Confirmation may have failed")
                            self.send_telegram(f"⚠️ Booking created but confirmation may have failed")

                    return True
                else:
                    self.log("Booking failed, continuing to poll...")

            # Progress update every 60 checks
            if check_count % 60 == 0:
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                self.log(f"[{mins:02d}:{secs:02d}] Still polling... ({check_count} checks)")

            time.sleep(check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="KBS Sports Facility Booking Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python kbs_booker.py \\
    -u "910101011234" \\
    -p "yourpassword" \\
    -d "07/01/2026" \\
    -ts "07:00:00" \\
    -te "08:00:00" \\
    --debug
        """
    )
    parser.add_argument("--username", "-u", required=True, help="IC number")
    parser.add_argument("--password", "-p", required=True, help="Password")
    parser.add_argument("--date", "-d", default="", help="Booking date (DD/MM/YYYY). If not specified, auto-calculates 8 weeks from today")
    parser.add_argument("--time-start", "-ts", default="", help="Start time (HH:MM:SS). If not specified, uses day-specific time slot")
    parser.add_argument("--time-end", "-te", default="", help="End time (HH:MM:SS). If not specified, uses day-specific time slot")
    parser.add_argument("--venue-id", default="GxqArR56DGE8ZKkBI2f9", help="Encoded venue ID from URL")
    parser.add_argument("--facility-id", default="GxqArR56DGE8AQp3sR5Knm0=", help="Encoded facility ID (optional, fetched dynamically)")
    parser.add_argument("--facility-id-num", type=int, default=477, help="Numeric facility ID")
    parser.add_argument("--tjk-id", type=int, default=528, help="TJK ID (slot type)")
    parser.add_argument("--neg", default="07", help="State code (default: 07)")
    parser.add_argument("--facility-index", type=int, default=0, help="Index of facility from list (default: 0, first one)")
    parser.add_argument("--list-facilities", action="store_true", help="List available facilities and exit")
    parser.add_argument("--num-users", default="4", help="Number of users (default: 4)")
    parser.add_argument("--purpose", default="4", help="Purpose code (default: 4)")
    parser.add_argument("--poll-timeout", type=int, default=3600, help="Max seconds to poll (default: 3600 = 1 hour)")
    parser.add_argument("--check-interval", type=float, default=1.0, help="Seconds between availability checks (default: 1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()

    booker = KBSBooker(args.username, args.password, debug=args.debug)

    # If just listing facilities
    if args.list_facilities:
        booker.log("Logging in to list facilities...")
        if not booker.login():
            booker.log("ERROR: Login failed!")
            return 1
        facilities = booker.get_facility_list(args.venue_id, args.neg)
        print(f"\nFound {len(facilities)} facilities:")
        for i, f in enumerate(facilities):
            print(f"  [{i}] idf={f['facility_id_encoded']}")
        return 0

    # Use automatic date/time calculation if not provided
    if not args.date or not args.time_start or not args.time_end:
        target = get_booking_target()
        if target is None:
            print("ERROR: Target date is a weekend. No booking scheduled.")
            return 1
        auto_date, auto_time_start, auto_time_end = target
        if not args.date:
            args.date = auto_date
        if not args.time_start:
            args.time_start = auto_time_start
        if not args.time_end:
            args.time_end = auto_time_end
        print(f"Auto-calculated booking: {args.date} {args.time_start}-{args.time_end}")

    config = {
        "venue_id": args.venue_id,
        "facility_id_encoded": args.facility_id,
        "facility_id": args.facility_id_num,
        "facility_index": args.facility_index,
        "tjk_id": args.tjk_id,
        "date": args.date,
        "time_start": args.time_start,
        "time_end": args.time_end,
        "neg": args.neg,
        "num_users": args.num_users,
        "purpose": args.purpose,
    }
    success = booker.run(
        config,
        poll_timeout=args.poll_timeout,
        check_interval=args.check_interval
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
