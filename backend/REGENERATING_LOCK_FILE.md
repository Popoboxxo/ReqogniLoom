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

- Docker (the resolution runs inside a `python:3.12-slim` container)
- Network access to PyPI

**Do not run `pip-compile` on your host.** Dependency resolution is
platform-dependent — `torch` (pulled in by `sentence-transformers`) declares its
`nvidia-*` and `triton` wheels behind Linux environment markers only. A lock
generated on Windows or macOS silently omits ~20 packages and therefore does not
describe the image that is actually deployed. The container also pins CPython to
3.12, matching `backend/Dockerfile`.

### Steps

```bash
# 1. Navigate to backend directory
cd backend

# 2. Regenerate the lock file from requirements.txt (linux/amd64, CPython 3.12)
docker run --rm -v "$PWD:/w" -w /w python:3.12-slim sh -c \
  'pip install -q --upgrade pip pip-tools && \
   pip-compile requirements.txt --output-file requirements.lock \
     --no-header --no-annotate --strip-extras'

# 3. Re-apply the provenance header.
#    pip-compile emits a bare pin list; the comment block at the top of
#    requirements.lock (platform, regeneration command, "installed by nothing")
#    is maintained by hand — copy it back above the first pin.

# 4. Verify the lock file was generated correctly.
#    NOTE: pip-compile normalises distribution names to lower case, so the
#    pins read `django==`, not `Django==`.
# - Check Django version: should be >= 5.2.17
# - Check cryptography version: should be >= 50.0.0
# - Check sentence-transformers: should be >= 6.0.0
# - Check pypdf: should be >= 6.16.1
# - Check anthropic: should be >= 0.122.0

grep -iE "^(django|cryptography|sentence-transformers|pypdf|anthropic)==" requirements.lock

# 5. Stage and commit the updated lock file
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

A: Not recommended, with one exception: the provenance header block at the top of
the file is hand-maintained and must be re-applied after every regeneration
(`--no-header` suppresses pip-compile's own banner). Everything below the header
is generated — manual edits there will be lost on the next regeneration.

**Q: Why did the pre-2026-08-28 lock file contain `playwright`, `ruff`, `pywin32`, `graphifyy`…?**

A: It was never a `pip-compile` output despite claiming to be one. It was a
`pip freeze` taken on a developer workstation, so it carried ~120 packages that
are not in this project's dependency closure at all, while pinning Django 4.2.30
and cryptography 49.0.0 — both below the security floors `requirements.txt`
requires. If you find the lock and `requirements.txt` disagreeing on a
security-critical floor again, regenerate rather than hand-patching the pin.
