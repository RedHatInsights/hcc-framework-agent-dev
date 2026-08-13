# Preflight Script Tests

Unit and integration tests for quality-monitor preflight scripts.

## Setup

Install test dependencies with uv:

```bash
cd instance/quality-monitor/agent/workflows/quality-monitor/preflight
uv sync --extra dev
```

## Running Tests

### All tests

```bash
cd instance/quality-monitor/agent/workflows/quality-monitor/preflight
uv run pytest
```

### Specific test file

```bash
uv run pytest tests/test_01_check_merged_prs.py
uv run pytest tests/test_02_scan_test_anti_patterns.py
```

### Specific test class or function

```bash
uv run pytest tests/test_02_scan_test_anti_patterns.py::TestExpandBracePatterns
uv run pytest tests/test_01_check_merged_prs.py::TestCheckPrViolations::test_detects_failed_checks
```

### With coverage

```bash
uv run pytest --cov=. --cov-report=html --cov-report=term
```

## Test Coverage

### test_01_check_merged_prs.py

Tests for merge violation detection:
- `TestCheckPrViolations` - Core violation detection logic
  - Failed check detection (FAILURE, CANCELLED, SKIPPED)
  - All-passing check handling
  - Error handling (gh CLI errors, timeouts, invalid JSON)
  - PR metadata inclusion
- `TestMainFunction` - Integration tests
  - Skip conditions (already scanned, at capacity, too many violations)
  - Violation processing and output
  - Non-GitHub repo filtering
  - 24-hour time window filtering
- `TestSeverityAssessment` - Severity classification
  - HIGH severity for FAILURE
  - MEDIUM severity for CANCELLED
  - LOW severity for SKIPPED

### test_02_scan_test_anti_patterns.py

Tests for test anti-pattern detection:
- `TestExpandBracePatterns` - Brace pattern expansion
  - Simple patterns (no braces)
  - Single brace expansion
  - Multiple options
  - Nested braces
- `TestDetectFramework` - Framework auto-detection
  - Playwright detection (playwright.config.ts/js)
  - No framework detected
  - No config provided
- `TestGetTestPatterns` - Pattern resolution
  - Repo-specific overrides
  - Playwright auto-detection
  - Generic fallback
  - No config fallback
- `TestFindTestFiles` - File discovery
  - Pattern matching
  - Exclude patterns
  - Max files limit
  - Large file filtering
  - Brace pattern expansion
- `TestLoadTestConfig` - YAML configuration loading
- `TestMainFunction` - Integration tests
  - Skip conditions (already scanned, at capacity, too many scans)

## Dependencies

Test dependencies are managed via `pyproject.toml`:
- `pytest>=8.0.0`
- `pytest-cov>=4.1.0`
- `pyyaml>=6.0`

Dependencies are installed automatically with `uv sync --extra dev`.

## Test Design

Tests mock the `common` module to avoid dependencies on bot infrastructure. This allows:
- Fast, isolated unit tests
- No external API calls (gh CLI, git)
- Deterministic behavior

### Mocking Strategy

Each test file uses an `autouse` fixture to mock the `common` module:
```python
@pytest.fixture(autouse=True)
def mock_common_module():
    mock_common = Mock()
    mock_common.load_project_repos = Mock(return_value={})
    mock_common.output_result = Mock()
    # ... other mocks
    sys.modules["common"] = mock_common
    yield mock_common
    del sys.modules["common"]
```

This ensures tests run without requiring bot infrastructure.

## CI Integration

These tests can be integrated into CI workflows:

```yaml
- name: Run preflight tests
  run: |
    cd instance/quality-monitor/agent/workflows/quality-monitor/preflight
    uv sync --extra dev
    uv run pytest --cov=. --cov-report=xml
```
