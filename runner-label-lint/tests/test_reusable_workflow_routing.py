"""Reusable checks must select trusted compute and survive stale shared temp settings."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ("clean-code", "repo-hygiene", "runner-label-lint")


class ReusableWorkflowRoutingTests(unittest.TestCase):
    def test_job_temp_bootstrap_precedes_actions_and_subprocesses(self):
        for name in WORKFLOWS:
            workflow = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())
            for job in workflow["jobs"].values():
                with self.subTest(workflow=name), tempfile.TemporaryDirectory() as directory:
                    environment_file = Path(directory) / "environment"
                    environment = dict(os.environ, RUNNER_TEMP=directory, GITHUB_ENV=str(environment_file),
                                       TMPDIR="/unavailable/prior-job", TEMP="/unavailable/prior-job",
                                       TMP="/unavailable/prior-job")
                    subprocess.run(["bash", "-e", "-c", job["steps"][0]["run"]],
                                   env=environment, check=True)
                    settings = dict(line.split("=", 1) for line in environment_file.read_text().splitlines())
                    environment.update(settings)
                    result = subprocess.check_output(["python3", "-c", "import tempfile; print(tempfile.gettempdir())"],
                                                     env=environment, text=True)
                    self.assertEqual(result.strip(), directory)
                    self.assertEqual(set(settings), {"TMPDIR", "TEMP", "TMP"})
                    self.assertIn("vars.HONUA_LIGHT_RUNNER", job["runs-on"])
                    self.assertIn("|| 'ubuntu-latest'", job["runs-on"])


if __name__ == "__main__":
    unittest.main()
