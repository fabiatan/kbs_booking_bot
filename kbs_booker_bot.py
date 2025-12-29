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

import os
import requests
import re
import time
import json
import glob
from datetime import datetime, timedelta
import argparse


def get_weekly_booking_targets():
    """
    Calculate booking targets for the entire week (Mon-Fri), 8 weeks from now.
    
    This is used when running on Monday to book all 5 weekday slots at once.
    
    Time slots:
    - Monday-Thursday: 7-9pm (19:00-21:00)
    - Friday: 8-10pm (20:00-22:00)

    Returns:
        list of tuples: [(date_str, time_start, time_end), ...] for Mon-Fri
    """
    today = datetime.now()
    
    # Calculate 8 weeks from today, then find the Monday of that week
    future_date = today + timedelta(weeks=8)
    # Subtract the weekday to get to Monday (weekday() returns 0 for Monday)
    target_monday = future_date - timedelta(days=future_date.weekday())
    
    time_slots = {
        0: ("19:00:00", "21:00:00"),  # Monday: 7-9pm
        1: ("19:00:00", "21:00:00"),  # Tuesday: 7-9pm
        2: ("19:00:00", "21:00:00"),  # Wednesday: 7-9pm
        3: ("19:00:00", "21:00:00"),  # Thursday: 7-9pm
        4: ("20:00:00", "22:00:00"),  # Friday: 8-10pm
    }
    
    targets = []
    for day_offset in range(5):  # Mon=0 to Fri=4
        target_date = target_monday + timedelta(days=day_offset)
        time_start, time_end = time_slots[day_offset]
        date_str = target_date.strftime("%d/%m/%Y")
        targets.append((date_str, time_start, time_end))
    
    return targets


def get_single_day_target(day_offset: int):
    """
    Calculate booking target for a specific day, 8 weeks from now.
    Used for parallel booking where each job books one day.
    
    Args:
        day_offset: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday
    
    Returns:
        tuple: (date_str, time_start, time_end, day_name)
    """
    if day_offset < 0 or day_offset > 4:
        raise ValueError(f"day_offset must be 0-4, got {day_offset}")
    
    today = datetime.now()
    future_date = today + timedelta(weeks=8)
    target_monday = future_date - timedelta(days=future_date.weekday())
    target_date = target_monday + timedelta(days=day_offset)
    
    time_slots = {
        0: ("21:00:00", "22:00:00"),  # Monday: 7-9pm
        1: ("19:00:00", "21:00:00"),  # Tuesday: 7-9pm
        2: ("21:00:00", "22:00:00"),  # Wednesday: 7-9pm
        3: ("21:00:00", "22:00:00"),  # Thursday: 7-9pm
        4: ("20:00:00", "22:00:00"),  # Friday: 8-10pm
    }
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    time_start, time_end = time_slots[day_offset]
    date_str = target_date.strftime("%d/%m/%Y")
    
    return (date_str, time_start, time_end, day_names[day_offset])


