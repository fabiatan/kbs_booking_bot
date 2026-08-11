# Test Coverage Analysis Report
**Date:** 2026-01-19
**Project:** KBS Booking Bot
**Current Test Coverage:** 10% (56 of 547 statements)

---

## Executive Summary

The current test suite covers only **10%** of the codebase, focusing exclusively on helper functions and configuration constants. The **core business logic** in the `KBSBooker` class (90% of the application) has **zero test coverage**. This represents a significant risk for:

- Undetected regressions during refactoring
- Difficulty diagnosing booking failures
- Lack of confidence in code changes
- No validation of error handling

---

## Current Test Coverage Breakdown

### ✅ What's Tested (56 statements, 10%)

| Component | Tests | Coverage | Status |
|-----------|-------|----------|--------|
| `get_booking_target()` | 8 tests | 100% | ✅ Excellent |
| `build_config()` | 3 tests | 100% | ✅ Excellent |
| `calculate_booking_price()` | 7 tests | 100% | ✅ Excellent |
| `TIME_SLOTS` constant | 4 tests | 100% | ✅ Good |
| `DAY_NAMES` constant | 2 tests | 100% | ✅ Good |
| `MYT` timezone | 1 test | 100% | ✅ Good |

**Total:** 25 tests, all passing

### ❌ What's NOT Tested (491 statements, 90%)

| Component | Lines | Criticality | Impact |
|-----------|-------|-------------|--------|
| `KBSBooker.login()` | 62 lines | 🔴 CRITICAL | Authentication failure = no bookings |
| `KBSBooker.run()` | 269 lines | 🔴 CRITICAL | Main orchestration logic |
| `KBSBooker.check_slot()` | 20 lines | 🟠 HIGH | Availability detection errors |
| `KBSBooker.book_slot()` | 56 lines | 🟠 HIGH | Booking submission failures |
| `KBSBooker.get_calendar_page()` | 81 lines | 🟠 HIGH | Token extraction with retry logic |
| `KBSBooker.confirm_booking()` | 17 lines | 🟡 MEDIUM | Confirmation step |
| `KBSBooker.get_facility_list()` | 35 lines | 🟡 MEDIUM | Facility discovery |
| `KBSBooker.send_telegram()` | 7 lines | 🟢 LOW | Notification delivery |
| `main()` function | 317 lines | 🟡 MEDIUM | CLI argument handling |

---

## Critical Gaps & Risk Assessment

### 🔴 CRITICAL - Must Address

#### 1. **No Integration Tests**
**Risk:** Cannot verify end-to-end booking flow works correctly

**Impact:**
- Hidden bugs in the booking workflow
- Token expiry issues undetected
- Session management problems
- Network retry logic untested

**Example Scenarios NOT Tested:**
- Full booking flow: login → get token → check availability → book → confirm
- Token refresh after long polling
- Facility retry logic when primary court fails
- Parallel booking with multiple jobs

---

#### 2. **Authentication Logic Untested (`login()`)**
**Risk:** Login failures will break ALL bookings

**Impact:**
- Hidden form token extraction bugs
- Incorrect session handling
- CSRF token parsing failures
- Login detection logic errors

**Specific Gaps (kbs_booker_bot.py:175-245):**
- Token extraction regex patterns (lines 194-200)
- Login response validation (lines 229-241)
- Error handling for network failures
- Session cookie persistence

**Recommended Tests:**
```python
def test_login_success():
    """Test successful login flow"""
    # Mock login page response with valid tokens
    # Verify session cookies set correctly

def test_login_token_extraction_failure():
    """Test login fails gracefully when tokens missing"""
    # Mock page with malformed HTML
    # Verify returns False and logs error

def test_login_invalid_credentials():
    """Test login fails with wrong password"""
    # Mock failed login response
    # Verify login detection logic
```

---

#### 3. **Booking Orchestration Untested (`run()`)**
**Risk:** Main workflow has 269 lines of complex logic with zero tests

