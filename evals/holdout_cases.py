"""Held-out eval cases: a log and questions the agent was never tuned on.

Written before the agent was ever run against samples/holdout_auth.log. Expected
values come from samples/holdout_truth.json, produced by the log generator, not
from tools.py.

Rule: do not tune the agent on these results. Fix what they reveal using the main
suite and unit tests, then re-run this suite only to measure.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDOUT_LOG = ROOT / "samples" / "holdout_auth.log"
TRUTH = json.loads((ROOT / "samples" / "holdout_truth.json").read_text())

T, S, A = TRUTH["totals"], TRUTH["scenarios"], TRUTH["accounts"]
STUFF, STOLEN, FOREIGN = S["credential_stuffing"], S["stolen_key"], S["foreign_login"]
INSIDER, LOCKED, DICT, IPV6 = S["insider_sudo"], S["locked_out"], S["dictionary"], S["ipv6_bruteforce"]

LS, TF, UB = "log_summary", "top_failed_ips", "users_by_ip"
SL, SAF, CMD, UA = "successful_logins_by_ip", "success_after_failures", "commands_by_ip", "user_activity"
EL = "external_logins"  # added after the first run (dev log 020): accepted path only
PA = "privileged_activity"  # added later (dev log 026): accepted path only

NO = ["no ", "no.", "no,", "no!", "no:", "no*", "no—", "no –", "never", "nunca", "none", "ninguna", "ninguno",
      "did not", "didn't", "not "]
DENIED = ["not in sudoers", "denied", "denegad", "rechaz", "failed", "falló", "no tenía permiso", "sin permiso"]
INTERNAL = ["internal", "interna", "company network", "red de la empresa", "corporate"]


def _hhmm(iso_ts: str) -> str:
    return iso_ts[11:16]


# Each case: id, tool (category for the report), prompt, expect (tool groups),
# optimal_calls, and checks: contains / numbers / any_of / excludes.
HOLDOUT_CASES = [
    dict(id="H-01", tool="overview", prompt="Give me a quick overview of this log: period covered, failed vs "
         "successful logins.", expect=[[LS]], optimal_calls=1,
         numbers=[T["failed_attempts"], T["successful_logins"]]),
    dict(id="H-02", tool="attacks", prompt="Which IP made the most failed login attempts, and how many?",
         expect=[[TF]], optimal_calls=1, contains=[IPV6["ip"]], numbers=[IPV6["attempts"]]),
    dict(id="H-03", tool="attacks", prompt="List the top 5 attacking IPs with their failed attempt counts.",
         expect=[[TF]], optimal_calls=1, contains=[ip for ip, _ in TRUTH["top_failed_ips"][:3]],
         numbers=[n for _, n in TRUTH["top_failed_ips"][:3]]),
    dict(id="H-04", tool="compromise", prompt="Was any account compromised in this log? Which accounts, and from "
         "which IPs?", expect=[[SAF, UA, SL, EL]], optimal_calls=3,
         contains=STUFF["compromised"] + [STUFF["ip"], STOLEN["ip"], STOLEN["user"]]),
    dict(id="H-05", tool="compromise", prompt="Did anyone log in from outside the company network? List them.",
         expect=[[SAF, UA, SL, EL]], optimal_calls=3, contains=[e["ip"] for e in TRUTH["external_logins"]]),
    dict(id="H-06", tool="compromise", prompt="Is the jenkins service account behaving normally? It should only "
         "connect from the CI server.", expect=[[UA]], optimal_calls=1,
         contains=[STOLEN["ip"], _hhmm(STOLEN["time"])]),
    dict(id="H-07", tool="impact", prompt=f"What did the session from {STOLEN['ip']} do on the server?",
         expect=[[CMD]], optimal_calls=1, contains=["curl", ".m.sh"]),
    dict(id="H-08", tool="compromise", prompt="Did anyone log in successfully from an unknown external location "
         "without a single failed attempt first? That could be a stolen SSH key.", expect=[[UA, SL, SAF, EL]],
         optimal_calls=3, contains=[STOLEN["ip"], STOLEN["user"]]),
    dict(id="H-09", tool="compromise", prompt=f"{STUFF['ip']} tried many accounts. How many did it try, and "
         "which did it get into?", expect=[[UB], [SL]], optimal_calls=2,
         contains=STUFF["compromised"], numbers=[STUFF["accounts_tried"]]),
    dict(id="H-10", tool="impact", prompt="Did the attacker who got into emma.wilson's account manage to get root?",
         expect=[[UA, SAF, SL], [CMD]], optimal_calls=2, any_of=[DENIED]),
    dict(id="H-11", tool="users", prompt="noah.taylor logged in during the night. From where and at what time? "
         "Is that IP part of our network?", expect=[[UA]], optimal_calls=1,
         contains=[FOREIGN["ip"], _hhmm(FOREIGN["time"])]),
    dict(id="H-12", tool="users", prompt="¿Algún empleado de la red interna ha intentado usar sudo sin tener "
         "permiso? ¿Quién y cuántas veces?", expect=[[UA, CMD, PA]], optimal_calls=3,
         contains=[INSIDER["user"]], numbers=[INSIDER["denied"]]),
    dict(id="H-13", tool="users", prompt="ava.johnson says they couldn't log in on the morning of Dec 3. What "
         "happened?", expect=[[UA]], optimal_calls=1, contains=[LOCKED["ip"]], numbers=[LOCKED["failures"]]),
    dict(id="H-14", tool="attacks", prompt=f"Which usernames were tried from {DICT['ip']}?", expect=[[UB]],
         optimal_calls=1, contains=["admin", "ubuntu", "oracle"]),
    dict(id="H-15", tool="attacks", prompt=f"How many distinct usernames did {DICT['ip']} try, and did any of "
         "them exist on this server?", expect=[[UB]], optimal_calls=1,
         contains=DICT["existing_users_tried"], numbers=[DICT["distinct_users"]]),
    dict(id="H-16", tool="network", prompt=f"Is {A['jenkins']['usual_ip']} an internal machine? What connects "
         "from it?", expect=[[UB, SL]], optimal_calls=1, contains=["jenkins"],
         excludes=["is external", "es externa", "external ip", "ip externa", "outside the company network",
                   "fuera de la red"]),
    dict(id="H-17", tool="attacks", prompt="How many failed login attempts came from IPv6 addresses?",
         expect=[[TF]], optimal_calls=1, numbers=[IPV6["attempts"]]),
    dict(id="H-18", tool="attacks", prompt="Were there failed public-key authentication attempts? From which IPs "
         "and for which users?", expect=[], optimal_calls=2,
         contains=[p["ip"] for p in TRUTH["publickey_failures"][:2]]),
    dict(id="H-19", tool="users", prompt="How often does the nagios account log in, and from where?",
         expect=[[UA]], optimal_calls=1, contains=[A["nagios"]["ip"]], numbers=[A["nagios"]["logins"]]),
    dict(id="H-20", tool="overview", prompt="How many logins used keyboard-interactive authentication?",
         expect=[], optimal_calls=2, numbers=[TRUTH["keyboard_interactive_logins"]]),
    dict(id="H-21", tool="attacks", prompt="Was there a coordinated attack from several IPs of the same subnet?",
         expect=[[TF]], optimal_calls=1, any_of=[NO], excludes=["194.26.29"]),
    dict(id="H-22", tool="overview", prompt="¿Cuántas IPs distintas intentaron entrar en el servidor sin éxito a lo largo de los tres días?",
         expect=[[LS, TF]], optimal_calls=1, numbers=[T["ips_with_failures"]]),
    dict(id="H-23", tool="compromise", prompt="Full incident review: were we compromised, how, and what should "
         "we do first?", expect=[[SAF, EL], [CMD]], optimal_calls=6, contains=[STOLEN["ip"], STUFF["ip"]]),
    dict(id="H-24", tool="impact", prompt="Did the pgbackup account run anything unusual?", expect=[[UA], [CMD]],
         optimal_calls=2, contains=["pg_backup.sh"]),
    dict(id="H-25", tool="compromise", prompt="When was the last successful login from outside the network, and "
         "by whom?", expect=[[UA, SL, SAF, EL]], optimal_calls=3,
         contains=[TRUTH["external_logins"][-1]["user"], TRUTH["external_logins"][-1]["ip"]]),
]
