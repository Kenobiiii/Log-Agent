"""Generate the second held-out SSH log and its ground truth.

A third company (a hosting provider's bastion host), different from samples/auth.log
and samples/holdout_auth.log. The first held-out set guided several fixes
(dev log 018-027), so this one measures generalization again. As before, the ground
truth is computed here from what is written into the log, independently of tools.py.

    python samples/generate_holdout2.py

writes samples/holdout2_auth.log and samples/holdout2_truth.json.
"""

import ipaddress
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

random.seed(31337)

OUT_DIR = Path(__file__).resolve().parent
HOST = "bastion-01"
START = datetime(2026, 12, 14)
DAYS = 3
# Office LAN, Tailscale-style VPN (CGNAT range, not RFC 1918) and the admins' IPv6 jump host.
INTERNAL_NETWORKS = ["10.50.0.0/16", "100.64.0.0/10", "fd12:3456::/64"]

lines, attempts, sudo_log, su_log, account_changes = [], [], [], [], []
_seq, _pid, _uids = [0], [7000], {"root": 0}


def pid():
    _pid[0] += random.randint(1, 30)
    return _pid[0]


def port():
    return random.randint(32768, 65535)


def uid(user):
    return _uids.setdefault(user, 1100 + len(_uids))


def add(ts, proc, msg):
    _seq[0] += 1
    lines.append((ts, _seq[0], f"{proc}: {msg}"))


def at(day, hour, minute=0, second=0):
    return START + timedelta(days=day, hours=hour, minutes=minute, seconds=second)


def fail(ts, user, ip, invalid=False):
    p, pt = pid(), port()
    if invalid:
        add(ts, f"sshd[{p}]", f"Invalid user {user} from {ip} port {pt}")
        add(ts + timedelta(seconds=2), f"sshd[{p}]", f"Failed password for invalid user {user} from {ip} port {pt} ssh2")
    else:
        add(ts + timedelta(seconds=1), f"sshd[{p}]",
            f"pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost={ip}  user={user}")
        add(ts + timedelta(seconds=2), f"sshd[{p}]", f"Failed password for {user} from {ip} port {pt} ssh2")
    if random.random() < 0.3:
        add(ts + timedelta(seconds=3), f"sshd[{p}]", f"Connection closed by {'invalid' if invalid else 'authenticating'} "
                                                     f"user {user} {ip} port {pt} [preauth]")
    attempts.append({"ts": ts + timedelta(seconds=2), "ip": ip, "user": user, "result": "failed", "method": "password"})


METHOD_TEXT = {"password": "password", "publickey": "publickey", "keyboard-interactive": "keyboard-interactive/pam"}


def session(ts, user, ip, method, minutes, sudo=(), accounts=()):
    p, pt = pid(), port()
    suffix = ": ED25519 SHA256:" + "".join(random.choices("abcdef0123456789", k=43)) if method == "publickey" else ""
    add(ts, f"sshd[{p}]", f"Accepted {METHOD_TEXT[method]} for {user} from {ip} port {pt} ssh2{suffix}")
    add(ts, f"sshd[{p}]", f"pam_unix(sshd:session): session opened for user {user}(uid={uid(user)}) by (uid=0)")
    attempts.append({"ts": ts, "ip": ip, "user": user, "result": "accepted", "method": method})
    events = [("sudo", c) for c in sudo] + [("account", a) for a in accounts]
    for i, (kind, item) in enumerate(events):
        t = ts + timedelta(seconds=int((i + 1) * minutes * 60 / (len(events) + 1)))
        if kind == "sudo":
            add(t, "sudo", f"   {user} : TTY=pts/{random.randint(0, 5)} ; PWD=/home/{user} ; USER=root ; COMMAND={item}")
            sudo_log.append({"ts": t, "user": user, "command": item})
        else:
            proc, msg = item
            add(t, f"{proc}[{pid()}]", msg)
            account_changes.append({"ts": t, "process": proc, "message": msg, "by": user, "ip": ip})
    end = ts + timedelta(minutes=minutes, seconds=random.randint(0, 59))
    add(end, f"sshd[{p}]", f"Received disconnect from {ip} port {pt}:11: disconnected by user")
    add(end, f"sshd[{p}]", f"pam_unix(sshd:session): session closed for user {user}")
    return end


def su(ts, user, ok, tty="pts/1"):
    if ok:
        add(ts, "su", f"(to root) {user} on {tty}")
        add(ts, "su", f"pam_unix(su:session): session opened for user root by {user}(uid={uid(user)})")
        add(ts + timedelta(minutes=random.randint(2, 20)), "su", "pam_unix(su:session): session closed for user root")
    else:
        add(ts, "su", f"pam_unix(su:auth): authentication failure; logname={user} uid={uid(user)} euid=0 "
                      f"tty=/dev/{tty} ruser={user} rhost=  user=root")
        add(ts + timedelta(seconds=2), "su", f"FAILED SU (to root) {user} on {tty}")
    su_log.append({"ts": ts, "user": user, "ok": ok})


# --- The company -------------------------------------------------------------