**Impact:**
- Polling timeout logic untested
- Facility retry logic unverified (lines 718-807)
- Token refresh logic unvalidated (lines 681-687)
- Success detection may fail silently

**Critical Paths NOT Tested:**
- Slot availability polling loop (lines 649-821)
- Primary facility failure + secondary retry (lines 718-810)
- Token refresh after 40 minutes (lines 681-687)
- Venue polling when closed (lines 576-609)
- Booking confirmation flow (lines 699-712)

**Recommended Tests:**
```python
def test_run_successful_booking():
    """Test successful booking with first availability check"""

def test_run_polling_timeout():
    """Test timeout after max polling time"""

def test_run_facility_retry_on_failure():
    """Test retry with secondary facility when primary fails"""

def test_run_token_refresh_after_long_wait():
    """Test token refresh after 40+ minutes polling"""

def test_run_venue_closed_polling():
    """Test polling for venue availability when initially closed"""
```

---

### 🟠 HIGH Priority

#### 4. **Slot Checking Logic Untested (`check_slot()`)**
**Risk:** Incorrect availability detection = missed bookings or false bookings

**Lines:** 391-429

**Gaps:**
- Response parsing logic (lines 419-420)
- Availability determination heuristics
- Edge cases (empty response, malformed data)

**Recommended Tests:**
```python
def test_check_slot_available():
    """Test slot availability detection"""

def test_check_slot_taken():
    """Test slot unavailability detection"""

def test_check_slot_network_error():
    """Test error handling for network failures"""

def test_check_slot_malformed_response():
    """Test handling of unexpected response formats"""
```

---

#### 5. **Booking Submission Untested (`book_slot()`)**
**Risk:** Booking may fail silently or succeed without confirmation

**Lines:** 431-499

**Gaps:**
- Form data construction (lines 446-473)
- Success detection from redirect URL (line 479)
- Booking ID extraction (lines 482-486)
- Price calculation integration

**Recommended Tests:**
```python
def test_book_slot_success():
    """Test successful booking submission"""

def test_book_slot_failure():
    """Test booking failure detection"""

def test_book_slot_missing_booking_id():
    """Test handling when booking ID not returned"""

def test_book_slot_network_timeout():
    """Test network timeout during booking"""
```

---

#### 6. **Calendar Page Token Extraction (`get_calendar_page()`)**
**Risk:** Token extraction failure = cannot book (no ks_token)

**Lines:** 293-389

**Gaps:**
- Retry logic with exponential backoff (lines 309-389)
- Multiple regex pattern matching (lines 364-376)
- Server error detection and recovery (lines 352-361)
- Session refresh on errors (lines 359-360)

**Recommended Tests:**
```python
def test_get_calendar_page_success():
    """Test successful token extraction"""

def test_get_calendar_page_retry_on_server_error():
    """Test retry logic when server returns error"""

def test_get_calendar_page_token_not_found():
    """Test failure after max retries"""

def test_get_calendar_page_multiple_patterns():
    """Test all regex patterns for token extraction"""
```

---

### 🟡 MEDIUM Priority

#### 7. **Facility List Parsing Untested (`get_facility_list()`)**
**Lines:** 247-291

**Recommended Tests:**
```python
def test_get_facility_list_success():
    """Test facility link extraction"""

def test_get_facility_list_empty():
    """Test handling when no facilities found"""

def test_get_facility_list_malformed_html():
    """Test error handling for malformed HTML"""
```

---

#### 8. **Booking Confirmation Untested (`confirm_booking()`)**
**Lines:** 511-539

**Recommended Tests:**
```python
def test_confirm_booking_success():
    """Test successful booking confirmation"""

def test_confirm_booking_failure():
    """Test confirmation failure detection"""

def test_confirm_booking_network_error():
    """Test network error handling"""
```

---

#### 9. **CLI Argument Handling Untested (`main()`)**
**Lines:** 824-1141

**Gaps:**
- Single day mode (--day-offset)
- Week booking mode (--book-week)
- Summary report mode (--summary-report)
- Facility listing mode (--list-facilities)
- Auto-detection fallback logic

