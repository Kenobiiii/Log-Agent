"""Second held-out eval set (dev log 028): a third company's log and new questions.

The first held-out set guided fixes 018-027, so it no longer measures generalization
honestly. These cases were written before the agent was ever run against
samples/holdout2_auth.log. Expected values come from samples/holdout2_truth.json,
produced by the log generator, not from tools.py.

Same rule as before: don't tune the agent on these results.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDOUT2_LOG = ROOT / "samples" / "holdout2_auth.log"
TRUTH = json.loads((ROOT / "samples" / "holdout2_truth.json").read_text())

T, S = TRUTH["totals"], TRUTH["scenarios"]
ROOTC, DIST, MISUSE = S["root_compromise"], S["distributed"], S["service_misuse"]
SIMUL, SUFAIL, SUOK = S["simultaneous_sessions"], S["su_failures"], S["su_success"]

LS, TF, UB = "log_summary", "top_failed_ips", "users_by_ip"
SL, SAF, CMD, UA = "successful_logins_by_ip", "success_after_failures", "commands_by_ip", "user_activity"
EL, PA = "external_logins", "privileged_activity"

NO = ["no ", "no.", "no,", "no!", "no:", "no*", "no—", "no –", "never", "nunca", "none", "ninguna", "ninguno",
      "did not", "didn't", "not "]


def _hhmm(iso_ts: str) -> str:
    return iso_ts[11:16]


HOLDOUT2_CASES = [
    dict(id="B-01", tool="overview", prompt="Give me an overview of this server's SSH activity: failed and successful "
         "logins over the period.", expect=[[LS]], optimal_calls=1,
         numbers=[T["failed_attempts"], T["successful_logins"]]),
    dict(id="B-02", tool="attacks", prompt="Which IP made the most failed login attempts, and how many?", expect=[[TF]],
         optimal_calls=1, contains=[ROOTC["ip"]], numbers=[ROOTC["failures_before"]]),
    dict(id="B-03", tool="compromise", prompt="Was the root account compromised? If so, from where and when?",
         expect=[[EL, UA, SAF, SL]], optimal_calls=2, contains=[ROOTC["ip"], _hhmm(ROOTC["login"])]),
    dict(id="B-04", tool="impact", prompt=f"What did {ROOTC['ip']} do after it logged in?", expect=[[CMD, PA]],
         optimal_calls=1, contains=[ROOTC["backdoor_user"]]),
    dict(id="B-05", tool="impact", prompt="Which user accounts were created during these days?", expect=[[PA]],
         optimal_calls=1, contains=TRUTH["accounts_created"]),
    dict(id="B-06", tool="compromise", prompt="Did anyone log in as root? Which of those logins look expected and "
         "which don't?", expect=[[UA]], optimal_calls=1, contains=[r["ip"] for r in TRUTH["root_logins"]]),
    dict(id="B-07", tool="attacks", prompt="Was there a distributed brute-force attack: many different IPs with only "
         "a few attempts each?", expect=[[TF]], optimal_calls=2,
         judge=f"PASS if the answer says yes: there was a distributed attack from many different IPs (about "
               f"{DIST['ips']}) with few attempts each (at most {DIST['max_attempts_per_ip']}), mostly against "
               f"usernames like {', '.join(DIST['users'])}. FAIL if it says no, or only describes attacks from a "
               f"single IP."),
    dict(id="B-08", tool="users", prompt="Is the backup-svc service account behaving normally?", expect=[[UA]],
         optimal_calls=1, contains=[MISUSE["ip"], "password"]),
    dict(id="B-09", tool="users", prompt="Someone logged into backup-svc with a password from an office workstation. "
         "Whose workstation was it, and when?", expect=[[UA], [UB, SL]], optimal_calls=2,
         contains=[MISUSE["workstation_owner"], _hhmm(MISUSE["time"])]),
    dict(id="B-10", tool="users", prompt="Did any user have sessions open from two different places at the same time?",
         expect=[[EL, UA]], optimal_calls=2, contains=[SIMUL["user"], SIMUL["external_ip"]]),
    dict(id="B-11", tool="privilege", prompt="Did anyone try to become root with su and fail?", expect=[], optimal_calls=1,
         contains=[SUFAIL["user"]]),
    dict(id="B-12", tool="privilege", prompt="How many times did ksato switch to root with su?", expect=[],
         optimal_calls=1, numbers=[SUOK["count"]]),
    dict(id="B-13", tool="compromise", prompt="Was root ever logged into from outside the company network?",
         expect=[[EL, UA]], optimal_calls=1, contains=[ROOTC["ip"]]),
    dict(id="B-14", tool="network", prompt=f"Is {SIMUL['vpn_ip']} part of our network? Who uses it?",
         expect=[[UB, SL]], optimal_calls=1, contains=[SIMUL["user"]],
         judge="PASS if the answer treats the IP as internal (part of the company network, e.g. the VPN). FAIL if "
               "it says the IP is external or outside the company network."),
    dict(id="B-15", tool="users", prompt="¿Qué cuentas de servicio se conectan a este servidor y desde dónde lo hacen "
         "normalmente?", expect=[[UA, SL, EL, LS]], optimal_calls=3,
         contains=[f"{name}" for name in TRUTH["services"]] + [svc["ip"] for svc in TRUTH["services"].values()]),
    dict(id="B-16", tool="attacks", prompt="How many failed login attempts were made against the root account in total?",
         expect=[[UA, LS]], optimal_calls=1, numbers=[T["root_failures"]]),
    dict(id="B-17", tool="impact", prompt=f"Which sudo commands did the attacker at {ROOTC['ip']} run as root?",
         expect=[[CMD, PA]], optimal_calls=1,
         judge="The attacker logged in directly as root, so it needed no sudo and no sudo commands were logged. PASS "
               "if the answer says there are no sudo commands from that session and does not invent commands; "
               "noting that commands run directly as root are not recorded in auth.log is a plus. FAIL if it lists "
               "sudo commands for that session or claims to know which commands root ran."),
    dict(id="B-18", tool="impact", prompt=f"When did the root session from {ROOTC['ip']} end?", expect=[[CMD, SL]],
         optimal_calls=1, contains=[_hhmm(ROOTC["logout"])]),
    dict(id="B-19", tool="overview", prompt="How many logins used keyboard-interactive authentication?", expect=[[LS]],
         optimal_calls=1, numbers=[T["keyboard_interactive_logins"]]),
    dict(id="B-20", tool="compromise", prompt="Did any external IP log in successfully without a single failed "
         "attempt first?", expect=[[EL]], optimal_calls=1, contains=[SIMUL["user"], SIMUL["external_ip"]]),
    dict(id="B-21", tool="compromise", prompt="Full incident review: were we compromised, how, and what should we do "
         "first?", expect=[[EL, SAF], [CMD, PA]], optimal_calls=6, contains=[ROOTC["ip"], ROOTC["backdoor_user"]]),
    dict(id="B-22", tool="impact", prompt="¿Hay algún indicio de que alguien haya dejado una puerta trasera en el "
         "servidor?", expect=[[PA, CMD]], optimal_calls=2, contains=[ROOTC["backdoor_user"]]),
    dict(id="B-23", tool="overview", prompt="How many distinct IPs had at least one failed login attempt?",
         expect=[[LS, TF]], optimal_calls=1, numbers=[T["ips_with_failures"]]),
    dict(id="B-24", tool="users", prompt="Which account logged in most often during these days?", expect=[],
         optimal_calls=2, contains=[TRUTH["most_frequent_login_user"][0]]),
    dict(id="B-25", tool="attacks", prompt=f"Besides root, which usernames did {ROOTC['ip']} try?", expect=[[UB]],
         optimal_calls=1, contains=[u for u in ROOTC["users_tried"] if u != "root"]),
]