FIRST = "abcdefghijklmnoprstvwz"
LAST = ["sato", "dubois", "morel", "meyer", "nguyen", "kowalski", "fernandes", "osei", "olsen", "bianchi",
        "novak", "jensen", "rossi", "kim", "silva", "horvat", "berg", "costa", "weber", "lindqvist"]
SCENARIO = ["ksato", "ldubois", "tmorel", "hmeyer"]
employees = list(SCENARIO)
while len(employees) < 60:
    name = random.choice(FIRST) + random.choice(LAST)
    if name not in employees:
        employees.append(name)
office = {u: f"10.50.{random.randint(2, 9)}.{random.randint(10, 240)}" for u in employees}
office["tmorel"] = "10.50.7.33"
vpn = {u: f"100.64.{random.randint(1, 20)}.{random.randint(2, 250)}" for u in employees}
vpn["ldubois"] = "100.64.12.5"
SERVICES = {"backup-svc": "10.50.1.20", "deploy-bot": "10.50.1.30", "zabbix": "10.50.1.40"}
JUMP_HOST = "fd12:3456::10"
EXISTING = set(employees) | set(SERVICES) | {"root"}

# --- Normal activity -------------------------------------------------------------

for day in range(DAYS):
    for user in employees:
        if user == "ldubois" and day == 1 or random.random() > 0.7:
            continue
        ts = at(day, random.choice([8, 9, 9, 10, 13, 14, 16]), random.randint(0, 59), random.randint(0, 59))
        remote = random.random() < 0.35
        ip = vpn[user] if remote else office[user]
        method = "keyboard-interactive" if remote else random.choice(["password", "publickey", "publickey"])
        if random.random() < 0.06:
            fail(ts - timedelta(seconds=20), user, ip)
        session(ts, user, ip, method, random.randint(10, 240))
    session(at(day, 8, 15), "root", JUMP_HOST, "publickey", random.randint(5, 25))
    session(at(day, 2, 0, 5), "backup-svc", SERVICES["backup-svc"], "publickey", 35, sudo=["/usr/local/bin/backup-run"])
    for hour in range(9, 22, 3):
        session(at(day, hour, 10), "deploy-bot", SERVICES["deploy-bot"], "publickey", 2,
                sudo=["/usr/bin/systemctl reload nginx"])
    for quarter in range(96):
        session(at(day, 0, 15 * quarter, 3), "zabbix", SERVICES["zabbix"], "publickey", 0)
    for ten in range(144):
        p = pid()
        add(at(day, 0, 10 * ten, 1), f"CRON[{p}]", "pam_unix(cron:session): session opened for user root(uid=0) by (uid=0)")
        add(at(day, 0, 10 * ten, 2), f"CRON[{p}]", "pam_unix(cron:session): session closed for user root")

# ksato is the on-call admin and becomes root with su.
KSATO_SU = [at(0, 10, 2, 11), at(0, 16, 40, 3), at(1, 9, 15, 40), at(2, 11, 20, 9)]
for ts in KSATO_SU:
    su(ts, "ksato", ok=True)

# Internet scanners.
for _ in range(80):
    ip = f"{random.choice([23, 37, 58, 91, 104, 141, 167, 178, 202, 213])}.{random.randint(1, 254)}." \
         f"{random.randint(0, 254)}.{random.randint(1, 254)}"
    ts = START + timedelta(seconds=random.randint(0, DAYS * 86400 - 3600))
    for k in range(random.randint(1, 5)):
        user = random.choice(["root", "admin", "test", "ubuntu", "user", "git"])
        fail(ts + timedelta(seconds=15 * k), user, ip, invalid=user not in EXISTING)

# --- Scenarios ---------------------------------------------------------------------

# S1 root brute force from outside, then success; root needs no sudo, so only the
# account changes it makes are visible.
ROOT_ATTACKER = "198.51.100.200"
ts = at(1, 2, 5)
for i in range(120):
    fail(ts, "admin" if i % 12 == 0 else "root", ROOT_ATTACKER, invalid=(i % 12 == 0))
    ts += timedelta(seconds=random.randint(30, 80))
ROOT_LOGIN = at(1, 4, 22, 17)
BACKDOOR = "support2"
root_end = session(ROOT_LOGIN, "root", ROOT_ATTACKER, "password", 31, accounts=[
    ("useradd", f"new user: name={BACKDOOR}, UID=1050, GID=1050, home=/home/{BACKDOOR}, shell=/bin/bash, from=/dev/pts/0"),
    ("usermod", f"add '{BACKDOOR}' to group 'sudo'"),
    ("passwd", f"pam_unix(passwd:chauthtok): password changed for {BACKDOOR}"),
])

# S2 distributed brute force: 30 IPs from 30 different /24s, a handful of attempts each.
DIST_IPS = []
while len(DIST_IPS) < 30:
    ip = f"185.{random.randint(100, 250)}.{random.randint(0, 254)}.{random.randint(1, 254)}"
    if ip.rsplit(".", 1)[0] not in {d.rsplit(".", 1)[0] for d in DIST_IPS}:
        DIST_IPS.append(ip)