**Recommended Tests:**
```python
def test_main_single_day_mode():
    """Test single day booking with --day-offset"""

def test_main_book_week_mode():
    """Test weekly booking mode"""

def test_main_summary_report():
    """Test summary report generation"""

def test_main_auto_date_calculation():
    """Test automatic date/time calculation"""
```

---

### 🟢 LOW Priority

#### 10. **Telegram Notification Testing**
**Lines:** 166-173

**Recommended Tests:**
```python
def test_send_telegram_success():
    """Test successful Telegram message"""

def test_send_telegram_failure():
    """Test graceful failure on network error"""
```

---

## Recommended Testing Strategy

### Phase 1: Critical Path Coverage (1-2 weeks)
**Goal:** Cover the most critical business logic first

1. **Authentication Tests** (2-3 days)
   - Test `login()` with mock responses
   - Test token extraction edge cases
   - Test session management

2. **Booking Flow Integration Tests** (3-4 days)
   - Test `run()` happy path
   - Test facility retry logic
   - Test token refresh
   - Test timeout scenarios

3. **API Interaction Tests** (2-3 days)
   - Test `check_slot()` with various responses
   - Test `book_slot()` success/failure paths
   - Test `confirm_booking()` flow

**Target Coverage:** 40-50%

---

### Phase 2: Edge Cases & Error Handling (1 week)
**Goal:** Test error conditions and edge cases

1. **Network Failure Scenarios**
   - Timeout handling
   - Connection errors
   - Retry logic validation

2. **Server Error Responses**
   - Malformed HTML
   - Server errors (500, 502, etc.)
   - Empty responses

3. **Token & Session Management**
   - Token expiry
   - Session timeout
   - Cookie persistence

**Target Coverage:** 60-70%

---

### Phase 3: CLI & Integration (1 week)
**Goal:** Test user-facing features and workflows

1. **CLI Argument Processing**
   - All command-line modes
   - Argument validation
   - Error messages

2. **Parallel Booking**
   - Multi-job execution
   - Result aggregation
   - Summary reports

3. **End-to-End Integration**
   - Full workflow tests (login → book → confirm)
   - Multi-day booking
   - Telegram notification flow

**Target Coverage:** 80-90%

---

## Testing Tools & Setup

### Recommended Testing Stack

1. **Unit Testing:** `unittest` (already in use) or `pytest`
2. **Mocking:** `unittest.mock` (already in use) or `responses`
3. **HTTP Mocking:** `responses` library for API calls
4. **Coverage:** `coverage.py` (already installed)
5. **CI/CD:** GitHub Actions workflow for running tests

### Setup Test Infrastructure

```bash
# Install testing dependencies
pip install pytest pytest-cov responses

# Run tests with coverage
pytest --cov=kbs_booker_bot --cov-report=html --cov-report=term

# Run specific test file
pytest test_kbs_booker_bot.py -v
```

### Example: Setting Up Mock HTTP Responses

```python
import responses
import requests

@responses.activate
def test_login_success():
    """Test successful login with mocked HTTP responses"""
    # Mock the login page
    responses.add(
        responses.GET,
        'https://stf.kbs.gov.my/ks_user/login.php',
        body='<input name="key" value="test_key"><input name="value" value="test_value">',
        status=200
    )

    # Mock the login handler
    responses.add(
        responses.POST,
        'https://stf.kbs.gov.my/ks_user/login_handler.php',
        body='<html>Selamat datang</html>',
        status=200
    )

    booker = KBSBooker('test_user', 'test_pass')
    assert booker.login() == True
```

---

## GitHub Actions CI/CD Integration

### Recommended: Add Test Workflow

Create `.github/workflows/test.yml`:

```yaml
name: Test Suite

on:
  push:
    branches: [ main, claude/** ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov responses

      - name: Run tests with coverage
        run: |
          pytest --cov=kbs_booker_bot --cov-report=xml --cov-report=term

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: false
```

---

## Specific Test Examples to Implement

### Example 1: Test Login with Token Extraction

