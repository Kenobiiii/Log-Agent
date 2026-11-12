"""Analysis tools for SSH auth logs (syslog / auth.log format)."""

import ipaddress
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from typing import NamedTuple

INTERNAL_NETWORKS = [ipaddress.ip_network("10.0.0.0/8")]
MAX_ITEMS = 30
ACCOUNT_PROCESSES = {"useradd", "usermod", "userdel", "groupadd", "groupmod", "passwd", "chpasswd", "chage"}

HEADER_RE = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2}) (?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<host>\S+) (?P<process>[\w.-]+)(?:\[(?P<pid>\d+)\])?: (?P<msg>.*)$"
)
FAILED_RE = re.compile(
    r"^Failed password for (?P<invalid>invalid user )?(?P<user>\S+) "
    r"from (?P<ip>[\d.]+) port \d+"
)
ACCEPTED_RE = re.compile(
    r"^Accepted (?P<method>password|publickey) for (?P<user>\S+) "
    r"from (?P<ip>[\d.]+) port \d+"
)
SESSION_CLOSED_RE = re.compile(r"^pam_unix\(sshd:session\): session closed for user (?P<user>\S+)")
SUDO_RE = re.compile(
    r"^\s*(?P<user>\S+) : (?:(?P<error>[^;]+?) ; )?TTY=\S+ ; PWD=(?P<pwd>\S+) ; "
    r"USER=(?P<run_as>\S+) ; COMMAND=(?P<command>.*)$"
)


class ParsedLog(NamedTuple):
    total_lines: int
    events: tuple       # failed / accepted SSH logins
    sessions: tuple     # SSH sessions opened by a successful login
    sudo: tuple         # sudo commands
    accounts: tuple     # user / group / password changes
    last_ts: datetime | None


# --- Parsing -----------------------------------------------------------------

def _parse_timestamp(month: str, day: str, time: str, year: int) -> datetime:
    return datetime.strptime(f"{year} {month} {day} {time}", "%Y %b %d %H:%M:%S")


@lru_cache(maxsize=8)
def _parse_log_cached(path: str, mtime: float, year: int) -> ParsedLog:
    events, sessions, sudo, accounts = [], [], [], []
    open_sessions = {}  # sshd pid -> session
    total_lines = 0
    ts = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            total_lines += 1
            header = HEADER_RE.match(line.rstrip("\n"))
            if not header:
                continue
            ts = _parse_timestamp(header["month"], header["day"], header["time"], year)
            process, pid, msg = header["process"], header["pid"], header["msg"]

            if process == "sshd":
                if m := FAILED_RE.match(msg):
                    events.append({
                        "ts": ts, "kind": "failed", "user": m["user"], "ip": m["ip"],
                        "method": "password", "invalid_user": m["invalid"] is not None,
                    })
                elif m := ACCEPTED_RE.match(msg):
                    events.append({
                        "ts": ts, "kind": "accepted", "user": m["user"], "ip": m["ip"],
                        "method": m["method"], "invalid_user": False,
                    })
                    session = {"user": m["user"], "ip": m["ip"], "start": ts, "end": None}
                    sessions.append(session)
                    open_sessions[pid] = session
                elif m := SESSION_CLOSED_RE.match(msg):
                    session = open_sessions.pop(pid, None)
                    if session and session["user"] == m["user"]:
                        session["end"] = ts

            elif process == "sudo":
                if m := SUDO_RE.match(msg):
                    sudo.append({
                        "ts": ts, "user": m["user"], "run_as": m["run_as"],
                        "command": m["command"], "pwd": m["pwd"], "error": m["error"],
                    })

            elif process in ACCOUNT_PROCESSES:
                accounts.append({"ts": ts, "process": process, "message": msg})

    return ParsedLog(total_lines, tuple(events), tuple(sessions), tuple(sudo), tuple(accounts), ts)


def parse_log(path: str, year: int | None = None) -> ParsedLog:
    """Parse the log file. Results are cached until the file changes."""
    year = year or datetime.now().year
    return _parse_log_cached(os.path.abspath(path), os.path.getmtime(path), year)


def _is_internal(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in net for net in INTERNAL_NETWORKS)


def _validate_ip(ip) -> str | None:
    try:
        ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return f"'{ip}' is not a valid IP address"
    return None


def _session_end(session: dict, log: ParsedLog) -> datetime:
    return session["end"] or log.last_ts


# --- Tools -------------------------------------------------------------------