DIST_USERS = ["admin", "ubuntu", "oracle", "postgres", "test"]
for ip in DIST_IPS:
    ts = START + timedelta(seconds=random.randint(0, DAYS * 86400 - 7200))
    for _ in range(random.randint(8, 15)):
        user = random.choice(DIST_USERS)
        fail(ts, user, ip, invalid=user not in EXISTING)
        ts += timedelta(minutes=random.randint(3, 9))

# S3 the backup service account used with a password from an employee's workstation.
MISUSE_TIME = at(2, 13, 40, 12)
session(MISUSE_TIME, "backup-svc", office["tmorel"], "password", 18,
        sudo=["/usr/bin/tar czf /tmp/db.tgz /var/lib/postgresql"])

# S4 two simultaneous sessions for ldubois: VPN all day and an external login meanwhile.
session(at(1, 9, 5), "ldubois", vpn["ldubois"], "keyboard-interactive", 8 * 60)
TRAVEL_IP, TRAVEL_TIME = "192.0.2.150", at(1, 11, 31, 44)
session(TRAVEL_TIME, "ldubois", TRAVEL_IP, "password", 25)

# S5 an employee repeatedly failing to become root with su.
HMEYER_FAILS = [at(2, 21, 14, 3), at(2, 21, 15, 30), at(2, 21, 17, 12)]
session(at(2, 21, 5), "hmeyer", office["hmeyer"], "password", 30)
for ts in HMEYER_FAILS:
    su(ts, "hmeyer", ok=False, tty="pts/2")

# --- Write the log -----------------------------------------------------------------

lines.sort()
with open(OUT_DIR / "holdout2_auth.log", "w") as f:
    for ts, _, text in lines:
        f.write(f"{ts.strftime('%b')} {ts.day:>2} {ts.strftime('%H:%M:%S')} {HOST} {text}\n")


# --- Ground truth ------------------------------------------------------------------

def internal(ip):
    return any(ipaddress.ip_address(ip) in ipaddress.ip_network(n) for n in INTERNAL_NETWORKS)


iso = datetime.isoformat
failed = [a for a in attempts if a["result"] == "failed"]
accepted = [a for a in attempts if a["result"] == "accepted"]
failures_by_ip = Counter(a["ip"] for a in failed)
logins_by_user = Counter(a["user"] for a in accepted)
root_logins = sorted({(a["ip"], internal(a["ip"])) for a in accepted if a["user"] == "root"})

truth = {
    "log": "samples/holdout2_auth.log",
    "internal_networks": INTERNAL_NETWORKS,
    "totals": {
        "lines": len(lines),
        "failed_attempts": len(failed),
        "successful_logins": len(accepted),
        "ips_with_failures": len(failures_by_ip),
        "keyboard_interactive_logins": sum(a["method"] == "keyboard-interactive" for a in accepted),
        "root_failures": sum(a["user"] == "root" for a in failed),
    },
    "top_failed_ips": [[ip, n] for ip, n in failures_by_ip.most_common(10)],
    "most_frequent_login_user": logins_by_user.most_common(1)[0],
    "root_logins": [{"ip": ip, "internal": i} for ip, i in root_logins],
    "accounts_created": [BACKDOOR],
    "scenarios": {
        "root_compromise": {"ip": ROOT_ATTACKER, "login": iso(ROOT_LOGIN), "logout": iso(root_end),
                            "failures_before": failures_by_ip[ROOT_ATTACKER],
                            "users_tried": sorted({a["user"] for a in failed if a["ip"] == ROOT_ATTACKER}),
                            "backdoor_user": BACKDOOR, "sudo_commands": 0},
        "distributed": {"ips": len(DIST_IPS), "distinct_24s": len({ip.rsplit('.', 1)[0] for ip in DIST_IPS}),
                        "attempts": sum(failures_by_ip[ip] for ip in DIST_IPS), "users": DIST_USERS,
                        "max_attempts_per_ip": max(failures_by_ip[ip] for ip in DIST_IPS)},
        "service_misuse": {"user": "backup-svc", "usual_ip": SERVICES["backup-svc"], "usual_method": "publickey",
                           "ip": office["tmorel"], "workstation_owner": "tmorel", "method": "password",
                           "time": iso(MISUSE_TIME), "command": "/usr/bin/tar czf /tmp/db.tgz /var/lib/postgresql"},
        "simultaneous_sessions": {"user": "ldubois", "vpn_ip": vpn["ldubois"], "external_ip": TRAVEL_IP,
                                  "external_login": iso(TRAVEL_TIME), "prior_failures": 0},
        "su_failures": {"user": "hmeyer", "count": len(HMEYER_FAILS), "first": iso(HMEYER_FAILS[0])},
        "su_success": {"user": "ksato", "count": len(KSATO_SU)},
    },
    "services": {name: {"ip": ip, "logins": logins_by_user[name]} for name, ip in SERVICES.items()},
}

(OUT_DIR / "holdout2_truth.json").write_text(json.dumps(truth, indent=2) + "\n")
print(f"{len(lines)} lines -> {OUT_DIR / 'holdout2_auth.log'}")
print(json.dumps(truth["totals"], indent=2))