```python
import unittest
from unittest.mock import Mock, patch
from kbs_booker_bot import KBSBooker

class TestKBSBookerLogin(unittest.TestCase):

    @patch('kbs_booker_bot.requests.Session')
    def test_login_success(self, mock_session):
        """Test successful login flow"""
        # Setup mock responses
        mock_get = Mock()
        mock_get.text = '''
            <form>
                <input type="hidden" name="key" value="abc123">
                <input type="hidden" name="value" value="xyz789">
            </form>
        '''
        mock_get.status_code = 200

        mock_post = Mock()
        mock_post.url = 'https://stf.kbs.gov.my/ks_user/home.php'
        mock_post.text = 'Selamat datang'
        mock_post.status_code = 200

        mock_session_instance = mock_session.return_value
        mock_session_instance.get.return_value = mock_get
        mock_session_instance.post.return_value = mock_post

        # Test login
        booker = KBSBooker('test_user', 'test_pass')
        result = booker.login()

        # Assertions
        self.assertTrue(result)
        self.assertTrue(booker.logged_in)
        mock_session_instance.get.assert_called_once()
        mock_session_instance.post.assert_called_once()

    @patch('kbs_booker_bot.requests.Session')
    def test_login_token_extraction_failure(self, mock_session):
        """Test login fails when tokens cannot be extracted"""
        # Setup mock with malformed HTML
        mock_get = Mock()
        mock_get.text = '<form>No tokens here</form>'
        mock_get.status_code = 200

        mock_session_instance = mock_session.return_value
        mock_session_instance.get.return_value = mock_get

        # Test login
        booker = KBSBooker('test_user', 'test_pass')
        result = booker.login()

        # Assertions
        self.assertFalse(result)
        self.assertFalse(booker.logged_in)
```

### Example 2: Test Booking Flow with Retry Logic

```python
class TestKBSBookerRun(unittest.TestCase):

    @patch.object(KBSBooker, 'confirm_booking')
    @patch.object(KBSBooker, 'book_slot')
    @patch.object(KBSBooker, 'check_slot')
    @patch.object(KBSBooker, 'get_calendar_page')
    @patch.object(KBSBooker, 'get_facility_list')
    @patch.object(KBSBooker, 'login')
    def test_run_successful_booking_on_first_try(
        self, mock_login, mock_get_facilities, mock_get_calendar,
        mock_check_slot, mock_book_slot, mock_confirm
    ):
        """Test successful booking flow on first availability check"""
        # Setup mocks
        mock_login.return_value = True
        mock_get_facilities.return_value = [
            {'facility_id_encoded': 'test_fac_1', 'venue_id': 'venue_1', 'neg': '07'}
        ]
        mock_check_slot.return_value = {'available': True, 'status': 200, 'text': 'ok'}
        mock_book_slot.return_value = {
            'success': True,
            'booking_id': '12345',
            'url': 'https://stf.kbs.gov.my/booking/added',
            'status': 200
        }
        mock_confirm.return_value = {'success': True, 'status': 200}

        # Create booker and config
        booker = KBSBooker('test_user', 'test_pass')
        booker.ks_token = 'test_token'

        config = {
            'venue_id': 'venue_1',
            'facility_id': 114,
            'tjk_id': 624,
            'date': '01/02/2026',
            'time_start': '19:00:00',
            'time_end': '21:00:00',
            'facility_index': 0,
            'neg': '07'
        }

        # Run booking
        result = booker.run(config, poll_timeout=10, check_interval=0.1)

        # Assertions
        self.assertTrue(result['success'])
        self.assertEqual(result['court_name'], 'Gelanggang Tenis 1')
        mock_check_slot.assert_called_once()
        mock_book_slot.assert_called_once()
        mock_confirm.assert_called_once()
```

### Example 3: Test Facility Retry Logic