def get_booking_target():
    """
    Calculate booking target: 8 weeks from today with day-specific time slots.
    (Legacy single-day function for backward compatibility)

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

    # Telegram notification config (from environment variables)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

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
        self.logged_in = False  # Track login state to skip re-login
        self._cached_facilities = None  # Cache facility list
    
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
        
        if logged_in:
            self.logged_in = True
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
        
        # Calculate total price based on time of day
        # Daytime (before 7pm/19:00) = RM 10/hour, Nighttime (7pm onwards) = RM 15/hour
        start_hour = start.hour if 'start' in dir() else 19  # Default to nighttime
        hourly_rate = 10 if start_hour < 19 else 15
        total_price = config.get("total_price") or str(hours * hourly_rate)
        
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
            "tt_jumlah": total_price,
            "jamsiang": config.get("rate_day", "10.00"),
            "jammalam": config.get("rate_night", "15.00"),
            "jamsiangbw": config.get("rate_day_bw", "15.00"),
            "jammalambw": config.get("rate_night_bw", "20.00"),
            "sehari": config.get("rate_daily", "200.00"),
            "seharibw": config.get("rate_daily_bw", "250.00"),
            "warga": config.get("warga", "1"),
            "tt_jum_pengguna": config.get("num_users", "4"),
            "tt_tujuan": config.get("purpose", "4"),
            "ks_token": self.ks_token,
            "ks_scriptname": "tempahan_addcal",
            "red": "",
            "idvanue": config.get("venue_id_num", "2"),
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
    
    def confirm_booking(self, booking_id: str, total_price: str = "15") -> dict:
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
    
    def run(self, config: dict, poll_timeout: int = 3600, check_interval: float = 1.0) -> dict:
        """
        Main booking flow - polls for availability and books when slot opens

        Args:
            config: Booking configuration
            poll_timeout: Max seconds to poll
            check_interval: Seconds between availability checks
        
        Returns:
            dict: {"success": bool, "court_name": str or None}
        """
        self.log("=" * 50)
        self.log("KBS Booking Bot Started")
        self.log("=" * 50)
        
        # Step 1: Login (skip if already logged in)
        if self.logged_in:
            self.log("Step 1: Already logged in, skipping...")
        else:
            self.log("Step 1: Logging in...")
            if not self.login():
                self.log("ERROR: Login failed!")
                return {"success": False, "court_name": None}
            self.log("Login successful!")
        
        # Step 2: Get facility IDs (use cache if available)
        # If venue is closed/unavailable, poll until facilities appear
        venue_poll_interval = 3.0  # seconds between venue checks
        venue_poll_timeout = min(poll_timeout, 3000)  # Max 50 minutes for venue polling
        
        if self._cached_facilities:
            self.log("Step 2: Using cached facility list...")
            facilities = self._cached_facilities
        else:
            self.log("Step 2: Fetching facility list (will poll if venue closed)...")
            venue_poll_start = datetime.now()
            venue_poll_count = 0
            
            while True:
                facilities = self.get_facility_list(
                    venue_id=config["venue_id"],
                    neg=config.get("neg", "07")
                )
                venue_poll_count += 1
                
                if facilities:
                    elapsed = (datetime.now() - venue_poll_start).total_seconds()
                    if venue_poll_count > 1:
                        self.log(f"Venue now available! Found {len(facilities)} facilities after {elapsed:.1f}s ({venue_poll_count} checks)")
                    else:
                        self.log(f"Found {len(facilities)} facilities")
                    self._cached_facilities = facilities  # Cache for next call
                    break
                
                # Check timeout
                elapsed = (datetime.now() - venue_poll_start).total_seconds()
                if elapsed >= venue_poll_timeout:
                    self.log(f"Venue polling timeout after {elapsed:.1f}s ({venue_poll_count} checks)")
                    self.log("ERROR: Venue still not available!")
                    return {"success": False, "court_name": None}
                
                # Progress update every 20 checks (~60 seconds)
                if venue_poll_count % 20 == 0:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    self.log(f"[{mins:02d}:{secs:02d}] Waiting for venue to open... ({venue_poll_count} checks)")
                
                time.sleep(venue_poll_interval)
        
        if not facilities:
            self.log("ERROR: Could not find any facilities!")
            return {"success": False, "court_name": None}
        
        # Use the facility index if specified, otherwise first one
        facility_index = config.get("facility_index", 0)
        if facility_index >= len(facilities):
            self.log(f"WARNING: facility_index {facility_index} out of range, using 0")
            facility_index = 0
        
        selected_facility = facilities[facility_index]
        self.log(f"Selected facility: {selected_facility}")
        
        # Update config with fresh encoded ID
        fresh_facility_id = selected_facility["facility_id_encoded"]
        
        # Step 3: Get calendar page for ks_token (skip if cached)
        if self.ks_token:
            self.log("Step 3: Using cached ks_token, skipping calendar page...")
        else:
            self.log("Step 3: Fetching calendar page for token...")
            self.get_calendar_page(
                venue_id=config["venue_id"],
                facility_id=fresh_facility_id,  # Use fresh ID from facility list
                neg=config.get("neg", "07")
            )
            
            if not self.ks_token:
                self.log("ERROR: Could not get ks_token!")
                return {"success": False, "court_name": None}
        
        # Step 4: Poll for availability
        self.log(f"Step 4: Polling for availability (timeout: {poll_timeout}s, interval: {check_interval}s)...")

        start_time = datetime.now()
        check_count = 0
        slot_available_notified = False

        while True:
            now = datetime.now()
            elapsed = (now - start_time).total_seconds()
            
            # Check timeout
            if elapsed > poll_timeout:
                self.log(f"Timeout after {poll_timeout}s ({check_count} checks)")
                # Skip Telegram notification for timeout - waste of time
                return {"success": False, "court_name": None}

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
                    # Skip Telegram notification for slot available - proceed directly to booking
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
                    # Determine facility name based on index (set once here)
                    facility_name = "Gelanggang Tenis 1" if config.get("facility_index", 0) == 0 else "Gelanggang Tenis 2"

                    # Confirm booking
                    if result.get("booking_id"):
                        self.log("Step 6: Confirming booking...")
                        # Calculate rate based on time of day
                        hourly_rate = 10 if t_start.hour < 19 else 15
                        confirm_result = self.confirm_booking(
                            booking_id=result["booking_id"],
                            total_price=str(hours * hourly_rate)
                        )
                        if confirm_result["success"]:
                            self.log(f"CONFIRMED! {confirm_result['url']}")
                        else:
                            self.log("WARNING: Confirmation may have failed")
                            self.send_telegram(f"⚠️ Booking created but confirmation may have failed")
                    else:
                        self.log("WARNING: Booking ID not found, skipping confirmation.")

                    return {"success": True, "court_name": facility_name}
                else:
                    self.log("Booking failed, continuing to poll...")
                    # Retry logic for failed booking
                    if config.get("retry_facility_index") is not None:
                        retry_index = config["retry_facility_index"]
                        self.log(f"Primary booking failed. Retrying with facility index {retry_index}...")
                        
                        # Fetch new facility details
                        facilities = self.get_facility_list(config["venue_id"], config.get("neg", "07"))
                        if 0 <= retry_index < len(facilities):
                            new_facility = facilities[retry_index]
                            self.log(f"Switching to facility: {new_facility['facility_id_encoded']}")
                            
                            # Update config for retry
                            # Prefer fetched ID from index if available, otherwise use strict default from args
                            if 'facility_id_encoded' in new_facility:
                                config["facility_id_encoded"] = new_facility['facility_id_encoded']
                            elif config.get("retry_facility_id"):
                                config["facility_id_encoded"] = config["retry_facility_id"]
                            
                            # Save original numeric ID before switching
                            original_num = config.get("facility_id")
                            
                            # Update Numeric ID
                            if config.get("retry_facility_id_num"):
                                config["facility_id"] = config["retry_facility_id_num"]
                            
                            # Update TJK ID (Crucial fix for different facilities)
                            original_tjk = config.get("tjk_id")
                            if config.get("retry_tjk_id"):
                                config["tjk_id"] = config["retry_tjk_id"]
                            
                            # RE-ATTEMPT BOOKING with the new facility
                            self.log(f"Re-attempting booking with facility: {config['facility_id_encoded']} (Num ID: {config['facility_id']}, TJK: {config['tjk_id']})...")
                            time.sleep(1.0) # Small delay before retry
                            retry_result = self.book_slot(config)
                            
                            if retry_result["success"]:
                                self.log(f"SUCCESS! Retry booking created: {retry_result['url']}")
                                # Calculate booking details once (available for all paths)
                                t_start = datetime.strptime(config["time_start"], "%H:%M:%S")
                                t_end = datetime.strptime(config["time_end"], "%H:%M:%S")
                                hours = int((t_end - t_start).seconds / 3600)
                                booking_date = datetime.strptime(config["date"], "%d/%m/%Y")
                                day_name = booking_date.strftime("%A")
                                retry_name = "Gelanggang Tenis 1" if retry_index == 0 else "Gelanggang Tenis 2"

                                if retry_result.get("booking_id"):
                                    self.log("Step 6: Confirming retry booking...")
                                    # Calculate rate based on time of day
                                    hourly_rate = 10 if t_start.hour < 19 else 15
                                    confirm_result = self.confirm_booking(
                                        booking_id=retry_result["booking_id"],
                                        total_price=str(hours * hourly_rate)
                                    )
                                    if confirm_result["success"]:
                                        self.log(f"CONFIRMED! {confirm_result['url']}")

                                        self.send_telegram(
                                            f"✅ <b>SUCCESS! (Retry Facility)</b>\n"
                                            f"Location: Kompleks Sukan KBS\n"
                                            f"Court: {retry_name}\n"
                                            f"Date: {config['date']} ({day_name})\n"
                                            f"Time: {config['time_start']}-{config['time_end']} ({hours}-hours)"
                                        )
                                    else:
                                        self.log("WARNING: Retry booking created but confirmation may have failed")
                                        self.send_telegram(f"⚠️ Retry booking created but confirmation may have failed")
                                else:
                                    self.log("WARNING: Retry Booking ID not found, skipping confirmation.")
                                    self.send_telegram(
                                       f"✅ <b>BOOKING CREATED! (Retry)</b> (Confirmation skipped)\n"
                                       f"Location: Kompleks Sukan KBS\n"
                                       f"Court: {retry_name}\n"
                                       f"Date: {config['date']} ({day_name})\n"
                                       f"Time: {config['time_start']}-{config['time_end']} ({hours}-hours)\n"
                                       f"Check website to verify status."
                                    )
                                return {"success": True, "court_name": retry_name}  # EXIT after successful backup booking
                            else:
                                self.log(f"Retry booking with facility index {retry_index} also failed.")
                                # self.send_telegram(f"❌ Booking failed - primary and retry facilities failed.")
                                # Don't exit here, maybe primary becomes available? Or just fail?
                                # If fast book, we might loop. If standard, we loop.
                                
                                # Revert ID to primary for next loop iteration check
                                config["facility_id_encoded"] = facilities[config.get("facility_index", 0)]['facility_id_encoded']
                                config["facility_id"] = original_num
                                config["tjk_id"] = original_tjk
                                
                                # Do NOT return False here. We want to continue polling if retry failed.
                                # Just log and loop around.
                                self.log("Continuing to poll...")
                                pass 
                        else:
                            self.log(f"Invalid retry facility index: {retry_index}. Cannot retry.")
                            pass
                    else:
                        # No retry facility configured, so just log and continue polling
                        pass

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
    parser.add_argument("--venue-id", default="GxqArR56DGE8ZakBI2f9", help="Encoded venue ID from URL")
    parser.add_argument("--facility-id", default="GxqArR56DGE8ZGR0sR5Knm0=", help="Encoded facility ID (optional, fetched dynamically)")
    parser.add_argument("--facility-id-num", type=int, default=114, help="Numeric facility ID (Primary)")
    parser.add_argument("--tjk-id", type=int, default=624, help="TJK ID (Primary)")
    parser.add_argument("--retry-facility-index", type=int, default=1, help="Index of secondary facility to retry if primary fails (e.g., 1)")
    parser.add_argument("--retry-facility-id", default="GxqArR56DGE8ZwNlsR5Knm0=", help="Encoded parameter for secondary facility (from HAR)")
    parser.add_argument("--retry-facility-id-num", type=int, default=202, help="Numeric ID of secondary facility (Retry)")
    parser.add_argument("--retry-tjk-id", type=int, default=625, help="TJK ID for secondary facility (Retry)")
    parser.add_argument("--venue-id-num", type=int, default=2, help="Numeric Venue ID (from idvanue)")
    parser.add_argument("--neg", default="07", help="State code (default: 07)")
    parser.add_argument("--facility-index", type=int, default=0, help="Index of facility from list (default: 0, first one)")
    parser.add_argument("--list-facilities", action="store_true", help="List available facilities and exit")
    parser.add_argument("--num-users", default="4", help="Number of users (default: 4)")
    parser.add_argument("--purpose", default="4", help="Purpose code (default: 4)")
    parser.add_argument("--poll-timeout", type=int, default=3600, help="Max seconds to poll (default: 3600 = 1 hour)")
    parser.add_argument("--check-interval", type=float, default=1.0, help="Seconds between availability checks (default: 1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--book-week", action="store_true", help="Book all 5 weekday slots (Mon-Fri) for the week 8 weeks ahead. Used when running on Monday.")
    parser.add_argument("--day-offset", type=int, default=None, help="Book specific day only (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri). For parallel booking.")
    parser.add_argument("--summary-report", action="store_true", help="Generate summary report from JSON result files (parallel booking only)")
    
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

    # SINGLE DAY MODE (for parallel booking): Book specific day only
    if args.day_offset is not None:
        date, time_start, time_end, day_name = get_single_day_target(args.day_offset)
        print("=" * 50)
        print(f"SINGLE DAY MODE: Booking {day_name}")
        print(f"Date: {date} | Time: {time_start}-{time_end}")
        print("=" * 50)
        
        config = {
            "venue_id": args.venue_id,
            "facility_id_encoded": args.facility_id,
            "facility_id": args.facility_id_num,
            "facility_index": args.facility_index,
            "tjk_id": args.tjk_id,
            "retry_facility_index": args.retry_facility_index,
            "retry_facility_id": args.retry_facility_id,
            "retry_facility_id_num": args.retry_facility_id_num,
            "retry_tjk_id": args.retry_tjk_id,
            "venue_id_num": args.venue_id_num,
            "date": date,
            "time_start": time_start,
            "time_end": time_end,
            "neg": args.neg,
            "num_users": args.num_users,
            "purpose": args.purpose,
        }
        
        result = booker.run(config, poll_timeout=args.poll_timeout, check_interval=args.check_interval)
        
        if isinstance(result, dict):
            success = result.get("success", False)
            court_name = result.get("court_name", "Unknown")
        else:
            success = bool(result)
            court_name = "Unknown"
        
        if success:
            print(f"✅ {day_name} booked successfully! (Court: {court_name})")
        else:
            print(f"❌ {day_name} booking failed.")
        
        # Save result to JSON for aggregation
        result_data = {
            "day_name": day_name,
            "date": date,
            "time_start": time_start,
            "time_end": time_end,
            "success": success,
            "court_name": court_name,
            "day_offset": args.day_offset
        }
        filename = f"booking_result_{args.day_offset}.json"
        with open(filename, "w") as f:
            json.dump(result_data, f)
        print(f"Result saved to {filename}")
        
        return 0 if success else 1

    # SUMMARY REPORT MODE: Aggregate results and send Telegram summary
    if args.summary_report:
        print("=" * 50)
        print("GENERATING WEEKLY SUMMARY REPORT")
        print("=" * 50)
        
        # Find all result files
        files = glob.glob("booking_result_*.json")
        results = []
        for f in files:
            try:
                with open(f, "r") as fp:
                    results.append(json.load(fp))
            except Exception as e:
                print(f"Error reading {f}: {e}")
        
        # Sort by day offset (0=Mon to 4=Fri)
        results.sort(key=lambda x: x.get("day_offset", 0))
        
        success_count = sum(1 for r in results if r["success"])
        total_count = 5  # We expect 5 days
        
        summary_lines = [
            f"📅 <b>WEEKLY BOOKING SUMMARY</b>",
            f"Location: Kompleks Sukan KBS",
            f"Total: {success_count}/{total_count} booked",
            ""
        ]
        
        # Ensure we have entries for all days (even if missing files)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        
        # Initialize map with placeholders
        final_results = {}
        for i in range(5):
            # Calculate date for this offset (approximate if not in results)
            # This is tricky without reference, but we usually have results.
            # If result missing, we mark as Failed/Unknown
            final_results[i] = {
                "day_name": day_names[i],
                "date": "???", 
                "time_start": "??:??:??", 
                "time_end": "??:??:??", 
                "success": False, 
                "court_name": None,
                "missing": True
            }
        
        # Fill in actual results
        for r in results:
            offset = r.get("day_offset")
            if offset is not None:
                final_results[offset] = r
                final_results[offset]["missing"] = False
        
        # Build the message
        for i in range(5):
            r = final_results[i]
            
            # Calculate hours if times available
            time_str = ""
            if r["time_start"] != "??:??:??":
                try:
                    from datetime import datetime as dt
                    t_start = dt.strptime(r["time_start"], "%H:%M:%S")
                    t_end = dt.strptime(r["time_end"], "%H:%M:%S")
                    hours = int((t_end - t_start).seconds / 3600)
                    time_str = f"    Time: {r['time_start']}-{r['time_end']} ({hours}h)"
                except:
                    time_str = f"    Time: {r['time_start']}-{r['time_end']}"
            
            status = "✅" if r["success"] else "❌"
            date_info = f"({r['date']})" if r['date'] != "???" else ""
            
            # Format:
            # ✅ Monday (23/02/2026) 
            #     Venue: Gelanggang Tenis 1
            #     Time: 21:00:00-22:00:00 (1h)
            
            summary_lines.append(f"{status} {r['day_name']} {date_info}")
            
            if r["success"] and r["court_name"]:
                summary_lines.append(f"    Venue: {r['court_name']}")
            
            if time_str:
                summary_lines.append(time_str)
            elif r.get("missing"):
                summary_lines.append("    (Job failed or result missing)")
        
        full_message = "\n".join(summary_lines)
        print(full_message)
        booker.send_telegram(full_message)
        
        return 0

    # BOOK WEEK MODE: Book all 5 weekday slots (Mon-Fri)
    if args.book_week:
        print("=" * 50)
        print("BOOK WEEK MODE: Booking Mon-Fri slots")
        print("=" * 50)
        
        weekly_targets = get_weekly_booking_targets()
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        print(f"Targets: {len(weekly_targets)} days")
        for i, (date, ts, te) in enumerate(weekly_targets):
            print(f"  [{i}] {day_names[i]}: {date} {ts}-{te}")
        
        results = []
        for i, (date, time_start, time_end) in enumerate(weekly_targets):
            print(f"\n{'='*50}")
            print(f"[{i+1}/5] Booking {day_names[i]} ({date})")
            print(f"{'='*50}")
            
            config = {
                "venue_id": args.venue_id,
                "facility_id_encoded": args.facility_id,
                "facility_id": args.facility_id_num,
                "facility_index": args.facility_index,
                "tjk_id": args.tjk_id,
                "retry_facility_index": args.retry_facility_index,
                "retry_facility_id": args.retry_facility_id,
                "retry_facility_id_num": args.retry_facility_id_num,
                "retry_tjk_id": args.retry_tjk_id,
                "venue_id_num": args.venue_id_num,
                "date": date,
                "time_start": time_start,
                "time_end": time_end,
                "neg": args.neg,
                "num_users": args.num_users,
                "purpose": args.purpose,
            }
            
            # For weekly booking, use shorter timeout per slot
            slot_timeout = min(args.poll_timeout // 5, 600)  # Max 10 min per slot
            result = booker.run(config, poll_timeout=slot_timeout, check_interval=args.check_interval)
            
            # Handle dict return format
            if isinstance(result, dict):
                success = result.get("success", False)
                court_name = result.get("court_name", "Unknown")
            else:
                # Fallback for bool return (shouldn't happen but just in case)
                success = bool(result)
                court_name = "Unknown"
            
            results.append((day_names[i], date, time_start, time_end, success, court_name))
            
            # Explicit continuation message regardless of success/failure
            if success:
                print(f"✅ {day_names[i]} booked successfully! (Court: {court_name})")
                # Note: Individual success messages are already sent by booker.run()
            else:
                print(f"❌ {day_names[i]} booking failed (both courts unavailable or timeout).")
            
            remaining = 5 - (i + 1)
            if remaining > 0:
                print(f"➡️  Continuing to next day... ({remaining} remaining)")
        
        print("\n" + "=" * 50)
        print("WEEKLY BOOKING SUMMARY")
        print("=" * 50)
        success_count = sum(1 for r in results if r[4])
        fail_count = len(results) - success_count
        print(f"Total: {success_count} SUCCESS, {fail_count} FAILED")
        for day, date, ts, te, success, court in results:
            status = "✅ SUCCESS" if success else "❌ FAILED"
            court_info = f" ({court})" if success and court else ""
            print(f"  {day} ({date}): {status}{court_info}")
        
        # Send Telegram summary in detailed format
        summary_lines = [
            f"📅 <b>WEEKLY BOOKING SUMMARY</b>",
            f"Location: Kompleks Sukan KBS",
            f"Total: {success_count}/5 booked",
            ""
        ]
        for day, date, ts, te, success, court in results:
            # Calculate hours
            from datetime import datetime as dt
            t_start = dt.strptime(ts, "%H:%M:%S")
            t_end = dt.strptime(te, "%H:%M:%S")
            hours = int((t_end - t_start).seconds / 3600)
            
            status = "✅" if success else "❌"
            court_info = f" - {court}" if success and court else ""
            summary_lines.append(f"{status} {day} ({date}){court_info}")
            summary_lines.append(f"    Time: {ts}-{te} ({hours}h)")
        
        booker.send_telegram("\n".join(summary_lines))
        
        # Return success if at least one day was booked
        any_success = any(r[4] for r in results)
        return 0 if any_success else 1

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
        "retry_facility_index": args.retry_facility_index,
        "retry_facility_id": args.retry_facility_id,
        "retry_facility_id_num": args.retry_facility_id_num,
        "retry_tjk_id": args.retry_tjk_id,
        "venue_id_num": args.venue_id_num,
        "date": args.date,
        "time_start": args.time_start,
        "time_end": args.time_end,
        "neg": args.neg,
        "num_users": args.num_users,
        "purpose": args.purpose,
    }
    result = booker.run(
        config,
        poll_timeout=args.poll_timeout,
        check_interval=args.check_interval
    )
    
    # Handle dict return format
    if isinstance(result, dict):
        success = result.get("success", False)
    else:
        success = bool(result)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())

