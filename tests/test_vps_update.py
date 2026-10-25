"""Test of deploy/vps/update.sh (#8): a failed build or API never goes live, and is not retried.

uv, npm, systemctl, curl, sleep and alembic are stubs in a temporary HOME; git, flock and the
file tools are real. The stub API answers with GIT_SHA from sha.env unless backend/BROKEN exists.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STUBS = {
    "uv": "exit 0\n",
    "sleep": "exit 0\n",
    # npm ci → node_modules; npm run build → dist from web/app.txt, fails while web/BROKEN exists.
    "npm": """
echo "npm $*" >> "$HOME/log"
case "$1" in
  ci) mkdir -p node_modules ;;
  run) [ -e BROKEN ] && exit 1
       mkdir -p dist/assets dist/.vite
       cp app.txt dist/index.html
       echo x > "dist/assets/chunk-$(cat app.txt).js"
       echo '{}' > dist/.vite/manifest.json ;;
esac
""",
    # restart = ExecStartPre (alembic upgrade head) + start; the API is down while backend/BROKEN exists.
    "systemctl": """
echo "restart" >> "$HOME/log"
repo="$HOME/apps/lassard/repo"
cp "$repo/backend/HEADREV" "$HOME/db-rev"
if [ -e "$repo/backend/BROKEN" ]; then rm -f "$HOME/api-sha"; else
  sed -n 's/^GIT_SHA=//p' "$HOME/apps/lassard/sha.env" > "$HOME/api-sha"; fi
""",
    "curl": """
[ -s "$HOME/api-sha" ] || exit 7
printf '{"status":"ok","sha":"%s"}' "$(cat "$HOME/api-sha")"
""",
}

ALEMBIC = """#!/usr/bin/env bash
case "$1" in
  current) echo "$(cat "$HOME/db-rev") (head)" ;;
  downgrade) echo "downgrade $2" >> "$HOME/log"; echo "$2" > "$HOME/db-rev" ;;
esac
"""


# update.sh runs on the Linux VPS (real flock, systemctl --user); Git Bash on Windows has no flock.
# CI (ubuntu-latest, make check) still runs this test (#122).
@unittest.skipIf(os.name == "nt", "deploy/vps/update.sh is Linux-only; runs in CI on ubuntu")
class VpsUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        self.app = self.home / "apps" / "lassard"
        self.origin = self.home / "origin"
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        for name, body in STUBS.items():
            (bin_dir / name).write_text("#!/usr/bin/env bash\n" + body)
            (bin_dir / name).chmod(0o755)

        (self.origin / "web").mkdir(parents=True)
        (self.origin / "backend").mkdir()
        (self.origin / "web" / "package-lock.json").write_text("{}\n")
        self.git("init", "-q", "-b", "main", cwd=self.origin)
        self.good = self.commit("v1", headrev="r1")

        (self.app / "deploy").mkdir(parents=True)
        (self.app / "releases").mkdir()
        (self.app / ".env").write_text("DATABASE_URL=postgresql://stub\n")
        shutil.copy(ROOT / "deploy" / "vps" / "update.sh", self.app / "deploy")
        self.git("clone", "-q", str(self.origin), str(self.app / "repo"), cwd=self.home)
        venv = self.app / "repo" / "backend" / ".venv" / "bin"
        venv.mkdir(parents=True)
        (venv / "alembic").write_text(ALEMBIC)
        (venv / "alembic").chmod(0o755)
        (self.home / "db-rev").write_text("r1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, app: str, headrev: str, broken_web=False, broken_api=False) -> str:
        (self.origin / "web" / "app.txt").write_text(app)
        (self.origin / "backend" / "HEADREV").write_text(headrev + "\n")
        for path, on in ((self.origin / "web" / "BROKEN", broken_web), (self.origin / "backend" / "BROKEN", broken_api)):
            path.unlink(missing_ok=True)
            if on:
                path.write_text("x")
        self.git("add", "-A", cwd=self.origin)
        self.git("commit", "-q", "-m", app, cwd=self.origin)
        return self.git("rev-parse", "HEAD", cwd=self.origin)

    def run_update(self, *args) -> subprocess.CompletedProcess:
        env = {**os.environ, "HOME": str(self.home)}
        (self.home / "log").write_text("")
        return subprocess.run(["bash", str(self.app / "deploy" / "update.sh"), *args], env=env, capture_output=True, text=True)

    def live(self) -> tuple[str, str]:
        www = self.app / "www"
        return (www / "version.txt").read_text().strip(), (www / "index.html").read_text()

    def log(self) -> list[str]:
        return (self.home / "log").read_text().splitlines()

    def test_good_commit_goes_live_without_build_manifest(self):
        self.assertEqual(self.run_update().returncode, 0)
        self.assertEqual(self.live(), (self.good, "v1"))
        self.assertFalse((self.app / "www" / ".vite").exists())
        self.assertEqual((self.app / "live-rev").read_text().strip(), self.good)
        # The next tick without a new commit does nothing.
        self.assertEqual(self.run_update().returncode, 0)
        self.assertEqual(self.log(), [])

    def test_failed_build_stays_off_the_site_and_is_not_retried(self):
        self.run_update()
        bad = self.commit("v2", headrev="r1", broken_web=True)
        self.assertEqual(self.run_update().returncode, 1)
        self.assertEqual(self.live(), (self.good, "v1"))
        self.assertEqual((self.app / "failed-rev").read_text().strip(), bad)
        self.assertEqual((self.home / "api-sha").read_text().strip(), self.good)
        # Next tick: the same commit is skipped, the API is not restarted.
        self.assertEqual(self.run_update().returncode, 0)
        self.assertEqual(self.log(), [])
        # A fix in main goes live and clears failed-rev.
        fixed = self.commit("v3", headrev="r1")
        self.assertEqual(self.run_update().returncode, 0)
        self.assertEqual(self.live(), (fixed, "v3"))
        self.assertFalse((self.app / "failed-rev").exists())

    def test_api_failure_rolls_back_release_and_migrations(self):
        self.run_update()
        self.commit("v2", headrev="r2", broken_api=True)
        result = self.run_update()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.live(), (self.good, "v1"))
        self.assertEqual((self.home / "api-sha").read_text().strip(), self.good)
        self.assertEqual((self.home / "db-rev").read_text().strip(), "r1")
        self.assertIn("downgrade r1", self.log())
        # The ready release of the live commit is used again: one web build, for the new commit.
        self.assertEqual([line for line in self.log() if line.startswith("npm run")], ["npm run -s build"])


if __name__ == "__main__":
    unittest.main()
