# Quality Monitor Preflight Scripts

Preflight scripts run before each bot workflow session to determine if there's work to do.

## Production Scripts

These are executed by the bot workflow:

### 01-check-merged-prs.py
Detects PRs merged with failed CI checks in the last 24 hours.

**Returns:**
- `skip` - Already scanned today, at capacity, or no violations found
- `start` - Found violations, provides formatted data for AI to process

**Detection:**
- Queries GitHub via `gh` CLI for recently merged PRs
- Checks `statusCheckRollup` for FAILURE/CANCELLED/SKIPPED conclusions
- Assesses severity (HIGH for FAILURE, MEDIUM for CANCELLED, LOW for SKIPPED)

### 02-scan-test-anti-patterns.py
Finds Playwright TypeScript test files for AI analysis.

**Returns:**
- `skip` - Already scanned today, at capacity, or no test files found
- `start` - Found test files, provides list for AI to analyze against anti-patterns.yaml

**Detection:**
- Auto-detects Playwright via `playwright.config.ts/js` indicators
- Uses patterns from `test-config.yaml` (configurable per-repo)
- Finds `**/*.spec.ts` test files with size limits and excludes
- Limits: max 20 files per repo, 3 repos per scan

## Manual Testing Scripts

**NOT used by the bot** - for local validation only.

### test_scanner.py
Test the anti-pattern scanner against a local repository.

```bash
python3 test_scanner.py ~/repos/js/insights-chrome
```

Shows:
- Framework detection (playwright detected via config files)
- Test file patterns used
- Exclude patterns applied
- List of test files found

### test_merge_checker.py
Test the merge violation checker against a local repository.

```bash
# Requires GH_TOKEN or gh CLI auth
python3 test_merge_checker.py ~/repos/js/landing-page-frontend
python3 test_merge_checker.py ~/repos/js/insights-chrome 20  # Check last 20 PRs
```

Shows:
- Recent merged PRs (last 10 by default)
- PRs merged in last 24 hours
- Check status for each PR (passed or violated)
- Violation severity (HIGH/MEDIUM/LOW)

## Configuration

### test-config.yaml
Controls which test files are scanned.

**Auto-detection:**
- Looks for `playwright.config.ts/js` to detect Playwright
- Falls back to generic TypeScript test patterns if no framework found

**Customization:**
```yaml
repos:
  insights-chrome:
    patterns:
      - "e2e/**/*.spec.ts"
    exclude:
      - "**/*.skip.spec.ts"
```

**Limits:**
- `max_files_per_repo: 20` - Prevent overwhelming AI with too many files
- `max_file_size_bytes: 102400` - Skip very large test files (100KB)
- `max_repos_per_scan: 3` - Limit repos per scan

### anti-patterns.yaml
Defines what patterns the AI should look for when analyzing test files.

Loaded by the AI during the workflow session (not by preflight scripts).

## State Management

Both preflight scripts use state to prevent duplicate scans:
- `last_merge_check_scan: "2026-07-30"` - Only scan once per day
- `last_anti_pattern_scan: "2026-07-30"` - Only scan once per day

State is saved via `common.save_state()` and loaded via `common.load_state()`.

## Capacity Management

Scripts check capacity before returning `start`:
```python
active_n, max_n = get_capacity()
if active_n >= max_n:
    output_result("skip", f"At capacity ({active_n}/{max_n})")
```

Also limits concurrent tasks:
- Max 5 active merge violation tasks
- Max 5 active test scan tasks

## Testing

See `tests/` directory for unit and integration tests (37 tests, 92% coverage).

Run tests:
```bash
cd preflight
uv sync --extra dev
uv run pytest
```