```python
@patch.object(KBSBooker, 'book_slot')
@patch.object(KBSBooker, 'check_slot')
@patch.object(KBSBooker, 'get_facility_list')
def test_run_facility_retry_on_primary_failure(
    self, mock_get_facilities, mock_check_slot, mock_book_slot
):
    """Test retry with secondary facility when primary booking fails"""
    # Setup mocks
    mock_get_facilities.return_value = [
        {'facility_id_encoded': 'fac_1', 'venue_id': 'venue_1', 'neg': '07'},
        {'facility_id_encoded': 'fac_2', 'venue_id': 'venue_1', 'neg': '07'}
    ]

    # Slot is available
    mock_check_slot.return_value = {'available': True, 'status': 200, 'text': 'ok'}

    # First booking fails, second succeeds
    mock_book_slot.side_effect = [
        {'success': False, 'url': 'fail', 'status': 400},  # Primary fails
        {'success': True, 'booking_id': '123', 'url': 'success', 'status': 200}  # Retry succeeds
    ]

    booker = KBSBooker('test_user', 'test_pass')
    booker.logged_in = True
    booker.ks_token = 'test_token'

    config = {
        'venue_id': 'venue_1',
        'facility_id': 114,
        'tjk_id': 624,
        'retry_facility_index': 1,
        'retry_facility_id_num': 202,
        'retry_tjk_id': 625,
        'date': '01/02/2026',
        'time_start': '19:00:00',
        'time_end': '21:00:00',
        'facility_index': 0,
        'neg': '07'
    }

    result = booker.run(config, poll_timeout=10, check_interval=0.1)

    # Assertions
    self.assertTrue(result['success'])
    self.assertEqual(result['court_name'], 'Gelanggang Tenis 2')  # Retry facility
    self.assertEqual(mock_book_slot.call_count, 2)  # Called twice
```

---

## Priority Recommendations Summary

### Immediate Actions (This Week)

1. ✅ **Create test infrastructure for HTTP mocking**
   - Install `responses` library
   - Create test fixtures for common responses

2. ✅ **Add authentication tests**
   - Test `login()` with 3-5 test cases
   - Cover success, failure, and token extraction edge cases

3. ✅ **Add basic integration test**
   - Single end-to-end test for happy path
   - Mock all HTTP calls

### Short Term (2-4 Weeks)

4. **Cover critical business logic**
   - Test `run()` orchestration
   - Test `check_slot()` and `book_slot()`
   - Test facility retry logic

5. **Add GitHub Actions CI workflow**
   - Run tests on every push
   - Generate coverage reports

### Medium Term (1-2 Months)

6. **Expand to edge cases**
   - Network failures
   - Server errors
   - Token expiry scenarios

7. **Add CLI testing**
   - Test all command-line modes
   - Test argument validation

### Long Term (Ongoing)

8. **Maintain coverage above 70%**
   - Add tests for new features
   - Refactor brittle tests
   - Regular coverage reviews

---

## Success Metrics

### Target Coverage Goals

| Timeframe | Coverage | Focus |
|-----------|----------|-------|
| Current | 10% | Helper functions only |
| 2 weeks | 40-50% | Critical paths covered |
| 1 month | 60-70% | Error handling tested |
| 2 months | 80%+ | Comprehensive coverage |

### Quality Indicators

- ✅ All tests passing in CI/CD
- ✅ No decrease in coverage on new PRs
- ✅ Critical paths (login, book, confirm) have 100% coverage
- ✅ Network error scenarios tested
- ✅ Integration tests validate end-to-end flow

---

## Conclusion

The current 10% test coverage leaves the application vulnerable to regressions and makes debugging difficult. By following the phased approach outlined above, you can systematically improve coverage to 80%+ within 2 months.

**Key Priorities:**
1. Test authentication logic (highest risk)
2. Test booking orchestration (`run()`)
3. Add integration tests for end-to-end flows
4. Set up CI/CD with automated testing

**Next Steps:**
1. Review and approve this analysis
2. Create GitHub issues for high-priority test cases
3. Start with Phase 1: Critical Path Coverage
4. Set up GitHub Actions workflow for CI/CD

---

**Coverage Report Location:** `htmlcov/index.html`
**Run Coverage Report:** `python3 -m coverage html && open htmlcov/index.html`
