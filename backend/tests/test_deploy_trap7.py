"""TRAP-7: the public link must open by checkpoint 2 (hosting #8, scripts/deploy.sh).

A wrong .env must stop the deploy before SSH; --dry-run must name the commit it deploys.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy.sh"
# On Windows a bare "bash" can be WSL (System32\bash.exe); use the one found in PATH.
BASH = shutil.which("bash") or "bash"
GIT = shutil.which("git")
VALID = {
    "DEPLOY_HOST": "203.0.113.10",
    "DEPLOY_USER": "deploy",
    "DEPLOY_SSH_KEY": "/nonexistent/key",
    "DEPLOY_DOMAIN": "shop.example.org",
    "DEPLOY_ACME_EMAIL": "ops@example.org",
}


def run(tmp_path: Path, *args: str, **overrides: str) -> tuple[subprocess.CompletedProcess, Path]:
    """Run deploy.sh in a clean environment (like env -i) with a fake ssh first in PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "ssh-calls"
    fake_ssh = bin_dir / "ssh"
    fake_ssh.write_text(f'#!/bin/sh\necho "$@" >> {calls}\nexit 99\n')
    fake_ssh.chmod(fake_ssh.stat().st_mode | stat.S_IXUSR)
    # A drive colon breaks "a:b" on Windows: join with os.pathsep and add the bash and git dirs.
    path = (
        os.pathsep.join([str(bin_dir), str(Path(BASH).parent), str(Path(GIT).parent)])
        if os.name == "nt"
        else f"{bin_dir}:/usr/bin:/bin"
    )
    env = {
        "PATH": path,
        "HOME": str(tmp_path),
        "DEPLOY_ENV_FILE": os.devnull,
        **VALID,
        **overrides,
    }
    proc = subprocess.run(
        [BASH, str(SCRIPT), *args],
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    return proc, calls


def test_trap7_empty_domain_stops_before_ssh(tmp_path):
    proc, calls = run(tmp_path, DEPLOY_DOMAIN="")
    assert proc.returncode == 2
    assert "DEPLOY_DOMAIN" in proc.stderr
    assert not calls.exists()


@pytest.mark.parametrize("domain", ["https://shop.example.org", "203.0.113.10"])
def test_trap7_domain_with_scheme_or_ip_rejected(tmp_path, domain):
    proc, calls = run(tmp_path, DEPLOY_DOMAIN=domain)
    assert proc.returncode == 2
    assert "DEPLOY_DOMAIN" in proc.stderr
    assert not calls.exists()


def test_trap7_dry_run_prints_origin_main_sha(tmp_path):
    sha = subprocess.run(
        ["git", "rev-parse", "origin/main"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    proc, calls = run(tmp_path, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert f"коммит: {sha}" in proc.stdout
    assert not calls.exists()
