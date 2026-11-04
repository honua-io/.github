import os
import subprocess
import tempfile
import unittest
from pathlib import Path

INSTALL = Path(__file__).resolve().parents[1] / "install.sh"
RECORDER = '#!/usr/bin/env bash\necho "$(basename "$0") $PWD $*" >> "$CALLS"\n'


class Installer(unittest.TestCase):
    """install.sh must never run from, or import from, the repository being checked."""

    def test_tools_run_isolated_from_the_checked_repository(self):
        with tempfile.TemporaryDirectory() as scratch:
            fake_bin, checked_repository = Path(scratch, "bin"), Path(scratch, "repo")
            fake_bin.mkdir()
            checked_repository.mkdir()
            (checked_repository / "venv.py").write_text("raise SystemExit('repository code ran')\n")
            for tool in ("npm", "python3"):
                (fake_bin / tool).write_text(RECORDER)
                (fake_bin / tool).chmod(0o755)
            calls = Path(scratch, "calls.txt")
            environment = Path(scratch, "venv")
            (environment / "bin").mkdir(parents=True)
            (environment / "bin" / "python").write_text(RECORDER)
            (environment / "bin" / "python").chmod(0o755)
            env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "CALLS": str(calls)}
            subprocess.run(["bash", str(INSTALL), str(environment)], cwd=checked_repository, env=env, check=True)
            for call in calls.read_text().splitlines():
                tool, working_directory, *arguments = call.split(" ")
                with self.subTest(call):
                    self.assertEqual(working_directory, str(INSTALL.parent))
                    self.assertTrue(tool == "npm" or arguments[0] == "-I", call)


if __name__ == "__main__":
    unittest.main()
