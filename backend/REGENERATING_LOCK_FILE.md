# Regenerating requirements.lock

The `requirements.lock` file is auto-generated and documents the complete pinned dependency tree that pip resolves when installing `requirements.txt`. It is maintained for reference and documentation purposes.

**Important:** The lock file is **NOT** used by Docker builds or CI — both install directly from `requirements.txt`. The lock file helps developers understand the full transitive dependency closure.

## When to Regenerate

Regenerate `requirements.lock` whenever you modify `requirements.txt`:

1. After updating any package version pin
2. After adding new dependencies
3. Before merging a PR that changes `requirements.txt`

## How to Regenerate

### Prerequisites

- Python 3.12+ (must match the Docker image runtime)
- `pip-tools` installed: `pip install pip-tools`
- A clean virtual environment (recommended)

### Steps

```bash
# 1. Navigate to backend directory
cd backend

# 2. (OPTIONAL) Create a fresh venv to ensure clean state
python3.12 -m venv /tmp/reqlo-lock-venv
source /tmp/reqlo-lock-venv/bin/activate

# 3. Install pip-tools
pip install --upgrade pip-tools

# 4. Regenerate the lock file from requirements.txt
pip-compile requirements.txt --output-file requirements.lock

# 5. Verify the lock file was generated correctly
# - Check Django version: should be >= 5.2.17
# - Check cryptography version: should be >= 50.0.0
# - Check sentence-transformers: should be >= 6.0.0
# - Check pypdf: should be >= 6.16.1
# - Check anthropic: should be >= 0.122.0

grep "^Django==" requirements.lock
grep "^cryptography==" requirements.lock
grep "^sentence-transformers==" requirements.lock
grep "^pypdf==" requirements.lock
grep "^anthropic==" requirements.lock

# 6. Stage and commit the updated lock file
git add requirements.lock
git commit -m "chore: regenerate requirements.lock from requirements.txt"
```

## Why requirements.txt → Lock File Drift Occurs

The `requirements.txt` file specifies version ranges (e.g., `Django>=5.2.17,<5.3`), while `requirements.lock` pins exact versions of every transitive dependency. Over time, new patch releases of upstream packages are published, but the lock file remains unchanged until it is explicitly regenerated. This is expected behavior and not a bug.

## CI Drift Validation

A CI job (`requirements-drift-check`) runs on every PR and commit to ensure that `requirements.txt` always specifies minimum versions that meet security floors:

- **Django:** >= 5.2.17 (fixes CVE-2026-48587, CVE-2026-6873, CVE-2026-8404, CVE-2026-48588, CVE-2026-53877, CVE-2026-53878)
- **cryptography:** >= 50.0.0 (fixes PYSEC-2026-3552: pkcs7_decrypt oracle)
- **pytest:** >= 9.1.1 (fixes CVE-2025-71176 / PYSEC-2026-1845)
- **pytest-django:** >= 4.14.0 (first release supporting pytest>=9 and Django>=5.2)
- **sentence-transformers:** >= 6.0.0 (requires transformers>=5.0.0 to fix RCE CVEs)

If you see the `requirements-drift-check` job fail, update the minimum versions in `requirements.txt` and re-run the job.

## Troubleshooting

**Q: `pip-compile` fails with package resolution errors**

A: Some packages have conflicting constraints. Common solutions:
- Update problematic packages to latest versions that are compatible
- Check for version conflicts manually: `pip install requirements.txt -v --dry-run`
- Consult the comments in `requirements.txt` for known constraints and rationales

**Q: The lock file is much larger than before**

A: This is normal. The lock file grows as transitive dependencies increase. Each dependency pulls in its own transitive tree, which gets flattened into a single lock file.

**Q: Can I edit the lock file manually?**

A: Not recommended. Any manual edits will be lost on the next regeneration. Always regenerate via `pip-compile`.
