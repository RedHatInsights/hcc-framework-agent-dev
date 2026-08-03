# Quality Monitor Preflight Scripts

Determine if bot session should start.

## Production Scripts

**01-check-merged-prs.py** - Detects PRs merged with failed CI (24h window)

Returns:
- `skip` - Already scanned today / at capacity / no violations
- `start` - Violations found, formatted for AI

Detection:
- Queries GitHub via `gh` CLI for merged PRs
- Checks `statusCheckRollup` for FAILURE/CANCELLED/SKIPPED
- Severity: HIGH (FAILURE) > MEDIUM (CANCELLED) > LOW (SKIPPED)

**02-scan-test-anti-patterns.py** - Finds Playwright TypeScript tests

Returns:
- `skip` - Already scanned today / at capacity / no tests
- `start` - Test files found, AI analyzes vs anti-patterns.yaml

Detection:
- Auto-detects Playwright via `playwright.config.ts/js`
- Uses `test-config.yaml` patterns (configurable per-repo)
- Finds `**/*.spec.ts` files
- Limits: 20 files/repo, 3 repos/scan

## Manual Testing (local only)

**test_scanner.py** - Test anti-pattern scanner:
```bash
python3 test_scanner.py ~/repos/js/insights-chrome
```

**test_merge_checker.py** - Test merge checker:
```bash
python3 test_merge_checker.py ~/repos/js/landing-page-frontend
python3 test_merge_checker.py ~/repos/js/insights-chrome 20  # Last 20 PRs
```

## Configuration

**test-config.yaml** - Controls test file scanning

Auto-detection: Finds `playwright.config.ts/js`

Per-repo override:
```yaml
repos:
  insights-chrome:
    patterns: ["e2e/**/*.spec.ts"]
    exclude: ["**/*.skip.spec.ts"]
```

Limits:
- `max_files_per_repo: 20`
- `max_file_size_bytes: 102400`
- `max_repos_per_scan: 3`

**anti-patterns.yaml** - Pattern definitions (loaded by AI, not preflight)

## State Management

Prevents duplicate scans:
- `last_merge_check_scan: "2026-07-30"`
- `last_anti_pattern_scan: "2026-07-30"`

## Capacity Checks

Max concurrent tasks:
- 5 merge violation tasks
- 5 test scan tasks

Skips if bot at capacity (10 total active tasks).

## Tests

```bash
cd preflight
uv sync --extra dev
uv run pytest  # 53 tests, 92% coverage
```
