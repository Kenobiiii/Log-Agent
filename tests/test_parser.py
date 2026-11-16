"""Parser rules, checked on a tiny hand-written log."""

import os

from tools import parse_log


def test_counts_each_failed_attempt_once(mini_log):
    # 'Invalid user', 'pam_unix ... failure' and 'Connection closed' are echoes
    # of the same attempt; only 'Failed password' lines count.
    failed = [e for e in parse_log(mini_log).events if e["kind"] == "failed"]
    assert len(failed) == 3
    assert [e["user"] for e in failed] == ["admin", "root", "alice"]


def test_marks_invalid_users(mini_log):
    failed = {e["user"]: e for e in parse_log(mini_log).events if e["kind"] == "failed"}
    assert failed["admin"]["invalid_user"] is True
    assert failed["root"]["invalid_user"] is False


def test_parses_accepted_logins_and_method(mini_log):
    accepted = [e for e in parse_log(mini_log).events if e["kind"] == "accepted"]
    assert [(e["user"], e["ip"], e["method"]) for e in accepted] == [
        ("alice", "1.2.3.4", "password"),
        ("bob", "10.0.0.5", "publickey"),
    ]


def test_parses_double_space_day_and_injects_year(mini_log):
    ts = parse_log(mini_log, year=2026).events[0]["ts"]
    assert (ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second) == (2026, 11, 9, 8, 0, 3)


def test_counts_all_lines(mini_log):
    assert parse_log(mini_log).total_lines == 15


def test_sessions_open_and_close_by_sshd_pid(mini_log):
    sessions = {s["user"]: s for s in parse_log(mini_log).sessions}
    assert sessions["alice"]["end"].hour == 8 and sessions["alice"]["end"].minute == 10
    assert sessions["bob"]["end"] is None  # never closed


def test_parses_sudo_commands_and_denials(mini_log):
    sudo = parse_log(mini_log).sudo
    assert [s["command"] for s in sudo] == ["/usr/bin/cat /etc/shadow", "/bin/bash"]
    assert sudo[0]["error"] is None
    assert sudo[1]["error"] == "user NOT in sudoers"
    assert all(s["user"] == "alice" and s["run_as"] == "root" for s in sudo)


def test_parses_account_changes(mini_log):
    accounts = parse_log(mini_log).accounts
    assert len(accounts) == 1
    assert accounts[0]["process"] == "useradd"
    assert "name=evil" in accounts[0]["message"]


def test_ignores_non_ssh_processes(mini_log):
    # The CRON line must not create events, sessions or sudo entries.
    log = parse_log(mini_log)
    assert not any(e["user"] == "root" and e["kind"] == "accepted" for e in log.events)


def test_ignores_malformed_lines(write_log):
    path = write_log("garbage line\n\nNov  9 08:00:00 srv sshd[1]: Failed password for root from 1.1.1.1 port 1 ssh2\n")
    log = parse_log(path)
    assert log.total_lines == 3
    assert len(log.events) == 1


def test_cache_is_invalidated_when_file_changes(write_log):
    line = "Nov  9 08:00:00 srv sshd[1]: Failed password for root from 1.1.1.1 port 1 ssh2\n"
    path = write_log(line)
    assert len(parse_log(path).events) == 1

    with open(path, "a") as f:
        f.write(line)
    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))  # make sure mtime changes

    assert len(parse_log(path).events) == 2