def log_summary(path: str) -> dict:
    log = parse_log(path)
    events = log.events
    if not events:
        return {"total_lines": log.total_lines, "error": "No SSH events found in log"}

    failed = [e for e in events if e["kind"] == "failed"]
    accepted = [e for e in events if e["kind"] == "accepted"]
    targeted_users = Counter(e["user"] for e in failed)

    return {
        "total_lines": log.total_lines,
        "ssh_events": len(events),
        "failed_attempts": len(failed),
        "successful_logins": len(accepted),
        "unique_ips": len({e["ip"] for e in events}),
        "ips_with_failures": len({e["ip"] for e in failed}),
        "unique_users": len({e["user"] for e in events}),
        "failures_on_nonexistent_users": sum(e["invalid_user"] for e in failed),
        "sudo_commands": len(log.sudo),
        "account_changes": len(log.accounts),
        "first_event": events[0]["ts"].isoformat(),
        "last_event": events[-1]["ts"].isoformat(),
        "most_targeted_users": [
            {"user": u, "failures": n} for u, n in targeted_users.most_common(5)
        ],
    }


def top_failed_ips(path: str, n: int = 5) -> dict:
    try:
        n = max(1, min(int(n), MAX_ITEMS))
    except (TypeError, ValueError):
        return {"error": f"'n' must be an integer, got {n!r}"}

    failures = Counter()
    successes = Counter()
    users = defaultdict(set)
    for e in parse_log(path).events:
        if e["kind"] == "failed":
            failures[e["ip"]] += 1
            users[e["ip"]].add(e["user"])
        else:
            successes[e["ip"]] += 1

    return {
        "ips_with_failures": len(failures),
        "top": [
            {
                "ip": ip,
                "failures": count,
                "distinct_users": len(users[ip]),
                "successful_logins": successes[ip],
                "internal": _is_internal(ip),
            }
            for ip, count in failures.most_common(n)
        ],
    }


def users_by_ip(path: str, ip: str) -> dict:
    if err := _validate_ip(ip):
        return {"error": err}
    ip = ip.strip()

    from_ip = [e for e in parse_log(path).events if e["ip"] == ip]
    if not from_ip:
        return {"error": f"IP {ip} not found in log"}

    stats = defaultdict(lambda: {"failures": 0, "successes": 0, "exists": True})
    for e in from_ip:
        s = stats[e["user"]]
        s["failures" if e["kind"] == "failed" else "successes"] += 1
        if e["invalid_user"]:
            s["exists"] = False

    users = sorted(
        ({"user": u, **s} for u, s in stats.items()),
        key=lambda x: (-x["failures"], x["user"]),
    )
    return {
        "ip": ip,
        "internal": _is_internal(ip),
        "distinct_users": len(users),
        "users": users[:MAX_ITEMS],
        "truncated": len(users) > MAX_ITEMS,
    }


def successful_logins_by_ip(path: str, ip: str) -> dict:
    if err := _validate_ip(ip):
        return {"error": err}
    ip = ip.strip()

    from_ip = [e for e in parse_log(path).events if e["ip"] == ip]
    if not from_ip:
        return {"error": f"IP {ip} not found in log"}

    logins = []
    failures = 0
    for e in from_ip:
        if e["kind"] == "failed":
            failures += 1
        else:
            logins.append({
                "timestamp": e["ts"].isoformat(),
                "user": e["user"],
                "method": e["method"],
                "prior_failures": failures,
            })

    return {
        "ip": ip,
        "internal": _is_internal(ip),
        "total_failures": failures,
        "login_count": len(logins),
        "logins": logins[:MAX_ITEMS],
        "truncated": len(logins) > MAX_ITEMS,
    }


def success_after_failures(path: str, min_failures: int = 3) -> dict:
    try:
        min_failures = max(1, int(min_failures))
    except (TypeError, ValueError):
        return {"error": f"'min_failures' must be an integer, got {min_failures!r}"}

    failures = Counter()
    tried_users = defaultdict(set)
    flagged = {}

    for e in parse_log(path).events:
        ip = e["ip"]
        if ip in flagged:
            continue
        if e["kind"] == "failed":
            failures[ip] += 1
            tried_users[ip].add(e["user"])
        elif failures[ip] >= min_failures:
            flagged[ip] = {
                "ip": ip,
                "internal": _is_internal(ip),
                "failures_before_success": failures[ip],
                "users_tried": len(tried_users[ip]),
                "first_login": e["ts"].isoformat(),
                "user": e["user"],
                "method": e["method"],
            }

    results = sorted(flagged.values(), key=lambda x: -x["failures_before_success"])
    return {
        "min_failures": min_failures,
        "count": len(results),
        "ips": results[:MAX_ITEMS],
        "truncated": len(results) > MAX_ITEMS,
    }


