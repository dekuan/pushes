import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pushes


class TerminalFormatting(unittest.TestCase):
    def test_columns_keep_padding_and_strip_terminal_controls(self):
        self.assertEqual(pushes.clip("Repo", 8), "Repo    ")
        self.assertEqual(pushes.clip("Repo     Branch", 15), "Repo     Branch")
        self.assertEqual(pushes.clip("仓库abc", 5), "仓库a")
        self.assertNotIn("\x1b", pushes.clean("bad\x1b[2J\nname"))


class FetchPolicy(unittest.TestCase):
    def test_automatic_fetch_requires_unpushed_commits_and_elapsed_interval(self):
        repo = pushes.Repo(Path("unused"))
        for count in (None, 0):
            repo.ahead = count
            repo.dirty = True
            self.assertFalse(pushes.should_fetch(repo, 30, 100, 0))
        repo.ahead = 1
        self.assertTrue(pushes.should_fetch(repo, 30, 100, 100))
        self.assertFalse(pushes.should_fetch(repo, 30, 99, 100))
        self.assertFalse(pushes.should_fetch(repo, 0, 100, 0))

    def test_manual_fetch_bypasses_count_interval_and_disable_setting(self):
        repo = pushes.Repo(Path("unused"))
        for count in (None, 0, 1):
            repo.ahead = count
            self.assertTrue(pushes.should_fetch(repo, 0, 1, 100, manual=True))


class GitIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        env_patch = patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.remote = self.root / "server.git"
        self.repo = self.root / "project"
        self.run_git(self.root, "init", "--bare", str(self.remote))
        self.run_git(self.root, "init", "-b", "main", str(self.repo))
        self.run_git(self.repo, "config", "user.name", "Test")
        self.run_git(self.repo, "config", "user.email", "test@example.invalid")
        self.run_git(self.repo, "remote", "add", "origin", str(self.remote))
        self.commit(self.repo, "one")
        self.run_git(self.repo, "push", "-u", "origin", "main")

    def run_git(self, path, *args):
        # Isolate all tests from user global configuration and hooks.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        result = subprocess.run(["git", "-C", str(path), *args], env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def commit(self, path, content):
        (path / "file.txt").write_text(content)
        self.run_git(path, "add", ".")
        self.run_git(path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", content)

    def test_counts_dirty_push_and_no_upstream(self):
        repo = pushes.inspect(self.repo)
        self.assertEqual((repo.status, repo.ahead, repo.icon), ("SYNCED", 0, "✓"))
        self.commit(self.repo, "two")
        repo = pushes.inspect(self.repo)
        self.assertEqual((repo.status, repo.ahead, repo.icon), ("READY", 1, "🟡"))
        (self.repo / "untracked").write_text("dirty")
        repo = pushes.inspect(self.repo)
        self.assertEqual((repo.status, repo.ahead, repo.icon), ("DIRTY", 1, "🧨"))
        pushes.operate(self.repo, "push", "main")
        self.assertEqual(pushes.inspect(self.repo).ahead, 0)
        self.run_git(self.repo, "branch", "--unset-upstream")
        self.assertIsNone(pushes.inspect(self.repo).ahead)

    def test_fetch_behind_diverged_and_error(self):
        peer = self.root / "peer"
        self.run_git(self.root, "clone", "-b", "main", str(self.remote), str(peer))
        self.commit(peer, "remote edit")
        self.run_git(peer, "push")
        self.assertEqual(pushes.inspect(self.repo).status, "SYNCED")
        repo, _ = pushes.update(pushes.inspect(self.repo), fetch=True)
        self.assertEqual((repo.status, repo.behind), ("BEHIND", 1))
        self.assertNotEqual(repo.fetched, "Never")
        self.commit(self.repo, "local edit")
        self.assertEqual(pushes.inspect(self.repo).status, "DIVERGED")
        self.run_git(self.repo, "remote", "set-url", "origin", str(self.root / "missing"))
        repo, _ = pushes.update(repo, fetch=True)
        self.assertTrue(repo.network_error)
        self.assertEqual(repo.status, "DIVERGED")

    def test_branch_switch_guards_and_remote_branch(self):
        self.run_git(self.repo, "branch", "feature")
        (self.repo / "dirty").touch()
        with self.assertRaises(pushes.GitError):
            pushes.operate(self.repo, "switch", "main", ("feature", False))
        (self.repo / "dirty").unlink()
        pushes.operate(self.repo, "switch", "main", ("feature", False))
        with self.assertRaises(pushes.GitError):
            pushes.operate(self.repo, "push", "main")
        self.run_git(self.repo, "push", "origin", "feature:remote-feature")
        repo = pushes.inspect(self.repo)
        self.assertIn(("origin/remote-feature", True), repo.branches)
        pushes.operate(self.repo, "switch", "feature", ("origin/remote-feature", True))
        self.assertEqual(pushes.inspect(self.repo).branch, "remote-feature")

    def test_discovery_one_level_worktree_and_subdirectory(self):
        (self.root / "nested").mkdir()
        deep = self.root / "nested" / "deep"
        self.run_git(self.root, "init", str(deep))
        worktree = self.root / "linked"
        self.run_git(self.repo, "worktree", "add", "-b", "linked", str(worktree))
        self.assertEqual(set(pushes.discover(self.root)), {self.repo, worktree})
        sub = self.repo / "sub"
        sub.mkdir()
        self.assertEqual(pushes.discover(sub), [self.repo])

    def test_empty_and_detached(self):
        empty = self.root / "empty"
        self.run_git(self.root, "init", str(empty))
        self.assertEqual(pushes.inspect(empty).status, "EMPTY")
        self.run_git(self.repo, "checkout", "--detach")
        self.assertEqual(pushes.inspect(self.repo).status, "DETACHED")

    def test_commit_stages_all_changes_respecting_gitignore(self):
        (self.repo / "deleted").write_text("delete me")
        self.commit(self.repo, "before deletion")
        (self.repo / "deleted").unlink()
        (self.repo / "file.txt").write_text("staged")
        self.run_git(self.repo, "add", "file.txt")
        (self.repo / "file.txt").write_text("unstaged")
        (self.repo / "untracked").write_text("include me")
        (self.repo / ".gitignore").write_text("ignored\n")
        (self.repo / "ignored").write_text("leave alone")
        phases = []
        result, message = pushes.update(pushes.inspect(self.repo),
            action=("commit", "main", "修复: quote ' and $literal"), progress=phases.append)
        self.assertIn("COMMITTING", phases)
        self.assertTrue(message)
        self.assertEqual(result.ahead, 2)
        self.assertFalse(result.dirty)
        self.assertEqual(self.run_git(self.repo, "show", "HEAD:file.txt"), "unstaged")
        self.assertEqual(self.run_git(self.repo, "log", "-1", "--format=%s"), "修复: quote ' and $literal")
        self.assertEqual(self.run_git(self.repo, "ls-tree", "--name-only", "HEAD").splitlines(),
                         [".gitignore", "file.txt", "untracked"])

    def test_commit_rejects_empty_message_no_changes_and_changed_branch(self):
        before = self.run_git(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(pushes.GitError):
            pushes.operate(self.repo, "commit", "main", "no changes")
        (self.repo / "file.txt").write_text("not staged")
        with self.assertRaises(pushes.GitError):
            pushes.operate(self.repo, "commit", "main", "   ")
        self.assertEqual(self.run_git(self.repo, "diff", "--cached", "--name-only"), "")
        self.run_git(self.repo, "switch", "-c", "other")
        with self.assertRaises(pushes.GitError):
            pushes.operate(self.repo, "commit", "main", "wrong branch")
        self.assertEqual(self.run_git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(self.run_git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_commit_respects_failing_hook(self):
        (self.repo / "file.txt").write_text("staged")
        self.run_git(self.repo, "add", "file.txt")
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'hook rejected commit' >&2\nexit 1\n")
        hook.chmod(0o755)
        result, message = pushes.update(pushes.inspect(self.repo), action=("commit", "main", "blocked"))
        self.assertEqual(result.status, "ERROR")
        self.assertIn("hook rejected commit", message)
        self.assertEqual(self.run_git(self.repo, "rev-list", "--count", "HEAD"), "1")


if __name__ == "__main__":
    unittest.main()
