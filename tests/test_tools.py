"""Analysis tools: logic on the tiny log, regression figures on the sample log,
and the run_tool dispatcher used by the agent."""

import json

import pytest

import tools
from tools import (
    TOOL_FUNCTIONS,
    external_logins,
    TOOLS,
    commands_by_ip,
    log_summary,
    run_tool,
    success_after_failures,
    successful_logins_by_ip,
    top_failed_ips,
    user_activity,
    users_by_ip,
)


# --- Logic on the tiny log -----------------------------------------------------

def test_log_summary_mini(mini_log):
    s = log_summary(mini_log)
    assert s["failed_attempts"] == 3
    assert s["successful_logins"] == 2
    assert s["failures_on_nonexistent_users"] == 1
    assert s["unique_ips"] == 2
    assert s["unique_users"] == 4
    assert s["sudo_commands"] == 2
    assert s["account_changes"] == 1


def test_success_after_failures_respects_threshold(mini_log):
    flagged = success_after_failures(mini_log, min_failures=3)["ips"]
    assert len(flagged) == 1
    assert flagged[0]["ip"] == "1.2.3.4"
    assert flagged[0]["user"] == "alice"
    assert flagged[0]["failures_before_success"] == 3
    assert flagged[0]["users_tried_before_success"] == 3
    assert success_after_failures(mini_log, min_failures=4)["count"] == 0


def test_users_by_ip_mini(mini_log):
    users = {u["user"]: u for u in users_by_ip(mini_log, "1.2.3.4")["users"]}
    assert users["admin"]["exists"] is False
    assert users["alice"] == {"user": "alice", "failures": 1, "successes": 1, "exists": True}


def test_commands_by_ip_attributes_sudo_to_session(mini_log):
    result = commands_by_ip(mini_log, "1.2.3.4")
    session = result["sessions"][0]
    assert session["user"] == "alice"
    assert [c["denied"] for c in session["sudo_commands"]] == [False, True]
    assert len(session["account_changes_during_session"]) == 1


def test_internal_flag(mini_log):
    assert successful_logins_by_ip(mini_log, "10.0.0.5")["internal"] is True
    assert successful_logins_by_ip(mini_log, "1.2.3.4")["internal"] is False


def test_user_activity_created_account(mini_log):
    evil = user_activity(mini_log, "evil")
    assert evil["exists"] is True
    assert evil["account_created"].endswith("08:07:00")
    assert evil["successful_logins"] == 0


def test_user_activity_nonexistent_user(mini_log):
    assert user_activity(mini_log, "admin")["exists"] is False


def test_top_failed_ips_groups_by_subnet(write_log):
    lines = [
        f"Nov  9 08:00:0{i} srv sshd[{i}]: Failed password for root from {ip} port 1 ssh2"
        for i, ip in enumerate(["1.2.3.4", "1.2.3.4", "1.2.3.5", "5.6.7.8"])
    ]
    path = write_log("\n".join(lines) + "\n")
    result = top_failed_ips(path, n=5)
    assert result["subnets_in_top"] == [{"subnet": "1.2.3.0/24", "ips": 2, "failures": 3}]


# --- Input validation ---------------------------------------------------------

@pytest.mark.parametrize("func", [users_by_ip, successful_logins_by_ip, commands_by_ip])
def test_ip_tools_reject_invalid_ip(mini_log, func):
    assert "not a valid IP" in func(mini_log, "999.1.1.1")["error"]


@pytest.mark.parametrize("func", [users_by_ip, successful_logins_by_ip, commands_by_ip])
def test_ip_tools_point_to_user_activity_for_usernames(mini_log, func):
    assert "use user_activity" in func(mini_log, "alice")["error"]


def test_ip_not_in_log(mini_log):
    assert "not found" in users_by_ip(mini_log, "8.8.8.8")["error"]


def test_user_activity_points_to_ip_tools_for_ips(mini_log):
    assert "use users_by_ip" in user_activity(mini_log, "1.2.3.4")["error"]


def test_user_activity_unknown_user(mini_log):
    assert "not found" in user_activity(mini_log, "nobody")["error"]


