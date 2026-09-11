"""Regression tests: load definitions only; never run the update entry point."""

import errno
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import textwrap
import time
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "aggiorna").read_text()
MARKER = "#== Cleanup:"
assert SOURCE.count(MARKER) == 1
DEFINITIONS = SOURCE.split(MARKER, 1)[0]
BASH = shutil.which("bash")


class PromptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fedoraup-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("AGGIORNA_DEBUG", "BASH_ENV", "ENV", "SUDO_PID")
            and not key.startswith("BASH_FUNC_")
        }
        self.env.update(
            PATH=f"{self.bin}{os.pathsep}{os.defpath}",
            TMPDIR=str(self.root),
            TEST_ROOT=str(self.root),
            TERM="xterm-256color",
        )
        # Fail closed if any test accidentally reaches a real system command.
        for name in (
            "sudo", "dnf", "flatpak", "fwupdmgr", "rpm", "curl",
            "systemctl", "pkcon", "cromup",
        ):
            self.command(
                name,
                'printf "FORBIDDEN: %s\\n" "$0" >> "$TEST_ROOT/forbidden"\nexit 97',
            )

    def tearDown(self):
        self.assertFalse((self.root / "forbidden").exists(),
                         "A test reached an unmocked system command")

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + textwrap.dedent(body) + "\n")
        path.chmod(0o700)
        return path

    def script(self, body):
        return DEFINITIONS + """
DEBUG_DIR=$TEST_ROOT
NO_AUTOREPAIR=1
PROMPT_TICKS=2
QUIET_TICKS=5
""" + textwrap.dedent(body)

    def bash(self, body, input=""):
        result = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", self.script(body)],
            input=input, capture_output=True, text=True, env=self.env, timeout=8,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def terminal(self, body, answers):
        """Reply through a real PTY only after each prompt becomes visible."""
        pid, master = pty.fork()
        if pid == 0:
            os.execve(BASH, [BASH, "--noprofile", "--norc", "-c",
                            self.script(body)], self.env)
        output = bytearray()
        answered = 0
        search_from = 0
        deadline = time.monotonic() + 8
        try:
            while time.monotonic() < deadline:
                readable, _, _ = select.select([master], [], [], 0.1)
                if not readable:
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output.extend(chunk)
                if answered < len(answers):
                    prompt, reply = answers[answered]
                    pos = output.find(prompt.encode(), search_from)
                    if pos >= 0 and b"\x1b[?25h" in output[pos:]:
                        # No redraw may overwrite the visible question while
                        # the command waits; no answer should be synthesized.
                        readable, _, _ = select.select([master], [], [], 0.25)
                        if readable:
                            extra = os.read(master, 65536)
                            output.extend(extra)
                            self.fail(f"Output changed before answering: {extra!r}")
                        os.write(master, reply.encode())
                        answered += 1
                        search_from = len(output)
            else:
                self.fail(f"Terminal test timed out: {output.decode(errors='replace')}")
            _, status = os.waitpid(pid, 0)
            pid = None
            self.assertEqual(os.waitstatus_to_exitcode(status), 0,
                             output.decode(errors="replace"))
            self.assertEqual(answered, len(answers),
                             output.decode(errors="replace"))
            return output.decode(errors="replace")
        finally:
            if pid is not None:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
            os.close(master)

    def test_recognizes_prompt_formats(self):
        prompts = [
            "Continue? [y/N]", "Perform operation? [Y|n]: ",
            "\x1b[33mContinue? [y/N]\x1b[0m", "Press ENTER to continue",
            "Premi INVIO per continuare", "PRESS RETURN", "Hit any key",
            "Premere il tasto INVIO", "Seleziona un'opzione:",
            "\x1b[2K\rChoose: ", "Choice: ", "Scelta: ", "Password:",
            "\x1b]8;;https://example.invalid\x1b\\Continue?\x1b]8;;\x1b\\",
            "\x1b]0;title\x07Continue?\x1b[0m\r",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.bash(f"is_question {shlex.quote(prompt)}")

    def test_progress_and_blank_lines_are_not_questions(self):
        for text in ("", "   ", "\x1b[0m", "Downloading 15%", "Resolving...",
                     "Running transaction", "[1/2] Updating package 100%"):
            with self.subTest(text=text):
                self.bash(f"! is_question {shlex.quote(text)}")

    def test_normalizes_redraws_and_ignores_blank_lines(self):
        output = self.bash(r"""
            text=$'Downloading 10%\r\e[2KPremi INVIO\e[0m\r'
            clean_prompt_line text
            printf '%s\n' "$text"
            last_line=''
            remember_prompt_line $'\e[33mContinue? [y/N]\e[0m' last_line
            remember_prompt_line '' last_line
            remember_prompt_line $' \e[0m\r' last_line
            printf '%s\n' "$last_line"
            remember_prompt_line 'Downloading 15%' last_line
            printf '%s\n' "$last_line"
        """)
        self.assertEqual(output.splitlines(),
                         ["Premi INVIO", "Continue? [y/N]", "Downloading 15%"])

    def test_partial_prompt_keeps_context_without_duplicate_display(self):
        output = self.bash(r"""
            log=$TEST_ROOT/context.log
            printf 'Warning: keep the device connected\n' > "$log"
            pending='Continue? [y/N] '; stall=0; asking=0; last_line=''
            poll_prompt Test pending stall asking last_line "$log"
            (( asking == 0 )) || exit 1
            poll_prompt Test pending stall asking last_line "$log"
            (( asking == 1 )) || exit 2
            [[ -z $pending ]] || exit 3
            [[ $(wc -l < "$log") == 2 ]] || exit 4
            poll_prompt Test pending stall asking last_line "$log"
        """)
        self.assertIn("Warning: keep the device connected", output)
        self.assertIn("Continue? [y/N]", output)
        self.assertEqual(output.count("the command is asking:"), 1)
        self.assertIn("\a", output)          # una domanda vera si deve sentire

    def test_fallback_shows_unknown_menu_without_assuming_a_question(self):
        output = self.bash(r"""
            log=$TEST_ROOT/menu.log
            printf 'Choose a provider\n  1. Alpha\n  2. Beta\n' > "$log"
            pending=''; stall=0; asking=0; last_line='  2. Beta'
            for ((n=1; n<QUIET_TICKS; n++)); do
                poll_prompt Test pending stall asking last_line "$log"
                (( asking == 0 )) || exit 1
            done
            poll_prompt Test pending stall asking last_line "$log"
            (( asking == 1 ))
        """)
        for text in ("Choose a provider", "1. Alpha", "2. Beta", "otherwise wait"):
            self.assertIn(text, output)
        self.assertNotIn("the command is asking:", output)
        # un comando lento ma sano non deve suonare come un allarme
        self.assertNotIn("\a", output)

    def test_silent_command_fallback_leaves_stdin_untouched(self):
        output = self.bash(r"""
            pending=''; stall=$(( QUIET_TICKS - 1 )); asking=0; last_line=''
            poll_prompt Test pending stall asking last_line /dev/null
            IFS= read -r answer
            [[ $answer == untouched ]]
        """, input="untouched\n")
        self.assertIn("no output available yet", output)

    def test_display_removes_captured_terminal_controls(self):
        output = self.bash(r"""
            ask_begin Test $'\e[2J\e[HWarning\n\e[33mContinue? [y/N]\e[0m\n\n'
        """)
        self.assertIn("Warning", output)
        self.assertIn("Continue? [y/N]", output)
        self.assertNotIn("\x1b[2J", output)
        self.assertNotIn("\x1b[H", output)
        self.assertNotIn("\x1b[33m", output)

    def test_run_step_handles_colored_enter_prompt_and_function_hook(self):
        output = self.terminal(r"""
            mock_hook() {
                printf '\e[33mPremi INVIO per continuare\e[0m\n\n'
                IFS= read -r answer
                printf 'ANSWER=<%s>\n' "$answer"
            }
            run_step Test-step mock_hook
            (( steps_ok == 1 && steps_fail == 0 ))
        """, [("Premi INVIO per continuare", "\n")])
        self.assertIn("the command is asking:", output)
        self.assertIn("ANSWER=<>", (self.root / "Test-step.log").read_text())

    def test_run_step_external_hook_and_menu_fallback(self):
        self.command("mock-hook", """
            printf 'Choose a provider\\n  1. Alpha\\n  2. Beta\\n'
            IFS= read -r answer
            printf 'ANSWER=<%s>\\n' "$answer"
        """)
        output = self.terminal("""
            run_step Test-menu mock-hook
            (( steps_ok == 1 && steps_fail == 0 ))
        """, [("2. Beta", "2\n")])
        self.assertIn("otherwise wait", output)
        self.assertIn("ANSWER=<2>", (self.root / "Test-menu.log").read_text())

    def test_dnf_multiple_partial_prompts_resume_and_preserve_log(self):
        self.command("mock-dnf", r"""
            printf 'Warning: example transaction\n'
            printf '\e[33mFIRST? [y/N]\e[0m '
            IFS= read -r answer
            printf 'ANSWER1=<%s>\n' "$answer"
            printf 'SECOND? [y/N]\n\n'
            IFS= read -r answer
            printf 'ANSWER2=<%s>\nRunning transaction\n' "$answer"
            printf '[1/1] Upgrading example 100%% | done\n'
        """)
        self.terminal("""
            run_dnf Test-dnf Install 0 300 300 1000 mock-dnf
            (( steps_ok == 1 && steps_fail == 0 ))
        """, [("FIRST? [y/N]", "n\n"), ("SECOND? [y/N]", "y\n")])
        log = (self.root / "Test-dnf.log").read_text()
        self.assertEqual(log.count("FIRST?"), 1)
        self.assertEqual(log.count("SECOND?"), 1)
        self.assertIn("ANSWER1=<n>", log)
        self.assertIn("ANSWER2=<y>", log)
        self.assertNotIn("__RC__", log)

    def test_dnf_transaction_after_prompt_is_still_detected(self):
        self.command("mock-dnf", r"""
            printf 'Continue? [y/N] '
            IFS= read -r answer
            printf 'Running transaction\n'
            printf '[1/1] Upgrading example 100%% | done\n'
        """)
        output = self.terminal("""
            run_dnf Test-progress Install 0 300 300 1000 mock-dnf
            (( steps_ok == 1 && steps_fail == 0 ))
        """, [("Continue? [y/N]", "y\n")])
        self.assertIn("Install 1/1:", output)

    def test_flatpak_update_and_remove_prompts(self):
        self.command("flatpak", r"""
            printf '\e[33mPress ENTER to continue\e[0m\n\n'
            IFS= read -r answer
            printf 'ANSWER=<%s>\n100%%\n' "$answer"
        """)
        for mode in ("update", "remove"):
            with self.subTest(mode=mode):
                self.terminal(f"""
                    run_flatpak Test-flatpak {mode} 0 1000 org.example.Mock
                    (( steps_ok == 1 && steps_fail == 0 ))
                """, [("Press ENTER to continue", "\n")])
                self.assertIn("ANSWER=<>",
                              (self.root / "Test-flatpak.log").read_text())

    def test_firmware_prompt_with_carriage_returns(self):
        self.command("sudo", '[[ $1 == -n ]] || exit 96\nshift\nexec "$@"')
        self.command("fwupdmgr", r"""
            printf 'Downloading 50%%\r\e[33mContinue? [y/N]\e[0m\r\n\r\n'
            IFS= read -r answer
            printf 'ANSWER=<%s>\n100%%\n' "$answer"
        """)
        self.terminal("""
            run_fw Test-firmware 0 1000 mock-device
            (( steps_ok == 1 && steps_fail == 0 ))
        """, [("Continue? [y/N]", "n\n")])
        self.assertIn("ANSWER=<n>",
                      (self.root / "Test-firmware.log").read_text())

    def test_failed_sudo_is_reported_without_prompting(self):
        self.command("sudo", """
            [[ $1 == -n ]] || exit 96
            printf 'sudo: a password is required\\n' >&2
            exit 1
        """)
        output = self.bash("""
            run_fw Test-auth 0 1000 mock-device
            (( steps_ok == 0 && steps_fail == 1 ))
        """)
        self.assertIn("sudo: a password is required", output)
        self.assertNotIn("the command is asking:", output)

    def test_failed_commands_remain_failed(self):
        self.command("mock-fail", "printf 'mock failure\\n' >&2\nexit 7")
        self.bash("""
            run_step Test-fail mock-fail
            run_dnf Test-dnf-fail Install 0 300 300 1000 mock-fail
            (( steps_ok == 0 && steps_fail == 2 ))
        """)

    def test_flatpak_delta_retry_is_preserved(self):
        self.command("flatpak", """
            printf '%s\\n' "$*" >> "$TEST_ROOT/flatpak-args"
            if [[ $* != *--no-static-deltas* ]]; then
                printf 'Decompressed delta part exceeds configured limit\\n'
                exit 1
            fi
            printf '100%%\\n'
        """)
        self.bash("""
            run_flatpak Test-delta update 0 1000 org.example.Mock
            (( steps_ok == 1 && steps_fail == 0 ))
        """)
        args = (self.root / "flatpak-args").read_text().splitlines()
        self.assertEqual(len(args), 2)
        self.assertIn("--no-static-deltas", args[1])

    def test_main_dnf_calls_keep_command_argument_positions(self):
        calls = "\n".join(line for line in SOURCE.splitlines()
                          if line.startswith("run_dnf "))
        self.assertEqual(len(calls.splitlines()), 2)
        self.bash("""
            run_dnf() {
                shift 6
                [[ $1 == sudo && $2 == -n ]] || exit 1
                [[ ${!#} == -y ]] || exit 2
            }
        """ + calls)


if __name__ == "__main__":
    unittest.main()
