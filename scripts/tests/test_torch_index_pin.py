"""S5.1 WP-2 / DEP-005 — eliminate the dependency-confusion index path.

The backend image used to install torch through a secondary wheel index
(``--extra-index-url``), which makes pip consider two mutually untrusted
indexes for *every* package name and take the highest version from either.
The fix pins the CPU wheel as an exact PEP-508 URL with a sha256 hash in a
dedicated requirements file that is installed in the same pip resolution pass
as requirements.txt — one trusted index, one CPU torch wheel, verified bytes.

These are static build-smoke guards: they never build an image or hit the
network, so they run in the normal pytest suite on Python 3.12 as well.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
REQUIREMENTS = BACKEND_DIR / "requirements.txt"
TORCH_REQUIREMENTS = BACKEND_DIR / "requirements-torch.txt"
DOCKERFILE = BACKEND_DIR / "Dockerfile"

VCS_PIN = (
    "django-celery-beat @ git+https://github.com/celery/"
    "django-celery-beat.git@6767df6f6f723a96ebd38269a073a11cde124850"
)
# Direct-URL requirement: exact CPU wheel + per-requirement hash. The local
# version (``+cpu``) is percent-encoded as ``%2B`` in the URL, per PEP 508.
# Hash is a URL fragment so pip verifies it without activating global
# --require-hashes mode, which the django-celery-beat VCS pin cannot use.
TORCH_PIN_RE = re.compile(
    r"^torch @ https://download\.pytorch\.org/whl/cpu/"
    r"torch-\d+\.\d+\.\d+%2Bcpu-cp315-cp315-manylinux_2_28_x86_64\.whl"
    r"#sha256=[0-9a-f]{64}$",
    re.MULTILINE,
)


def _requirement_lines(path: Path) -> list[str]:
    """Return non-comment, non-blank lines of a requirements file."""
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_no_secondary_index_flag_in_any_dockerfile() -> None:
    dockerfiles = sorted(REPO_ROOT.rglob("Dockerfile*"))
    assert dockerfiles, "no Dockerfile found — guard is misconfigured"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in dockerfiles
        if "--extra-index-url" in path.read_text(encoding="utf-8")
        or "--index-url" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"secondary pip index flag found in: {offenders}"


def test_torch_is_pinned_by_url_with_sha256() -> None:
    """Exactly one torch requirement, an exact CPU wheel URL + verified hash."""
    assert TORCH_REQUIREMENTS.is_file(), "missing backend/requirements-torch.txt"
    torch_lines = [
        line for line in _requirement_lines(TORCH_REQUIREMENTS)
        if re.match(r"^torch\b", line)
    ]
    assert len(torch_lines) == 1, f"expected one torch pin, got {torch_lines}"
    assert TORCH_PIN_RE.fullmatch(torch_lines[0]), (
        f"torch pin is not an exact CPU wheel URL + sha256 hash: {torch_lines[0]}"
    )


def test_only_one_cpu_torch_would_be_installed() -> None:
    """Static build-smoke: no competing torch spec anywhere in build inputs."""
    specs: list[str] = []
    for path in (REQUIREMENTS, TORCH_REQUIREMENTS):
        for line in _requirement_lines(path):
            if re.match(r"^torch\b", line):
                specs.append(f"{path.name}: {line}")
    assert len(specs) == 1, f"duplicate/competing torch requirements: {specs}"
    # No other index override anywhere in the build inputs could re-resolve
    # torch to the default CUDA wheel from PyPI.
    for path in (DOCKERFILE, REQUIREMENTS, TORCH_REQUIREMENTS):
        text = path.read_text(encoding="utf-8")
        assert "--extra-index-url" not in text, f"secondary index in {path.name}"
        assert "--index-url" not in text, f"index override in {path.name}"


def _run_blocks(text: str) -> list[str]:
    """Return Dockerfile RUN instructions with backslash continuations joined."""
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("RUN "):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
            if not line.rstrip().endswith("\\"):
                blocks.append("\n".join(current))
                current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def test_dockerfile_installs_torch_pin_in_single_resolution_pass() -> None:
    """The pinned file must actually be used, in the same pip RUN as the rest."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY requirements.txt requirements-torch.txt ./" in text

    # The RUN block that installs requirements.txt must also install the torch
    # pin; otherwise the wheel URL is dead config and the CUDA wheel returns.
    pin_blocks = [
        block for block in _run_blocks(text)
        if re.search(r"(?<![\w-])-r\s+requirements\.txt(?![\w-])", block)
    ]
    assert len(pin_blocks) == 1, f"expected one requirements RUN block, got {len(pin_blocks)}"
    main_block = pin_blocks[0]
    assert re.search(r"(?<![\w-])-r\s+requirements-torch\.txt(?![\w-])", main_block), (
        "torch pin file is not installed in the same pip pass as requirements.txt"
    )
    others = [b for b in _run_blocks(text) if b != main_block]
    assert not any("requirements-torch.txt" in b for b in others), (
        "torch pin file installed in a second, separate pip pass"
    )


def test_no_global_require_hashes_mode() -> None:
    """--require-hashes is not viable here: 145 packages lack hashes and the
    django-celery-beat VCS pin is incompatible with that pip mode."""
    for path in (DOCKERFILE, REQUIREMENTS, TORCH_REQUIREMENTS):
        assert "--require-hashes" not in path.read_text(encoding="utf-8"), (
            f"global --require-hashes added in {path.name}"
        )


def test_django_celery_beat_vcs_pin_preserved() -> None:
    """The unrelated VCS pin must stay byte-for-byte unchanged (S5.1 scope)."""
    lines = _requirement_lines(REQUIREMENTS)
    assert lines.count(VCS_PIN) == 1, (
        "django-celery-beat VCS pin missing or altered — out of WP-2 scope"
    )
