"""Tests for the factory's deterministic spine, on a throwaway git repo."""

import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "factory" / "bin"
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def load(name):
    loader = importlib.machinery.SourceFileLoader(f"factory_{name}", str(BIN / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(cmd, cwd, **kwargs):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, **IDENTITY}, **kwargs)


def git(cwd, *args):
    res = run(["git", *args], cwd)
    if res.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {res.stderr}")
    return res.stdout


class Sandbox(unittest.TestCase):
    """A repo with an origin, the factory's scripts and one job in a worktree."""

    CHECKS = '#!/usr/bin/env bash\nset -euo pipefail\necho "verificare ăîșțâ"\ntest -f hello.txt\n'

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        origin = self.tmp / "origin.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(origin))
        self.repo = self.tmp / "repo"
        git(self.tmp, "clone", "-q", origin.as_posix(), str(self.repo))
        git(self.repo, "config", "core.autocrlf", "false")
        (self.repo / "factory" / "bin").mkdir(parents=True)
        for script in ("job", "gate", "route", "argon"):
            shutil.copy(BIN / script, self.repo / "factory" / "bin" / script)
        config = json.loads((ROOT / "factory" / "config.json").read_text(encoding="utf-8"))
        config["repo"] = "origin"
        (self.repo / "factory" / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (self.repo / "factory" / "checks.sh").write_text(self.CHECKS, encoding="utf-8", newline="\n")
        (self.repo / ".gitignore").write_text("/factory/jobs/\n/factory/argon.local.json\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "start")
        git(self.repo, "push", "-q", "origin", "HEAD:main")
        self.worktree = self.tmp / "repo-factory" / "001-test"
        git(self.repo, "worktree", "add", "-q", "-b", "factory/001-test", self.worktree.as_posix(), "origin/main")
        self.job_dir = self.repo / "factory" / "jobs" / "001-test"
        (self.job_dir / "round-1").mkdir(parents=True)
        (self.job_dir / "spec.md").write_text("# Test\n", encoding="utf-8")
        self.write_job(round=1)

    def write_job(self, **fields):
        job = {"id": "001-test", "issue": 1, "worktree": self.worktree.as_posix(), "stage": "gate", "round": 1,
               "round_limit": 3, "intake": None, "agents": None, "gate": None, "reviews": {}, "pr": 7,
               "branch": "factory/001-test", "started": "2026-10-30T00:00:00Z", "ended": None, "cost_usd": 0.0}
        job.update(fields)
        (self.job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")

    def commit(self, path, text="x\n"):
        target = self.worktree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        git(self.worktree, "add", path)
        git(self.worktree, "commit", "-q", "-m", f"change {path}")

    def script(self, name, *args):
        return run([sys.executable, str(self.repo / "factory" / "bin" / name), *args], self.repo)

    def checks_md(self):
        return (self.job_dir / "round-1" / "checks.md").read_text(encoding="utf-8")


class GateTest(Sandbox):
    def test_failing_checks_fail_and_keep_romanian_output(self):
        res = self.script("gate", "001-test")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertTrue(self.checks_md().startswith("GATE: FAIL"))
        self.assertIn("ăîșțâ", self.checks_md())

    def test_passing_checks_pass(self):
        self.commit("hello.txt")
        res = self.script("gate", "001-test")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(self.checks_md().startswith("GATE: PASS"))

    def test_changing_a_protected_file_fails(self):
        self.commit("hello.txt")
        self.commit("factory/checks.sh", "exit 0\n")
        self.assertEqual(self.script("gate", "001-test").returncode, 1)
        self.assertIn("M factory/checks.sh", self.checks_md())

    def test_adding_a_workflow_fails(self):
        self.commit("hello.txt")
        self.commit(".github/workflows/pages.yml", "on: push\n")
        self.assertEqual(self.script("gate", "001-test").returncode, 1)
        self.assertIn(".github/workflows/pages.yml (blocked)", self.checks_md())

    def test_adding_a_hosting_config_fails(self):
        self.commit("hello.txt")
        self.commit("wrangler.toml", "name = 'x'\n")
        self.assertEqual(self.script("gate", "001-test").returncode, 1)

    def test_a_new_ordinary_file_passes(self):
        self.commit("hello.txt")
        self.commit("tool/notes.txt")
        self.assertEqual(self.script("gate", "001-test").returncode, 0)


class ArgonTest(Sandbox):
    def fake_tool(self, body):
        tool = self.tmp / "fake_tool.py"
        tool.write_text(body, encoding="utf-8")
        local = {"command": [sys.executable, str(tool)]}
        (self.repo / "factory" / "argon.local.json").write_text(json.dumps(local), encoding="utf-8")

    def argon_md(self):
        return (self.job_dir / "round-1" / "argon.md").read_text(encoding="utf-8")

    def test_without_local_config_it_reports_unavailable(self):
        res = self.script("argon", "001-test")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self.argon_md().startswith("ARGON: UNAVAILABLE"))

    def test_a_reply_with_romanian_and_quotes_survives(self):
        self.commit("hello.txt", 'diacritice ăîșțâ și "ghilimele"\n')
        self.fake_tool('import sys\nfrom pathlib import Path\n'
                       'sys.stdout.reconfigure(encoding="utf-8")\n'
                       'text = Path(sys.argv[sys.argv.index("--fisier") + 1]).read_text(encoding="utf-8")\n'
                       'print("răspuns ăîșțâ" if "ghilimele" in text and "ăîșțâ" in text else "diff pierdut")\n')
        res = self.script("argon", "001-test")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self.argon_md().startswith("ARGON: REPLIED"), self.argon_md())
        self.assertIn("răspuns ăîșțâ", self.argon_md())

    def test_a_failing_tool_reports_unavailable(self):
        self.fake_tool('import sys\nsys.exit(2)\n')
        self.assertEqual(self.script("argon", "001-test").returncode, 0)
        self.assertTrue(self.argon_md().startswith("ARGON: UNAVAILABLE"))


class RouteTest(Sandbox):
    def test_route_records_the_agents_through_job(self):
        (self.job_dir / "intake.md").write_text("DECISION: ACCEPT\nRISK: low\nSURFACES: ui\nRESCOPED: no\n\n## Scope\nx\n",
                                                encoding="utf-8")
        self.write_job(stage="intake", round=0)
        res = self.script("route", "001-test")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        job = json.loads((self.job_dir / "job.json").read_text(encoding="utf-8"))
        self.assertEqual(job["agents"]["builder"], "sonnet")
        self.assertEqual(sorted(job["agents"]["reviewers"]), ["code", "ui", "ux"])

    def test_job_refuses_another_repo(self):
        config_path = self.repo / "factory" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["repo"] = "Ramanul/software-factory"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        res = self.script("job", "summary")
        self.assertEqual(res.returncode, 1)
        self.assertIn("Ramanul/software-factory", res.stderr)


class JobTest(unittest.TestCase):
    def setUp(self):
        self.job = load("job")
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-job-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.job.JOBS = self.tmp / "jobs"
        self.record = {"id": "001-x", "issue": 1, "pr": 7, "stage": "approve", "round": 1, "round_limit": 3,
                       "worktree": str(self.tmp), "branch": "factory/001-x", "intake": None, "reviews": {},
                       "agents": {"builder": "sonnet", "reviewers": {"code": "haiku"}}, "gate": None,
                       "started": "2026-10-30T00:00:00Z", "ended": None, "cost_usd": 0.0}
        self.dir = self.job.JOBS / "001-x"
        self.dir.mkdir(parents=True)

    def test_an_illegal_transition_is_refused(self):
        self.record["stage"] = "intake"
        with self.assertRaises(self.job.Refused):
            self.job.advance(self.record, "build")

    def test_merge_stops_at_needs_human_while_auto_merge_is_off(self):
        self.assertFalse(self.job.CONFIG["auto_merge"])
        calls = []
        self.job.gh = lambda *args: calls.append(args) or ""
        self.job.gh_json = lambda *args: {"isDraft": False}
        self.job.cost_usd = lambda job: 0.0
        self.job.sync = lambda job: job
        (self.dir / "decision.md").write_text("APPROVE\n\n## Why\nbun\n", encoding="utf-8")
        (self.dir / "job.json").write_text(json.dumps(self.record), encoding="utf-8")
        self.job.cmd_merge(self.record)
        self.assertEqual(self.record["stage"], "needs-human")
        self.assertTrue((self.dir / "decision.md").read_text(encoding="utf-8").startswith("ESCALATE"))
        self.assertFalse([c for c in calls if "merge" in c], calls)

    def test_cost_finds_a_windows_path_and_skips_unpriced_models(self):
        folder = self.tmp / "session" / "subagents"
        folder.mkdir(parents=True)
        lines = [
            {"message": {"content": r"Job folder: C:\x\factory\jobs\001-x\. Job: 001-x."}},
            {"type": "assistant", "message": {"id": "a", "model": "claude-sonnet-5-5",
                                              "usage": {"input_tokens": 1000000, "output_tokens": 0}}},
            {"type": "assistant", "message": {"id": "b", "model": "nepretuit", "usage": {"input_tokens": 5}}},
        ]
        (folder / "agent-1.jsonl").write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
        self.job.transcripts_dir = lambda: self.tmp
        self.assertEqual(self.job.cost_usd(self.record), 2.0)

    def test_the_lock_makes_a_second_process_wait(self):
        lock = self.tmp / ".lock"
        held = open(lock, "a")
        self.job.take_lock(held)
        child = ("import importlib.machinery as m, importlib.util as u, sys, time\n"
                 f"l = m.SourceFileLoader('j', {str(BIN / 'job')!r})\n"
                 "s = u.spec_from_loader('j', l); j = u.module_from_spec(s); l.exec_module(j)\n"
                 "t = time.time(); f = open(sys.argv[1], 'a'); j.take_lock(f); print(time.time() - t)\n")
        proc = subprocess.Popen([sys.executable, "-c", child, str(lock)], stdout=subprocess.PIPE, text=True)
        time.sleep(1.5)
        held.close()
        out, _ = proc.communicate(timeout=20)
        self.assertGreater(float(out), 0.5)


class GuardTest(unittest.TestCase):
    ALLOWED = [
        "git status --porcelain",
        "cd C:/x && git push origin factory/001-test",
        "git push -u origin factory/001-test",
        'gh pr create --draft --head factory/001-test --title "x" --body "Closes #1"',
        "gh issue create --label factory --title x --body y",
        "python factory/bin/job queue",
        "bash factory/checks.sh",
    ]
    BLOCKED = [
        "git push",
        "git push origin main",
        "git push origin HEAD:main",
        "git push origin factory/x:main",
        "git push --force origin factory/001-test",
        "git push https://github.com/Ramanul/izz-ro HEAD:main",
        "git -C ../izz-ro status",
        "cd ../publimag && ls",
        "git remote set-url origin https://github.com/x/y",
        "npx wrangler deploy",
        "npx vercel --prod",
        "netlify deploy",
        "firebase deploy",
        "gh repo create x",
        "gh api repos/Ramanul/izz-ro",
        "gh pr merge 7",
        "gh workflow run deploy.yml",
        "gh auth token",
        "scp file host:/var/www",
    ]

    def verdict(self, command):
        event = json.dumps({"tool_input": {"command": command}})
        return subprocess.run([sys.executable, str(BIN / "guard")], input=event, capture_output=True, text=True)

    def test_allowed_commands_pass(self):
        for command in self.ALLOWED:
            with self.subTest(command):
                self.assertEqual(self.verdict(command).returncode, 0)

    def test_blocked_commands_stop(self):
        for command in self.BLOCKED:
            with self.subTest(command):
                res = self.verdict(command)
                self.assertEqual(res.returncode, 2, command)
                self.assertIn("Blocked by factory/bin/guard", res.stderr)

    def test_settings_wire_the_guard(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        hook = settings["hooks"]["PreToolUse"][0]
        self.assertIn("Bash", hook["matcher"])
        self.assertIn("factory/bin/guard", hook["hooks"][0]["command"])


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "factory" / "config.json").read_text(encoding="utf-8"))

    def test_nothing_merges_or_publishes_by_itself(self):
        self.assertIs(self.config["auto_merge"], False)
        self.assertEqual(self.config["repo"], "Ramanul/software-factory")
        self.assertIn(".github/*", self.config["blocked_paths"])

    def test_the_factory_protects_its_own_files(self):
        for path in ("factory/bin/*", ".claude/*", "factory/checks.sh", "factory/config.json"):
            self.assertIn(path, self.config["protected_paths"])

    def test_no_workflow_or_page_config_exists(self):
        self.assertFalse((ROOT / ".github").exists())
        self.assertFalse((ROOT / "CNAME").exists())

    def test_agents_use_only_known_frontmatter(self):
        names = {"intake", "spec-writer", "builder", "reviewer-code", "reviewer-security", "reviewer-ux",
                 "reviewer-ui", "approver"}
        found = {p.stem: p for p in (ROOT / ".claude" / "agents").glob("*.md")}
        self.assertEqual(set(found), names)
        for name, path in found.items():
            front = path.read_text(encoding="utf-8").split("---")[1]
            keys = set(re.findall(r"^(\w+):", front, re.M))
            allowed = {"name", "description", "tools", "model"} | ({"hooks"} if name == "builder" else set())
            self.assertEqual(keys - allowed, set(), name)
            self.assertIn(f"name: {name}", front)

    def test_intake_has_no_shell(self):
        front = (ROOT / ".claude" / "agents" / "intake.md").read_text(encoding="utf-8").split("---")[1]
        self.assertNotIn("Bash", front)

    def test_scripts_are_called_through_python(self):
        skill = (ROOT / ".claude" / "skills" / "factory" / "SKILL.md").read_text(encoding="utf-8")
        calls = re.findall(r"(\S*)\s*factory/bin/(?:job|gate|route|argon) \S", skill)
        self.assertTrue(calls)
        self.assertEqual({c.strip("`") for c in calls}, {"python"})


if __name__ == "__main__":
    unittest.main()