def test_top_failed_ips_reports_how_many_it_returns(sample_log, mini_log):
    # The model miscounts long lists (TF-12), so the tool states the count.
    for path, n in ((sample_log, 10), (sample_log, 30), (mini_log, 10)):
        result = top_failed_ips(path, n=n)
        assert result["ips_returned"] == len(result["top"])
    assert top_failed_ips(sample_log, n=10)["ips_returned"] == 10


def test_top_failed_ips_clamps_n(mini_log):
    assert len(top_failed_ips(mini_log, n=1000)["top"]) <= tools.MAX_ITEMS
    assert "error" in top_failed_ips(mini_log, n="many")


# --- Regression figures on the sample log ---------------------------------------
# Ground truth used by the evals. If one of these changes, the evals' expected
# answers are wrong too.

def test_sample_summary(sample_log):
    s = log_summary(sample_log)
    assert (s["total_lines"], s["failed_attempts"], s["successful_logins"]) == (15981, 4147, 502)
    assert s["top_usernames_by_failures"][0] == {"user": "root", "failures": 2155}


def test_sample_top_ips_and_subnet(sample_log):
    top = top_failed_ips(sample_log, n=30)
    assert [(x["ip"], x["failures"]) for x in top["top"][:3]] == [
        ("185.220.101.47", 1850), ("45.142.212.100", 900), ("91.240.118.52", 119),
    ]
    assert top["subnets_in_top"][0] == {"subnet": "194.26.29.0/24", "ips": 25, "failures": 430}


def test_sample_compromised_ips(sample_log):
    flagged = {x["ip"]: x for x in success_after_failures(sample_log)["ips"]}
    assert set(flagged) == {"91.240.118.52", "203.0.113.77", "10.99.0.15", "10.20.8.64"}
    assert flagged["203.0.113.77"]["user"] == "backup"
    assert flagged["203.0.113.77"]["users_tried_before_success"] == 6
    assert flagged["91.240.118.52"]["failures_before_success"] == 83


def test_sample_attacker_commands(sample_log):
    sessions = commands_by_ip(sample_log, "203.0.113.77")["sessions"]
    commands = [c["command"] for s in sessions for c in s["sudo_commands"]]
    assert "/usr/bin/cat /etc/shadow" in commands
    assert any(c.startswith("/usr/bin/wget http://203.0.113.77/") for c in commands)


def test_sample_backdoor_account(sample_log):
    svc = user_activity(sample_log, "svc-update")
    assert svc["account_created"].endswith("-11-11T02:06:08")  # syslog has no year
    assert [x["ip"] for x in svc["login_ips"]] == ["203.0.113.77"]


# --- run_tool dispatcher ---------------------------------------------------------

def test_run_tool_returns_json(mini_log):
    result = json.loads(run_tool("log_summary", "{}", mini_log))
    assert result["failed_attempts"] == 3


@pytest.mark.parametrize("name, arguments, expected", [
    ("does_not_exist", "{}", "Unknown tool"),
    ("users_by_ip", "{not json", "not valid JSON"),
    ("top_failed_ips", '{"count": 3}', "Invalid arguments"),
])
def test_run_tool_returns_errors_as_json(mini_log, name, arguments, expected):
    assert expected in json.loads(run_tool(name, arguments, mini_log))["error"]


def test_run_tool_ignores_path_from_model(mini_log):
    # The model must never choose which file is read.
    result = json.loads(run_tool("log_summary", '{"path": "/etc/passwd"}', mini_log))
    assert result["failed_attempts"] == 3


def test_every_schema_has_a_function():
    names = [t["function"]["name"] for t in TOOLS]
    assert sorted(names) == sorted(TOOL_FUNCTIONS)
    assert not any("path" in t["function"]["parameters"].get("properties", {}) for t in TOOLS)


