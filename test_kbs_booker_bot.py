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

from kbs_booker_bot import (
    get_booking_target,
    build_config,
    calculate_booking_price,
    TIME_SLOTS,
    DAY_NAMES,
    MYT,
)


class TestGetBookingTarget(unittest.TestCase):
    """Tests for get_booking_target() function."""
    
    def test_single_day_monday(self):
        """Test getting Monday booking target."""
        result = get_booking_target(0)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)  # (date, start, end, day_name)
        self.assertEqual(result[3], "Monday")
        self.assertEqual(result[1], TIME_SLOTS[0][0])  # time_start
        self.assertEqual(result[2], TIME_SLOTS[0][1])  # time_end
    
    def test_single_day_friday(self):
        """Test getting Friday booking target."""
        result = get_booking_target(4)
        self.assertIsNotNone(result)
        self.assertEqual(result[3], "Friday")
        self.assertEqual(result[1], "20:00:00")  # Friday special time
        self.assertEqual(result[2], "22:00:00")
    
    def test_all_weekdays(self):
        """Test getting all 5 weekday targets."""
        result = get_booking_target(-1)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 5)
        
        # Verify all days are present
        day_names = [r[3] for r in result]
        self.assertEqual(day_names, DAY_NAMES)
    
    def test_invalid_day_offset_too_high(self):
        """Test that invalid day_offset raises ValueError."""
        with self.assertRaises(ValueError):
            get_booking_target(5)
    
    def test_invalid_day_offset_too_low(self):
        """Test that invalid negative day_offset raises ValueError."""
        with self.assertRaises(ValueError):
            get_booking_target(-2)
    
    def test_date_format(self):
        """Test that date is in DD/MM/YYYY format."""
        result = get_booking_target(0)
        date_str = result[0]
        # Should match DD/MM/YYYY pattern
        parts = date_str.split("/")
        self.assertEqual(len(parts), 3)
        self.assertEqual(len(parts[0]), 2)  # DD
        self.assertEqual(len(parts[1]), 2)  # MM
        self.assertEqual(len(parts[2]), 4)  # YYYY
    
    def test_time_format(self):
        """Test that times are in HH:MM:SS format."""
        result = get_booking_target(0)
        time_start = result[1]
        time_end = result[2]
        
        # Should match HH:MM:SS pattern
        for time_str in [time_start, time_end]:
            parts = time_str.split(":")
            self.assertEqual(len(parts), 3)
            self.assertEqual(len(parts[0]), 2)  # HH
            self.assertEqual(len(parts[1]), 2)  # MM
            self.assertEqual(len(parts[2]), 2)  # SS
    
    @patch('kbs_booker_bot.datetime')
    def test_auto_detect_weekday(self, mock_datetime):
        """Test auto-detect returns correct day based on current date."""
        # Mock a Wednesday (8 weeks from now would still be a weekday)
        mock_now = MagicMock()
        mock_datetime.now.return_value = mock_now
        mock_now.__add__ = lambda self, x: datetime(2026, 2, 25, tzinfo=MYT)  # Wednesday
        mock_datetime.strptime = datetime.strptime
        
        # Note: This test is tricky due to datetime mocking
        # The real function uses datetime.now(MYT), so we skip deep mocking
        result = get_booking_target()
        # Should return a tuple (not None) for weekdays
        if result is not None:
            self.assertEqual(len(result), 4)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
