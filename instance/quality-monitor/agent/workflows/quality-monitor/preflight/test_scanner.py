#!/usr/bin/env python3
"""Manual test runner for anti-pattern scanner.

MANUAL TESTING ONLY - not used by the bot workflow.
Run locally to validate scanner behavior against real repositories.
"""

import sys
from pathlib import Path

# Import scanner functions
sys.path.insert(0, str(Path(__file__).parent))

# Import after path setup
from importlib import util
spec = util.spec_from_file_location("scanner", "02-scan-test-anti-patterns.py")
scanner = util.module_from_spec(spec)

# Mock common module before loading scanner
from unittest.mock import Mock
mock_common = Mock()
sys.modules['common'] = mock_common

# Now execute the module
spec.loader.exec_module(scanner)


def test_repo(repo_path: str):
    """Test the scanner against a specific repository."""
    repo_path = Path(repo_path).expanduser()

    if not repo_path.exists():
        print(f"❌ Repository not found: {repo_path}")
        return

    print(f"\n🔍 Testing anti-pattern scanner on: {repo_path}")
    print("=" * 80)

    # Load test config
    config = scanner.load_test_config()
    if config:
        print("✅ Loaded test-config.yaml")
    else:
        print("⚠️  No test-config.yaml found, using hardcoded patterns")

    # Detect framework
    framework = scanner.detect_framework(repo_path, config)
    print(f"\n📦 Framework detection: {framework or 'none detected'}")

    # Get test patterns
    patterns, excludes = scanner.get_test_patterns(repo_path.name, repo_path, config)
    print(f"\n🎯 Test patterns:")
    for pattern in patterns:
        print(f"  - {pattern}")

    if excludes:
        print(f"\n🚫 Exclude patterns:")
        for exclude in excludes:
            print(f"  - {exclude}")

    # Find test files
    test_files = scanner.find_test_files(repo_path, repo_path.name, config, max_files=20)

    print(f"\n📄 Found {len(test_files)} test files:")
    for i, test_file in enumerate(test_files, 1):
        size_kb = test_file['size'] / 1024
        print(f"  {i:2d}. {test_file['path']} ({size_kb:.1f} KB)")

    if not test_files:
        print("  (no test files found)")

    print("\n" + "=" * 80)
    print(f"✅ Scanner test complete - found {len(test_files)} files to analyze\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_scanner.py <repo_path>")
        print("\nExamples:")
        print("  python test_scanner.py ~/repos/insights-chrome")
        print("  python test_scanner.py /path/to/any/repo")
        sys.exit(1)

    test_repo(sys.argv[1])