def test_tools_work_with_ipv6(write_log):
    path = write_log(
        "Dec  1 22:10:00 srv sshd[1]: Failed password for root from 2001:db8::17 port 4242 ssh2\n"
        "Dec  1 22:10:12 srv sshd[1]: message repeated 4 times: [ Failed password for root from 2001:db8::17 port 4242 ssh2]\n"
        "Dec  1 22:11:00 srv sshd[2]: Failed password for root from 2001:db8::18 port 4243 ssh2\n"
        "Dec  1 22:12:00 srv sshd[3]: Failed password for root from 1.2.3.4 port 1 ssh2\n")
    top = top_failed_ips(path, n=5)
    assert top["top"][0] == {"ip": "2001:db8::17", "failures": 5, "distinct_users": 1,
                             "successful_logins": 0, "internal": False}
    assert top["subnets_in_top"] == [{"subnet": "2001:db8::/64", "ips": 2, "failures": 6}]
    assert users_by_ip(path, "2001:db8::17")["users"][0]["failures"] == 5
    assert log_summary(path)["failed_attempts"] == 7


# --- external_logins (dev log 020) ------------------------------------------------

def test_external_logins_mini(mini_log):
    result = external_logins(mini_log)
    # bob logs in from 10.0.0.5 (internal) and is not listed.
    assert result["external_logins"] == 1
    login = result["logins"][0]
    assert (login["ip"], login["user"], login["failures_before_first_login"]) == ("1.2.3.4", "alice", 3)


def test_external_logins_finds_login_without_failures(write_log):
    # A service account that always connects from inside, then from outside with no
    # failed attempt at all: the stolen-key pattern success_after_failures can't see.
    path = write_log(
        "Dec  1 08:00:00 srv sshd[1]: Accepted publickey for ci from 192.168.1.50 port 1 ssh2: ED25519 SHA256:a\n"
        "Dec  1 10:00:00 srv sshd[2]: Accepted publickey for ci from 192.168.1.50 port 2 ssh2: ED25519 SHA256:a\n"
        "Dec  2 03:12:00 srv sshd[3]: Accepted publickey for ci from 198.51.100.77 port 3 ssh2: ED25519 SHA256:a\n"
        "Dec  2 03:40:00 srv sshd[4]: Accepted publickey for ci from 198.51.100.77 port 4 ssh2: ED25519 SHA256:a\n")
    assert success_after_failures(path, min_failures=1)["count"] == 0
    logins = external_logins(path)["logins"]
    assert len(logins) == 1
    login = logins[0]
    # syslog has no year, so compare timestamps without it
    assert (login["first_login"][5:], login["last_login"][5:]) == ("12-02T03:12:00", "12-02T03:40:00")
    assert {k: v for k, v in login.items() if k not in ("first_login", "last_login")} == {
        "ip": "198.51.100.77", "user": "ci", "logins": 2, "methods": ["publickey"],
        "failures_before_first_login": 0, "user_logins_from_internal_ips": 2,
    }


def test_sample_external_logins(sample_log):
    pairs = {(p["ip"], p["user"]) for p in external_logins(sample_log)["logins"]}
    assert pairs == {("91.240.118.52", "mlopez"), ("203.0.113.77", "backup"), ("203.0.113.77", "svc-update")}


def test_user_activity_dates_failures(write_log):
    # Failures on two different days from the same IP must not be merged (H-13, dev log 021).
    path = write_log(
        "Dec  1 10:48:40 srv sshd[1]: Failed password for ann from 172.16.5.16 port 1 ssh2\n"
        "Dec  3 09:03:02 srv sshd[2]: Failed password for ann from 172.16.5.16 port 2 ssh2\n"
        "Dec  3 09:05:04 srv sshd[3]: Failed password for ann from 172.16.5.16 port 3 ssh2\n"
        "Dec  3 09:41:00 srv sshd[4]: Accepted password for ann from 172.16.5.16 port 4 ssh2\n")
    ua = user_activity(path, "ann")
    by_ip = ua["failures_by_ip"][0]
    assert by_ip["failures"] == 3
    assert (by_ip["first_failure"][5:], by_ip["last_failure"][5:]) == ("12-01T10:48:40", "12-03T09:05:04")
    assert [(d["date"][5:], d["failures"]) for d in ua["failures_by_day"]] == [("12-01", 1), ("12-03", 2)]