def commands_by_ip(path: str, ip: str) -> dict:
    if err := _validate_ip(ip):
        return {"error": err}
    ip = ip.strip()

    log = parse_log(path)
    if not any(e["ip"] == ip for e in log.events):
        return {"error": f"IP {ip} not found in log"}

    ip_sessions = [s for s in log.sessions if s["ip"] == ip]
    results = []
    for s in ip_sessions:
        start, end = s["start"], _session_end(s, log)

        # Sessions of the same user from other IPs that overlap this one.
        # sudo lines don't include the source IP, so commands in an overlap
        # can't be attributed with certainty.
        overlapping = [
            o for o in log.sessions
            if o is not s and o["user"] == s["user"] and o["ip"] != ip
            and o["start"] <= end and _session_end(o, log) >= start
        ]

        commands = []
        for c in log.sudo:
            if c["user"] != s["user"] or not (start <= c["ts"] <= end):
                continue
            commands.append({
                "timestamp": c["ts"].isoformat(),
                "command": c["command"],
                "run_as": c["run_as"],
                "denied": c["error"] is not None,
                "error": c["error"],
                "ambiguous": any(o["start"] <= c["ts"] <= _session_end(o, log) for o in overlapping),
            })

        account_changes = [
            {"timestamp": a["ts"].isoformat(), "process": a["process"], "message": a["message"]}
            for a in log.accounts if start <= a["ts"] <= end
        ]

        results.append({
            "user": s["user"],
            "login": start.isoformat(),
            "logout": s["end"].isoformat() if s["end"] else None,
            "sudo_commands": commands[:MAX_ITEMS],
            "sudo_truncated": len(commands) > MAX_ITEMS,
            "account_changes_during_session": account_changes[:MAX_ITEMS],
            "overlapping_sessions_from_other_ips": [
                {"ip": o["ip"], "login": o["start"].isoformat()} for o in overlapping
            ],
        })

    return {
        "ip": ip,
        "internal": _is_internal(ip),
        "session_count": len(results),
        "sessions": results[:MAX_ITEMS],
        "truncated": len(results) > MAX_ITEMS,
        "note": (
            "auth.log only records sudo commands and account changes; regular "
            "shell commands are not logged. Commands marked ambiguous happened "
            "while the same user had another session open from a different IP."
        ),
    }


# --- Registry ----------------------------------------------------------------

TOOL_FUNCTIONS = {
    "log_summary": log_summary,
    "top_failed_ips": top_failed_ips,
    "users_by_ip": users_by_ip,
    "successful_logins_by_ip": successful_logins_by_ip,
    "success_after_failures": success_after_failures,
    "commands_by_ip": commands_by_ip,
}

_IP_PARAMS = {
    "type": "object",
    "properties": {
        "ip": {"type": "string", "description": "IPv4 address, e.g. 203.0.113.77"}
    },
    "required": ["ip"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_summary",
            "description": (
                "General overview of the SSH log: line count, failed attempts, "
                "successful logins, unique IPs and users, sudo commands, account "
                "changes, time range and most targeted users. Call this first to "
                "get the big picture."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_failed_ips",
            "description": (
                "Ranking of IPs by number of failed login attempts. For each IP "
                "returns failures, distinct usernames tried, successful logins "
                "and whether it belongs to the internal network."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of IPs to return (1-30). Default 5."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "users_by_ip",
            "description": (
                "Usernames attempted from a given IP, with failures and successes "
                "per user and whether the user exists on the system."
            ),
            "parameters": _IP_PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "successful_logins_by_ip",
            "description": (
                "Successful logins from a given IP (timestamp, user, auth method) "
                "and how many failed attempts preceded each one."
            ),
            "parameters": _IP_PARAMS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "success_after_failures",
            "description": (
                "Find IPs that had several failed attempts and THEN logged in "
                "successfully, a sign of a compromised account. Catches attacks "
                "that don't show up in the top failed IPs due to low volume."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "min_failures": {
                        "type": "integer",
                        "description": "Minimum failures before the success to flag an IP. Default 3.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commands_by_ip",
            "description": (
                "What happened after an IP logged in: for each SSH session from "
                "that IP, the sudo commands run (including denied ones) and any "
                "user/group/password changes during the session. Use it on IPs "
                "that successfully logged in to assess the impact of an intrusion."
            ),
            "parameters": _IP_PARAMS,
        },
    },
]


def run_tool(name: str, arguments: str | dict | None, path: str) -> str:
    """Execute a tool call from the model and return the result as a JSON string.

    `path` is injected here so the model never chooses which file is read.
    Errors are returned as JSON instead of raised, so the agent loop keeps going.
    """
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
        args.pop("path", None)
        result = func(path, **args)
    except json.JSONDecodeError:
        result = {"error": f"Arguments are not valid JSON: {arguments!r}"}
    except TypeError as e:
        result = {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
    return json.dumps(result, ensure_ascii=False)
