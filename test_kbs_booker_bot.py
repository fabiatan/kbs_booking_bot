#!/usr/bin/env python3
"""
Unit tests for KBS Booking Bot helper functions.

Run with: python3 -m pytest test_kbs_booker_bot.py -v
Or: python3 test_kbs_booker_bot.py
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
import argparse

import requests as requests_lib

from kbs_booker_bot import (
    get_target_date,
    build_config,
    calculate_booking_price,
    KBSBooker,
    TIME_SLOTS,
    DAY_NAMES,
    MYT,
)


class TestGetTargetDate(unittest.TestCase):
    """Tests for get_target_date() function."""
    
    @patch('kbs_booker_bot.datetime')
    def test_weekday_target(self, mock_datetime):
        """Test that a weekday target returns correct tuple."""
        # Mock today = Monday April 6, 2026 → +60 = Friday June 5, 2026
        mock_now = datetime(2026, 4, 6, 10, 0, 0, tzinfo=MYT)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = get_target_date(days_ahead=60)
        self.assertIsNotNone(result)
        date_str, time_start, time_end, day_name = result
        self.assertEqual(day_name, "Friday")
        self.assertEqual(date_str, "05/06/2026")
        self.assertEqual(time_start, TIME_SLOTS[4][0])  # Friday slot
    
    @patch('kbs_booker_bot.datetime')
    def test_weekend_target_returns_none_saturday(self, mock_datetime):
        """Test that Saturday target returns None."""
        # Mock today = Thursday April 9, 2026 → +60 = Sunday June 8, 2026 (weekend)
        # Actually let's find a date where +60 = Saturday
        # April 4 (Sat) + 60 = June 3 (Wed) — not a weekend
        # Need to find: target.weekday() == 5 (Saturday)
        # June 6, 2026 is Saturday. 60 days before = April 7, 2026 (Tuesday)
        mock_now = datetime(2026, 4, 7, 10, 0, 0, tzinfo=MYT)
        mock_datetime.now.return_value = mock_now
        
        result = get_target_date(days_ahead=60)
        # June 6, 2026 is a Saturday → should return None
        self.assertIsNone(result)
    
    @patch('kbs_booker_bot.datetime')
    def test_weekend_target_returns_none_sunday(self, mock_datetime):
        """Test that Sunday target returns None."""
        # June 7, 2026 is Sunday. 60 days before = April 8, 2026 (Wednesday)
        mock_now = datetime(2026, 4, 8, 10, 0, 0, tzinfo=MYT)
        mock_datetime.now.return_value = mock_now
        
        result = get_target_date(days_ahead=60)
        # June 7, 2026 is a Sunday → should return None
        self.assertIsNone(result)
    
    @patch('kbs_booker_bot.datetime')
    def test_date_format(self, mock_datetime):
        """Test that date is in DD/MM/YYYY format."""
        mock_now = datetime(2026, 4, 4, 10, 0, 0, tzinfo=MYT)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = get_target_date(days_ahead=60)
        if result is not None:
            date_str = result[0]
            parts = date_str.split("/")
            self.assertEqual(len(parts), 3)
            self.assertEqual(len(parts[0]), 2)  # DD
            self.assertEqual(len(parts[1]), 2)  # MM
            self.assertEqual(len(parts[2]), 4)  # YYYY
    
    @patch('kbs_booker_bot.datetime')
    def test_time_slots_applied(self, mock_datetime):
        """Test that correct time slot is applied based on target weekday."""
        # April 6 (Mon) + 60 = June 5 (Fri, weekday=4)
        mock_now = datetime(2026, 4, 6, 10, 0, 0, tzinfo=MYT)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = get_target_date(days_ahead=60)
        self.assertIsNotNone(result)
        _, time_start, time_end, _ = result
        expected_start, expected_end = TIME_SLOTS[4]  # Friday
        self.assertEqual(time_start, expected_start)
        self.assertEqual(time_end, expected_end)
    
    def test_default_days_ahead(self):
        """Test that default days_ahead is 60 and produces a result (may be None on weekends)."""
        result = get_target_date()
        # Result is either a tuple or None — both are valid
        if result is not None:
            self.assertEqual(len(result), 4)
    
    @patch('kbs_booker_bot.datetime')
    def test_custom_days_ahead(self, mock_datetime):
        """Test with custom days_ahead value."""
        mock_now = datetime(2026, 4, 4, 10, 0, 0, tzinfo=MYT)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = get_target_date(days_ahead=30)
        # April 4 + 30 = May 4, 2026 (Monday) → should return valid target
        if result is not None:
            self.assertEqual(result[3], "Monday")


class TestBuildConfig(unittest.TestCase):
    """Tests for build_config() function."""
    
    def setUp(self):
        """Set up mock args for tests."""
        self.mock_args = argparse.Namespace(
            venue_id="test_venue_123",
            facility_id="test_facility_456",
            facility_id_num=114,
            facility_index=0,
            tjk_id=624,
            retry_facility_index=1,
            retry_facility_id="retry_facility_789",
            retry_facility_id_num=202,
            retry_tjk_id=625,
            venue_id_num=2,
            neg="07",
            num_users="4",
            purpose="4",
        )
    
    def test_basic_config_building(self):
        """Test that build_config returns all required fields."""
        config = build_config(self.mock_args, "01/01/2026", "19:00:00", "21:00:00")
        
        # Check all required fields exist
        required_fields = [
            "venue_id", "facility_id_encoded", "facility_id", "facility_index",
            "tjk_id", "retry_facility_index", "retry_facility_id",
            "retry_facility_id_num", "retry_tjk_id", "venue_id_num",
            "date", "time_start", "time_end", "neg", "num_users", "purpose"
        ]
        for field in required_fields:
            self.assertIn(field, config)
    
    def test_config_values_match_args(self):
        """Test that config values match the input args."""
        config = build_config(self.mock_args, "01/01/2026", "19:00:00", "21:00:00")
        
        self.assertEqual(config["venue_id"], "test_venue_123")
        self.assertEqual(config["facility_id"], 114)
        self.assertEqual(config["tjk_id"], 624)
        self.assertEqual(config["date"], "01/01/2026")
        self.assertEqual(config["time_start"], "19:00:00")
        self.assertEqual(config["time_end"], "21:00:00")
    
    def test_config_is_dict(self):
        """Test that build_config returns a dict."""
        config = build_config(self.mock_args, "01/01/2026", "19:00:00", "21:00:00")
        self.assertIsInstance(config, dict)


class TestCalculateBookingPrice(unittest.TestCase):
    """Tests for calculate_booking_price() function."""
    
    def test_daytime_rate(self):
        """Test daytime rate (before 7pm) is RM 10/hour."""
        hours, total, rate = calculate_booking_price("10:00:00", "12:00:00")
        self.assertEqual(hours, 2)
        self.assertEqual(rate, 10)
        self.assertEqual(total, 20)
    
    def test_nighttime_rate_at_7pm(self):
        """Test nighttime rate (7pm onwards) is RM 15/hour."""
        hours, total, rate = calculate_booking_price("19:00:00", "21:00:00")
        self.assertEqual(hours, 2)
        self.assertEqual(rate, 15)
        self.assertEqual(total, 30)
    
    def test_nighttime_rate_after_7pm(self):
        """Test nighttime rate for slots starting after 7pm."""
        hours, total, rate = calculate_booking_price("21:00:00", "22:00:00")
        self.assertEqual(hours, 1)
        self.assertEqual(rate, 15)
        self.assertEqual(total, 15)
    
    def test_boundary_before_7pm(self):
        """Test rate at 6:59pm is still daytime rate."""
        hours, total, rate = calculate_booking_price("18:00:00", "19:00:00")
        self.assertEqual(rate, 10)
        self.assertEqual(total, 10)
    
    def test_four_hour_booking(self):
        """Test 4-hour booking calculation."""
        hours, total, rate = calculate_booking_price("08:00:00", "12:00:00")
        self.assertEqual(hours, 4)
        self.assertEqual(total, 40)  # 4 * 10
    
    def test_one_hour_night(self):
        """Test 1-hour nighttime booking."""
        hours, total, rate = calculate_booking_price("20:00:00", "21:00:00")
        self.assertEqual(hours, 1)
        self.assertEqual(total, 15)
    
    def test_returns_tuple(self):
        """Test that function returns a 3-tuple."""
        result = calculate_booking_price("19:00:00", "21:00:00")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)


class TestTimeSlots(unittest.TestCase):
    """Tests for TIME_SLOTS configuration."""
    
    def test_all_days_defined(self):
        """Test that all 5 weekdays are defined."""
        self.assertEqual(len(TIME_SLOTS), 5)
        for day in range(5):
            self.assertIn(day, TIME_SLOTS)
    
    def test_time_format_valid(self):
        """Test that all time slots have valid format."""
        for day, (start, end) in TIME_SLOTS.items():
            # Check format HH:MM:SS
            datetime.strptime(start, "%H:%M:%S")
            datetime.strptime(end, "%H:%M:%S")
    
    def test_friday_special(self):
        """Test that Friday has special time slot."""
        friday_start, friday_end = TIME_SLOTS[4]
        self.assertEqual(friday_start, "20:00:00")
        self.assertEqual(friday_end, "22:00:00")
    
    def test_each_day_price_rate(self):
        """Test that each TIME_SLOT has correct rate based on start time."""
        for day, (start, end) in TIME_SLOTS.items():
            hours, total, rate = calculate_booking_price(start, end)
            start_hour = int(start.split(":")[0])
            expected_rate = 10 if start_hour < 19 else 15
            self.assertEqual(
                rate, expected_rate,
                f"{DAY_NAMES[day]} ({start}-{end}) should have rate RM{expected_rate}, got RM{rate}"
            )


class TestDayNames(unittest.TestCase):
    """Tests for DAY_NAMES configuration."""
    
    def test_all_weekdays(self):
        """Test that all 5 weekday names are present."""
        expected = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        self.assertEqual(DAY_NAMES, expected)
    
    def test_correct_order(self):
        """Test that days are in correct order."""
        self.assertEqual(DAY_NAMES[0], "Monday")
        self.assertEqual(DAY_NAMES[4], "Friday")


class TestMYTTimezone(unittest.TestCase):
    """Tests for MYT timezone configuration."""
    
    def test_myt_offset(self):
        """Test that MYT is UTC+8."""
        utc_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        myt_time = utc_time.astimezone(MYT)
        self.assertEqual(myt_time.hour, 8)


class TestLoginRetry(unittest.TestCase):
    """Tests for login() retry behavior on network errors."""

    def _make_booker(self):
        """Create a KBSBooker with dummy credentials."""
        return KBSBooker("dummy_user", "dummy_pass", debug=False)

    @patch.object(requests_lib.Session, 'post')
    @patch.object(requests_lib.Session, 'get')
    def test_login_succeeds_with_valid_response(self, mock_get, mock_post):
        """Test that login succeeds when server responds normally."""
        login_page_html = '<input name="key" value="abc123"><input name="value" value="def456">'
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.text = login_page_html
        mock_get.return_value = get_resp

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.url = "https://stf.kbs.gov.my/home.php"
        post_resp.text = "selamat datang"
        mock_post.return_value = post_resp

        booker = self._make_booker()
        result = booker.login()
        self.assertTrue(result)
        self.assertEqual(mock_get.call_count, 1)

    @patch.object(requests_lib.Session, 'get')
    def test_login_raises_on_timeout(self, mock_get):
        """Test that login raises ReadTimeout when server is unreachable."""
        mock_get.side_effect = requests_lib.exceptions.ReadTimeout("read timed out")

        booker = self._make_booker()
        with self.assertRaises(requests_lib.exceptions.ReadTimeout):
            booker.login()
        self.assertEqual(mock_get.call_count, 1)


class TestGetCalendarPage(unittest.TestCase):
    """Tests for get_calendar_page() — goes directly to calendar page."""

    def _make_booker(self):
        """Create a KBSBooker with dummy credentials."""
        booker = KBSBooker("dummy_user", "dummy_pass", debug=False)
        booker.logged_in = True  # Skip login
        return booker

    @patch.object(requests_lib.Session, 'get')
    def test_no_redundant_nav_pages(self, mock_get):
        """Nav pages (tempahan_home, listfasiliti) should NOT be fetched at all."""
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.text = "<html>no token here</html>"
        mock_get.return_value = empty_resp

        booker = self._make_booker()
        booker.get_calendar_page("vid", "fid", max_retries=3, retry_delay=0)

        # Collect all URLs that were fetched
        urls = [call.args[0] if call.args else call.kwargs.get('url', '') for call in mock_get.call_args_list]

        # tempahan_home and listfasiliti should NOT appear at all
        home_calls = [u for u in urls if 'tempahan_home' in u]
        list_calls = [u for u in urls if 'tempahan_listfasiliti' in u]
        cal_calls = [u for u in urls if 'tempahan_addcal' in u]

        self.assertEqual(len(home_calls), 0, "tempahan_home should NOT be called")
        self.assertEqual(len(list_calls), 0, "tempahan_listfasiliti should NOT be called")
        self.assertEqual(len(cal_calls), 3, "tempahan_addcal should be called on every attempt")

    @patch.object(requests_lib.Session, 'get')
    def test_uses_calendar_timeout(self, mock_get):
        """Calendar page request should use CALENDAR_TIMEOUT."""
        token_html = '<input name="ks_token" value="abcdef1234567890abcdef1234567890">'
        cal_resp = MagicMock()
        cal_resp.status_code = 200
        cal_resp.text = token_html
        mock_get.return_value = cal_resp

        booker = self._make_booker()
        booker.get_calendar_page("vid", "fid", max_retries=1, retry_delay=0)

        # Check the timeout used for the calendar page (1st call, no nav pages)
        cal_call = mock_get.call_args_list[0]
        self.assertEqual(cal_call.kwargs.get('timeout'), KBSBooker.CALENDAR_TIMEOUT)

    @patch.object(requests_lib.Session, 'get')
    def test_caches_last_ks_token(self, mock_get):
        """Successful token extraction should cache to _last_ks_token."""
        token_html = '<input name="ks_token" value="abcdef1234567890abcdef1234567890">'
        resp = MagicMock()
        resp.status_code = 200
        resp.text = token_html
        mock_get.return_value = resp

        booker = self._make_booker()
        self.assertIsNone(booker._last_ks_token)

        booker.get_calendar_page("vid", "fid", max_retries=1, retry_delay=0)

        self.assertEqual(booker._last_ks_token, "abcdef1234567890abcdef1234567890")
        self.assertEqual(booker.ks_token, booker._last_ks_token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
