"""Evaluation suite for the SSH log agent.

Runs realistic analyst tasks against samples/auth.log (15 per tool), checks the
answers against known ground truth and analyzes the path the agent took:
missing tools, duplicate calls, tool errors, loops and wasted steps.

Usage (from the project root):
    python evals/run_evals.py                      # all 90 cases
    python evals/run_evals.py --tool commands_by_ip
    python evals/run_evals.py --case CMD-03 SAF-07
    python evals/run_evals.py --per-tool 2 --workers 6

    python evals/run_evals.py --diagnose           # also run the LLM root-cause diagnosis
    python evals/run_evals.py --label "stricter system prompt"
    python evals/run_evals.py --suite holdout      # unseen log and cases: measure only

Each run writes to evals/results/<timestamp>/:
    results.jsonl   one line per case: answer, checks, full tool trace, tokens,
                    hints and diagnosis
    summary.json    score and metrics per case and in total, plus what was run
                    (git commit, system prompt and tools hashes, model)
    report.md       score, comparison with the previous run, summary per tool,
                    suggested fixes by category, failures, tool usage
and appends one row to evals/history.csv.

Comparison: each run is compared with the latest earlier run that shares cases
(or --baseline), using only the common cases. Score = PASS 1, WARN 0.5, rest 0.

Non-passing cases get two kinds of feedback:
    hints       deterministic rules that point to the likely culprit
    diagnosis   (with --diagnose) an LLM reviews prompt, tools, trace and answer and returns the
                root cause, evidence, fix and where to apply it
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
from openai import OpenAI  # noqa: E402

from agent import DEFAULT_MODEL, MAX_STEPS, SYSTEM_PROMPT, LogAgent  # noqa: E402
from tools import TOOLS  # noqa: E402

DEFAULT_LOG = ROOT / "samples" / "auth.log"
HOLDOUT_LOG = ROOT / "samples" / "holdout_auth.log"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
HISTORY_FILE = Path(__file__).resolve().parent / "history.csv"

# Points per case. The run score is the average, as a percentage.
STATUS_SCORE = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0, "STUCK": 0.0, "ERROR": 0.0}

# Extra tool calls allowed over the optimal path before flagging it.
CALL_SLACK = 2
# Same tool with the same arguments this many times = the agent is looping.
LOOP_THRESHOLD = 3
API_RETRIES = 2
# Truncation of tool results and answers sent to the diagnosis model. The
# diagnosis is told when a result was cut, so it never blames the agent for it.
DIAG_RESULT_CHARS = 4000
DIAG_ANSWER_CHARS = 4000


# =============================================================================
# Cases
# =============================================================================

@dataclass
class Case:
    id: str
    tool: str                       # tool this case mainly exercises
    prompt: str
    expect: list                    # groups of tools; each group needs >= 1 call
    optimal_calls: int              # tool calls on a reasonable optimal path
    contains: list = field(default_factory=list)   # substrings that must appear
    numbers: list = field(default_factory=list)    # numbers that must appear
    any_of: list = field(default_factory=list)     # groups: at least one per group
    expect_tool_error: bool = False                # a tool error is the correct outcome (bad input)
    excludes: list = field(default_factory=list)   # substrings that must NOT appear
    judge: str = ""                                # criterion graded by an LLM (for checks text matching can't do)


LS, TF, UB = "log_summary", "top_failed_ips", "users_by_ip"
SL, SAF, CMD = "successful_logins_by_ip", "success_after_failures", "commands_by_ip"
UA = "user_activity"
EL = "external_logins"
HONESTY = "honesty"  # category, not a tool: answers that must not claim more than the log shows

NO = ["no ", "no.", "no,", "no!", "no:", "no*", "no—", "no –", "never", "nunca", "none", "ninguna", "ninguno",
      "did not", "didn't", "not "]
NOT_FOUND = ["not found", "no aparece", "not appear", "doesn't appear", "does not appear",
             "no se encontr", "no hay", "no existe", "isn't in", "is not in", "no figura"]
UNANSWERABLE = "The log cannot answer this. PASS only if the answer clearly says that this information is not in the SSH auth log or cannot be determined with the available tools. FAIL if it states a definite answer (yes, no, a value, a list) as a fact from the log."
DENIED = ["not in sudoers", "denied", "denegad", "rechaz", "failed", "falló", "no tenía permiso", "sin permiso"]

CASES = [
    # --- log_summary ---------------------------------------------------------
    Case("LS-01", LS, "Prepare a short executive briefing for the CISO about this server's SSH activity: "
         "time period covered, total failed and successful logins, and which accounts attackers target most.",
         [[LS]], 1, contains=["root"], numbers=[4147, 502]),
    Case("LS-02", LS, "¿Cuántas líneas tiene el log y cuántas de ellas son eventos de autenticación SSH?",
         [[LS]], 1, numbers=[15981, 4649]),
    Case("LS-03", LS, "How many distinct IP addresses appear in the SSH events, and how many of them "
         "had at least one failed login?", [[LS]], 1, numbers=[378, 230]),
    Case("LS-04", LS, "Un auditor quiere saber cuántos intentos fallidos se hicieron contra usuarios que ni "
         "siquiera existen en el sistema y qué porcentaje del total representan.",
         [[LS]], 1, numbers=[1633], any_of=[["39"]]),
    Case("LS-05", LS, "Which five usernames received the most failed attempts? Include the counts.",
         [[LS]], 1, contains=["root", "admin", "guest", "deploy", "test"], numbers=[2155, 281]),
    Case("LS-06", LS, "Was there any sudo activity or user account changes recorded in this log? Give me the counts.",
         [[LS]], 1, numbers=[30, 3]),
    Case("LS-07", LS, "Estoy rellenando el informe semanal: necesito eventos SSH totales, logins correctos, "
         "intentos fallidos y número de usuarios únicos.", [[LS]], 1, numbers=[4649, 502, 4147, 159]),
    Case("LS-08", LS, "What's the ratio of failed to successful logins on this server, and is that ratio alarming?",
         [[LS]], 1, numbers=[4147, 502]),
    Case("LS-09", LS, "Is 'deploy' among the most attacked accounts? It's a real service account, so tell me "
         "how many failed attempts it received.", [[LS]], 1, contains=["deploy"], numbers=[80]),
    Case("LS-10", LS, "Give me the first and last timestamp of SSH authentication activity in this log.",
         [[LS]], 1, contains=["00:02:29", "23:51:52"]),
    Case("LS-11", LS, "How many unique usernames appear in the log, counting both failed and successful logins?",
         [[LS]], 1, numbers=[159]),
    Case("LS-12", LS, "Resume el log en tres frases para un compañero que entra de guardia ahora.",
         [[LS]], 1, numbers=[4147]),
    Case("LS-13", LS, "Our SOC dashboard says there were about 4,500 failed SSH logins in this period. "
         "Does the log agree? Give me the exact figure.", [[LS]], 1, numbers=[4147]),
    Case("LS-14", LS, "Is root the most targeted account? By how many failed attempts does it exceed the second one?",
         [[LS]], 1, contains=["root", "admin"], numbers=[2155, 281]),
    Case("LS-15", LS, "Before I dig in: how big is this log and how much of it is actually SSH authentication events?",
         [[LS]], 1, numbers=[15981, 4649]),

    # --- top_failed_ips ------------------------------------------------------
    Case("TF-01", TF, "Which IP made the most failed login attempts, and did it ever manage to get in?",
         [[TF]], 1, contains=["185.220.101.47"], numbers=[1850]),
    Case("TF-02", TF, "Give me the top 3 offending IPs with their failure counts so I can add them to the "
         "firewall blocklist.", [[TF]], 1,
         contains=["185.220.101.47", "45.142.212.100", "91.240.118.52"], numbers=[1850, 900, 119]),
    Case("TF-03", TF, "Of the 10 IPs with the most failed logins, is any of them part of our internal network?",
         [[TF]], 1, any_of=[NO + ["external", "extern"]]),
    Case("TF-04", TF, "Hay una IP en el top de fallos que prueba muchos nombres de usuario distintos pero nunca "
         "consigue entrar. ¿Cuál es y cuántos usuarios distintos prueba?",
         [[TF]], 1, contains=["45.142.212.100"], numbers=[30]),
    Case("TF-05", TF, "Among the IPs with the most failures, which one has a lot of failures AND at least one "
         "successful login? That's my priority.", [[TF]], 1, contains=["91.240.118.52"]),
    Case("TF-06", TF, "I see lots of IPs starting with 194.26.29. How many of them appear in the top 30 IPs by "
         "failed attempts?", [[TF]], 1, numbers=[25]),
    Case("TF-07", TF, "List the top 5 IPs by failures and tell me which are brute-forcing a single account and "
         "which are trying many accounts.", [[TF]], 1,
         contains=["185.220.101.47", "45.142.212.100", "91.240.118.52"]),
    Case("TF-08", TF, "How many different IPs had at least one failed login?", [[TF, LS]], 1, numbers=[230]),
    Case("TF-09", TF, "Is 203.0.113.77 among the top 20 IPs by failed attempts? Which position and how many failures?",
         [[TF]], 1, contains=["203.0.113.77"], numbers=[16]),
    Case("TF-10", TF, "Which IP is fourth by number of failed logins?", [[TF]], 1,
         contains=["194.26.29.117"], numbers=[28]),
    Case("TF-11", TF, "Necesito bloquear todas las IPs con más de 100 intentos fallidos. ¿Cuáles son?", [[TF]], 1,
         contains=["185.220.101.47", "45.142.212.100", "91.240.118.52"]),
    Case("TF-12", TF, "The firewall team wants the top 10 attacking IPs with their counts, in a table.", [[TF]], 1,
         contains=["185.220.101.47", "194.26.29.198"]),
    Case("TF-13", TF, "Do any IPs from our internal 10.x network show up among the 30 IPs with the most failures? "
         "If so, which one, and should I worry?", [[TF]], 1, contains=["10.99.0.15"]),
    Case("TF-14", TF, "Compare the top two attacking IPs: how many different accounts did each one try?", [[TF]], 1,
         contains=["185.220.101.47", "45.142.212.100"], numbers=[30]),
    Case("TF-15", TF, "What share of all failed login attempts came from the single top attacking IP?",
         [[TF], [LS]], 2, numbers=[1850, 4147], any_of=[["44.6", "44,6", "45"]]),

    # --- users_by_ip ---------------------------------------------------------
    Case("UB-01", UB, "Which usernames did 185.220.101.47 try?", [[UB, TF]], 1, contains=["root"]),
    Case("UB-02", UB, "45.142.212.100 ran a dictionary attack. Which of the usernames it tried are real accounts "
         "on this system?", [[UB]], 1, contains=["root", "ansible", "backup", "deploy", "sysadmin"]),
    Case("UB-03", UB, "Did 203.0.113.77 try any usernames that don't exist on the system?", [[UB]], 1,
         contains=["admin"]),
    Case("UB-04", UB, "Which account did 203.0.113.77 try the most, and how many times?", [[UB]], 1,
         contains=["backup"], numbers=[10]),
    Case("UB-05", UB, "91.240.118.52 tried a lot of usernames. Were they real employee accounts or generic ones "
         "like admin/test? How many distinct usernames?", [[UB]], 1, numbers=[60]),
    Case("UB-06", UB, "¿Qué usuario se intentó desde 10.99.0.15 y cuántos fallos tuvo?", [[UB]], 1,
         contains=["psanchez"], numbers=[9]),
    Case("UB-07", UB, "Was 'oracle' tried from 45.142.212.100? How many times, and does that account exist here?",
         [[UB]], 1, contains=["oracle"], numbers=[22]),
    Case("UB-08", UB, "For the IP 8.8.8.8, which users were attempted?", [[UB, SL, CMD]], 1, any_of=[NOT_FOUND],
         expect_tool_error=True),
    Case("UB-09", UB, "Which usernames were tried from 999.1.1.1?", [], 1, expect_tool_error=True,
         any_of=[["invalid", "inválid", "válid", "not a valid", "isn't a valid", "not valid",
                  "out of range", "fuera de rango"]]),
    Case("UB-10", UB, "From 194.26.29.117, which accounts were targeted and how many times each?", [[UB]], 1,
         contains=["root", "admin"], numbers=[15, 13]),
    Case("UB-11", UB, "Did the attacker at 45.142.212.100 ever try the 'backup' account? How many times?", [[UB]], 1,
         numbers=[39]),
    Case("UB-12", UB, "Find the IP that got into mlopez's account after failing, and tell me how many other "
         "employees it tried before that.", [[SAF, TF, SL, UA]], 1,
         contains=["91.240.118.52"], any_of=[["59", "60", "42", "41"]]),
    Case("UB-13", UB, "Which IP tried the 'deploy' account the most?", [[UB, UA]], 1,
         contains=["45.142.212.100"], numbers=[28]),
    Case("UB-14", UB, "For each of the top 3 attacking IPs, how many different usernames did they try and were any "
         "of them real accounts?", [[TF], [UB]], 4,
         contains=["185.220.101.47", "45.142.212.100", "91.240.118.52"]),
    Case("UB-15", UB, "¿Se probó el usuario 'sysadmin' desde alguna de las IPs con más fallos? ¿Desde cuál y cuántas veces?",
         [[TF], [UB]], 3, contains=["45.142.212.100", "sysadmin"], numbers=[18]),

    # --- successful_logins_by_ip ---------------------------------------------
    Case("SL-01", SL, "Did 185.220.101.47 ever manage to log in?", [[SL, TF]], 1, any_of=[NO]),
    Case("SL-02", SL, "When exactly did 91.240.118.52 log in, as which user and with which auth method?", [[SL]], 1,
         contains=["mlopez", "password", "15:27"]),
    Case("SL-03", SL, "List all successful logins from 203.0.113.77.", [[SL]], 1,
         contains=["backup", "svc-update", "01:51", "04:03"]),
    Case("SL-04", SL, "How many failed attempts did 203.0.113.77 make before its first successful login?",
         [[SL, SAF]], 1, numbers=[16]),
    Case("SL-05", SL, "10.99.0.15 had several failed logins. Did it eventually get in, and when?", [[SL]], 1,
         contains=["psanchez", "10:48"]),
    Case("SL-06", SL, "How many times did 10.20.0.40 log in, and as which user?", [[SL]], 1,
         contains=["monitor"], numbers=[72]),
    Case("SL-07", SL, "Which users logged in from 10.20.0.5, how many times, and with what auth method?", [[SL]], 1,
         contains=["sysadmin", "publickey"], numbers=[9]),
    Case("SL-08", SL, "La IP 10.20.8.64 aparece con algunos fallos. ¿Sus logins son normales o sospechosos?",
         [[SL]], 1, contains=["jrey"], numbers=[5]),
    Case("SL-09", SL, "Did 45.142.212.100 succeed in logging in at any point?", [[SL, TF]], 1, any_of=[NO]),
    Case("SL-10", SL, "Check 10.20.0.30: how many logins, which account and what auth method?", [[SL]], 1,
         contains=["deploy", "publickey"], numbers=[5]),
    Case("SL-11", SL, "Did any of the 194.26.29.x IPs that appear at the top of the failure ranking get in?",
         [[TF, SL, SAF]], 1, any_of=[NO]),
    Case("SL-12", SL, "An alert says 203.0.113.77 logged in as two different accounts. Confirm which accounts and "
         "the time gap between both logins.", [[SL]], 1,
         contains=["backup", "svc-update"], any_of=[["2 h", "2h", "2 hour", "2 hora", "132", "2:11", "2:12"]]),
    Case("SL-13", SL, "Which authentication method did the attacker use when logging in from 91.240.118.52?",
         [[SL, SAF]], 1, contains=["password"]),
    Case("SL-14", SL, "From 10.20.0.15, who logged in and how many times?", [[SL]], 1,
         contains=["backup"], numbers=[3]),
    Case("SL-15", SL, "Did anyone log in from 8.8.8.8?", [[SL, UB, CMD]], 1, any_of=[NOT_FOUND + NO],
         expect_tool_error=True),

    # --- success_after_failures ----------------------------------------------
    Case("SAF-01", SAF, "Did any IP log in successfully after a series of failed attempts? List them.", [[SAF]], 1,
         contains=["91.240.118.52", "203.0.113.77"]),
    Case("SAF-02", SAF, "Find compromised accounts in this log and tell me which ones are real intrusions and which "
         "are just employees who mistyped their password.", [[SAF]], 3,
         contains=["mlopez", "backup", "psanchez"]),
    Case("SAF-03", SAF, "Which external IPs got in after failing more than 10 times?", [[SAF]], 1,
         contains=["91.240.118.52", "203.0.113.77"]),
    Case("SAF-04", SAF, "Was any IP successful after more than 50 failed attempts?", [[SAF]], 1,
         contains=["91.240.118.52"], numbers=[83]),
    Case("SAF-05", SAF, "How many IPs logged in after at least one failed attempt?", [[SAF]], 1, numbers=[29]),
    Case("SAF-06", SAF, "Is there any IP from which a user logged in after exactly 9 failed attempts?", [[SAF]], 1,
         contains=["10.99.0.15", "psanchez"]),
    Case("SAF-07", SAF, "HR reports that employee mlopez got a strange 'new login' alert on Nov 10. Investigate "
         "whether the account was compromised, from where, and how the attacker found the password.",
         [[SAF, SL, UA]], 2, contains=["91.240.118.52"]),
    Case("SAF-08", SAF, "The 'backup' service account behaved strangely on Nov 11. Find out whether someone broke "
         "into it, from which IP and after how many failed attempts.", [[SAF, SL]], 1,
         contains=["203.0.113.77"], numbers=[16]),
    Case("SAF-09", SAF, "Which internal IPs show a failure-then-success pattern with 3 or more failures? "
         "Are they worrying?", [[SAF]], 1, contains=["10.99.0.15", "10.20.8.64"]),
    Case("SAF-10", SAF, "¿Qué cuenta fue la primera en ser comprometida desde una IP externa, cronológicamente?",
         [[SAF, EL]], 1, contains=["mlopez"]),
    Case("SAF-11", SAF, "The top failure ranking looks scary, but I care about attacks that actually worked, even "
         "quiet ones. Find low-volume attacks that succeeded.", [[SAF, EL]], 1, contains=["203.0.113.77"]),
    Case("SAF-12", SAF, "For each IP that got in after 3+ failures, how many distinct usernames did it try before "
         "succeeding?", [[SAF]], 1, contains=["91.240.118.52", "203.0.113.77"], numbers=[42, 6]),
    Case("SAF-13", SAF, "Was there a successful password spray attack? Explain how you know.", [[SAF]], 2,
         contains=["91.240.118.52", "mlopez"]),
    Case("SAF-14", SAF, "Using a threshold of 2 failed attempts, how many IPs succeed after failing?", [[SAF]], 1,
         numbers=[18]),
    Case("SAF-15", SAF, "Among the IPs that got in after 3+ failures, which one used public key authentication "
         "for that login?", [[SAF]], 1, contains=["10.20.8.64", "jrey"]),

    # --- commands_by_ip ------------------------------------------------------
    Case("CMD-01", CMD, "What did 203.0.113.77 do after logging in?", [[CMD]], 1,
         contains=["shadow", "svc-update", "wget"]),
    Case("CMD-02", CMD, "Did the attacker who got into mlopez's account manage to escalate privileges?",
         [[SAF, SL, UA], [CMD]], 2, any_of=[DENIED]),
    Case("CMD-03", CMD, "Full incident response: find any account compromised from an external IP, determine what "
         "the attacker did after logging in (privilege use, new accounts, persistence) and list concrete "
         "cleanup steps.", [[SAF, EL], [CMD]], 5, contains=["203.0.113.77", "svc-update", "crontab"]),
    Case("CMD-04", CMD, "Was any new user created on the system during these 3 days? By which account and from "
         "which IP?", [[CMD]], 3, contains=["svc-update", "backup", "203.0.113.77"]),
    Case("CMD-05", CMD, "What sudo commands did sysadmin run from 10.20.0.5?", [[CMD]], 1, contains=["apt upgrade"]),
    Case("CMD-06", CMD, "List the privileged commands the deploy account ran from 10.20.0.30.", [[CMD]], 1,
         contains=["app.service"]),
    Case("CMD-07", CMD, "Which privileged commands were run from 10.20.0.15?", [[CMD]], 1, contains=["backup.sh"]),
    Case("CMD-08", CMD, "Were any commands executed from 185.220.101.47?", [[CMD, SL, TF]], 1, any_of=[NO]),
    Case("CMD-09", CMD, "Did anyone download and execute a script on this server? Who, when and from where?",
         [[CMD]], 3, contains=["wget", "x.sh", "svc-update", "203.0.113.77"]),
    Case("CMD-10", CMD, "Some commands from the backup account session on Nov 11 are flagged as ambiguous. Explain "
         "why, and which ones definitely came from the attacker.", [[CMD]], 2,
         contains=["shadow", "10.20.0.15"]),
    Case("CMD-11", CMD, "Did the attacker at 203.0.113.77 read the password hashes?", [[CMD]], 1,
         contains=["shadow"]),
    Case("CMD-12", CMD, "¿Se ejecutó algún comando con sudo desde la IP 91.240.118.52? ¿Tuvo éxito?", [[CMD]], 1,
         any_of=[DENIED]),
    Case("CMD-13", CMD, "What did the svc-update account do, and is it a legitimate account?", [[SAF, SL, UA], [CMD]], 2,
         contains=["wget", "203.0.113.77"]),
    Case("CMD-14", CMD, "Show me jgarcia's sudo activity from 10.20.2.16.", [[CMD]], 1,
         contains=["apt update", "nginx"]),
    Case("CMD-15", CMD, "Determine whether the intruder established persistence on the server. Provide evidence "
         "with timestamps.", [[CMD]], 3, contains=["crontab", "svc-update"]),

    # --- user_activity -------------------------------------------------------
    Case("UA-01", UA, "HR reports that mlopez got a 'new login from an unusual location' alert. From which IPs has "
         "mlopez logged in, and is any of them outside our network?", [[UA]], 1, contains=["91.240.118.52"]),
    Case("UA-02", UA, "When was the svc-update account created, and from where has it logged in?", [[UA]], 1,
         contains=["02:06", "203.0.113.77"]),
    Case("UA-03", UA, "Has the deploy service account ever logged in from outside the company network?", [[UA]], 1,
         contains=["10.20.0.30"], any_of=[NO]),
    Case("UA-04", UA, "Does an account called 'oracle' exist on this server? How many times did attackers try it?",
         [[UA]], 1, numbers=[71], any_of=[["not exist", "doesn't exist", "does not exist", "no existe", "nonexistent",
                                           "non-existent", "invalid", "inexistente", "there is no",
                                           "no such", "no hay ninguna cuenta"]]),
    Case("UA-05", UA, "¿Desde qué IPs se conecta normalmente jgarcia y con qué método?", [[UA]], 1,
         contains=["10.20.2.16", "10.99.0.121"]),
    Case("UA-06", UA, "How many failed attempts did the backup account receive, and from which IPs?", [[UA]], 1,
         contains=["45.142.212.100", "203.0.113.77"], numbers=[49, 39]),
    Case("UA-07", UA, "psanchez says they were locked out on Nov 11. How many failed attempts did their account have, "
         "and from where?", [[UA]], 1, contains=["10.99.0.15", "91.240.118.52"], numbers=[11]),
    Case("UA-08", UA, "How many times did the monitor account log in, and was it always from the same machine?",
         [[UA]], 1, contains=["10.20.0.40"], numbers=[72]),
    Case("UA-09", UA, "Did sysadmin ever log in with a password, or only with SSH keys? From where?", [[UA]], 1,
         contains=["publickey", "10.20.0.5"]),
    Case("UA-10", UA, "Was the mlopez account able to run anything as root?", [[UA, CMD]], 2, any_of=[DENIED]),
    Case("UA-11", UA, "Look up the user 'nobody': has it been used on this server?", [[UA]], 1,
         any_of=[NOT_FOUND + NO], expect_tool_error=True),
    Case("UA-12", UA, "Which IP attacked the root account the most, and how many failed attempts did root get in total?",
         [[UA]], 1, contains=["185.220.101.47"], numbers=[1850, 2155]),
    Case("UA-13", UA, "jrey had failed logins. How many came from inside the network and how many from outside, "
         "and from which IPs?", [[UA]], 1, contains=["10.20.8.64", "91.240.118.52"], numbers=[3]),
    Case("UA-14", UA, "¿Qué usuario se conecta desde la IP 10.20.0.5 y con qué frecuencia lo hace?", [[UB, SL, UA]], 1, contains=["sysadmin"]),
    Case("UA-15", UA, "Investigate the employee account jrey: is there any sign that it was compromised?", [[UA]], 1,
         contains=["10.20.8.64", "91.240.118.52"]),

    # --- external_logins ------------------------------------------------------
    Case("EL-01", EL, "Did anyone log in from outside the company network? List them.", [[EL]], 1,
         contains=["91.240.118.52", "203.0.113.77", "mlopez", "backup", "svc-update"]),
    Case("EL-02", EL, "How many successful logins came from external IPs?", [[EL]], 1, numbers=[3]),
    Case("EL-03", EL, "Which accounts were accessed from outside the network, and do those users normally log in "
         "from inside?", [[EL]], 1, contains=["mlopez", "backup", "svc-update"]),
    Case("EL-04", EL, "Was any external login made without a single failed attempt first, like a stolen SSH key "
         "would be?", [[EL]], 1, any_of=[NO]),
    Case("EL-05", EL, "Which login from outside the network happened first, and when?", [[EL]], 1,
         contains=["mlopez", "15:27"]),
    Case("EL-06", EL, "What was the most recent login from outside the network?", [[EL]], 1,
         contains=["svc-update", "04:03"]),
    Case("EL-07", EL, "Did the svc-update account ever log in from inside the network?", [[EL, UA]], 1, any_of=[NO]),
    Case("EL-08", EL, "¿Desde qué IPs externas se ha entrado en el servidor y con qué cuentas?", [[EL]], 1,
         contains=["91.240.118.52", "203.0.113.77", "mlopez", "backup", "svc-update"]),
    Case("EL-09", EL, "Did any external IP log into more than one account?", [[EL]], 1,
         contains=["203.0.113.77", "backup", "svc-update"]),
    Case("EL-10", EL, "How many failed attempts did each external IP make before its first successful login?",
         [[EL]], 1, numbers=[83, 16]),
    Case("EL-11", EL, "Did any login from outside the network use public key authentication?", [[EL]], 1,
         any_of=[NO]),
    Case("EL-12", EL, "Has the backup account logged in from outside the network? It should only connect from the "
         "backup server.", [[EL, UA]], 1, contains=["203.0.113.77", "01:51"]),
    Case("EL-13", EL, "Were there logins from outside the network at night, between 00:00 and 06:00?", [[EL]], 1,
         contains=["backup", "svc-update", "203.0.113.77"]),
    Case("EL-14", EL, "List the external logins in a table with user, IP, time and authentication method.",
         [[EL]], 1, contains=["mlopez", "backup", "svc-update", "password"]),
    Case("EL-15", EL, "Is there any external login by a user that never logs in from inside the network?", [[EL]], 1,
         contains=["svc-update"]),

    # --- honesty: don't claim more than the log shows --------------------------
    # Questions auth.log can't answer: the right answer says so.
    Case("HN-01", HONESTY, "Which files did the attacker at 203.0.113.77 read without using sudo?", [], 1,
         judge=UNANSWERABLE),
    Case("HN-02", HONESTY, "What country is 185.220.101.47 located in?", [], 0, judge=UNANSWERABLE),
    Case("HN-03", HONESTY, "What password did the attacker use to log into mlopez's account?", [], 0, judge=UNANSWERABLE),
    Case("HN-04", HONESTY, "Did the attacker copy files off the server with scp or rsync?", [], 1, judge=UNANSWERABLE),
    Case("HN-05", HONESTY, "¿Qué comandos ejecutó el atacante con la cuenta mlopez sin usar sudo?", [], 1,
         judge=UNANSWERABLE),
    Case("HN-06", HONESTY, "Did the firewall block 45.142.212.100 at some point?", [], 0, judge=UNANSWERABLE),
    Case("HN-07", HONESTY, "How much data did the attacker transfer during the backup account session?", [], 1,
         judge=UNANSWERABLE),
    Case("HN-08", HONESTY, "Did 91.240.118.52 also attack other servers of the company?", [], 0, judge=UNANSWERABLE),
    # Log-wide questions whose answer is "yes" but needs checking the whole log:
    # a partial check must not turn into a confident "no" (held-out H-12, dev log 023).
    Case("HN-09", HONESTY, "Was any user denied sudo on this server during these days? Who?", [[CMD, UA, SAF, EL]], 3,
         contains=["mlopez"]),
    Case("HN-10", HONESTY, "Did anyone read /etc/shadow on this server?", [[CMD]], 3,
         contains=["shadow", "203.0.113.77"]),
]


def load_suite(name: str) -> list[Case]:
    if name == "holdout":
        from holdout_cases import HOLDOUT_CASES
        return [Case(**c) for c in HOLDOUT_CASES]
    return CASES


# =============================================================================
# Answer checks
# =============================================================================

def _number_pattern(n: int) -> re.Pattern:
    """Match a number allowing thousands separators: 4147, 4,147, 4.147, 4 147."""
    digits = str(n)
    head, groups = digits[: len(digits) % 3 or 3], []
    rest = digits[len(head):]
    groups = [rest[i:i + 3] for i in range(0, len(rest), 3)]
    body = head + "".join(rf"[.,\s ]?{g}" for g in groups)
    return re.compile(rf"(?<![\d.,:\-]){body}(?!\d)(?![.,]\d)")


# Frequent function words per language. The language of a text is the one whose
# words appear most often. Enough to tell apart the languages seen in practice.
STOPWORDS = {
    "en": {"the", "and", "of", "to", "is", "was", "in", "from", "with", "that", "this", "it", "for", "are",
           "were", "did", "has", "have", "which", "not", "no", "on", "by", "any", "all", "after", "before"},
    "es": {"el", "la", "los", "las", "de", "del", "y", "que", "en", "con", "por", "para", "es", "fue",
           "una", "un", "se", "su", "sus", "al", "lo", "como", "desde", "tras", "antes", "hay", "pero"},
    "nl": {"de", "het", "een", "en", "van", "is", "niet", "geen", "met", "voor", "op", "zijn", "dat", "die",
           "heeft", "nooit", "deze", "ook", "nee", "wel", "naar"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "kein", "keine", "mit", "von", "den", "dem", "ein",
           "eine", "wurde", "auf", "für", "sich", "auch"},
    "fr": {"le", "la", "les", "et", "est", "des", "une", "un", "du", "dans", "pour", "pas", "aucun", "avec",
           "sur", "qui", "que", "été"},
    "pt": {"o", "os", "as", "e", "é", "do", "da", "dos", "das", "não", "nenhum", "com", "uma", "em", "foi"},
    "it": {"il", "lo", "gli", "e", "è", "di", "che", "non", "nessun", "con", "una", "per", "sono", "della"},
}
NON_LATIN_SCRIPT = re.compile(r"[Ѐ-ӿ؀-ۿ฀-๿぀-ヿ一-鿿가-힯]")
VIETNAMESE = re.compile(r"[ạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹđơư]", re.IGNORECASE)
_CODE = re.compile(r"`[^`]*`|```.*?```", re.DOTALL)
_WORD = re.compile(r"[^\W\d_]+")


def detect_language(text: str) -> str:
    """Rough language guess: 'en', 'es', 'nl', ..., 'vi', 'non-latin' or 'unknown'."""
    text = _CODE.sub(" ", text)  # IPs, usernames and commands are not language
    if NON_LATIN_SCRIPT.search(text):
        return "non-latin"
    if len(VIETNAMESE.findall(text)) >= 3:
        return "vi"
    words = Counter(w.lower() for w in _WORD.findall(text))
    scores = {lang: sum(words[w] for w in stop) for lang, stop in STOPWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else "unknown"


def check_answer(case: Case, answer: str) -> list[str]:
    """Return a list of failed checks (empty if all passed)."""
    text = answer.lower()
    failed = []
    # Cases are written in English or Spanish; short prompts may not be detected.
    expected_lang = "es" if detect_language(case.prompt) == "es" else "en"
    answer_lang = detect_language(answer)
    if answer_lang not in (expected_lang, "unknown"):
        failed.append(f"wrong language: answered in {answer_lang}, question is in {expected_lang}")
    for s in case.contains:
        if s.lower() not in text:
            failed.append(f"missing text: {s!r}")
    for n in case.numbers:
        if not _number_pattern(n).search(answer):
            failed.append(f"missing number: {n}")
    for group in case.any_of:
        if not any(s.lower() in text for s in group):
            failed.append(f"missing any of: {group}")
    for s in case.excludes:
        if s.lower() in text:
            failed.append(f"unexpected text: {s!r}")
    return failed


# =============================================================================
# Path analysis
# =============================================================================

def _call_key(call: dict) -> tuple:
    try:
        args = json.loads(call["arguments"] or "{}")
    except json.JSONDecodeError:
        args = call["arguments"]
    return call["name"], json.dumps(args, sort_keys=True)


def analyze_path(case: Case, trace: dict) -> dict:
    calls = trace["tool_calls"]
    names = [c["name"] for c in calls]
    used = set(names)

    missing = [g for g in case.expect if not used.intersection(g)]
    expected_union = {t for g in case.expect for t in g}
    extra = sorted(used - expected_union) if case.expect else sorted(used)

    keys = Counter(_call_key(c) for c in calls)
    duplicates = [f"{name}({args}) x{n}" for (name, args), n in keys.items() if n > 1]
    looping = [f"{name}({args}) x{n}" for (name, args), n in keys.items() if n >= LOOP_THRESHOLD]
    errors = [f"{c['name']}: {c['error']}" for c in calls if c["error"]]

    budget = case.optimal_calls + CALL_SLACK
    return {
        "tool_sequence": names,
        "tool_call_count": len(calls),
        "optimal_calls": case.optimal_calls,
        "efficiency": round(case.optimal_calls / len(calls), 2) if calls else (1.0 if case.optimal_calls == 0 else 0.0),
        "over_budget": len(calls) > budget,
        "missing_expected_tools": missing,
        "extra_tools": extra,
        "duplicate_calls": duplicates,
        "looping_calls": looping,
        "tool_errors": errors,
    }


def classify(result: dict, case: Case) -> tuple[str, list[str]]:
    """Return (status, reasons). Status: ERROR, STUCK, FAIL, WARN or PASS."""
    if result.get("exception"):
        return "ERROR", [result["exception"]]

    path = result["path"]
    trace = result["trace"]
    reasons = []

    stuck = []
    if trace["hit_max_steps"]:
        stuck.append(f"hit MAX_STEPS ({MAX_STEPS}) without a final answer")
    if path["looping_calls"]:
        stuck.append(f"looping: {'; '.join(path['looping_calls'])}")
    if stuck:
        return "STUCK", stuck + result["failed_checks"]

    if result["failed_checks"]:
        return "FAIL", result["failed_checks"]

    if path["missing_expected_tools"]:
        reasons.append(f"did not use expected tools: {path['missing_expected_tools']}")
    if path["duplicate_calls"]:
        reasons.append(f"duplicate calls: {'; '.join(path['duplicate_calls'])}")
    if path["over_budget"]:
        reasons.append(f"{path['tool_call_count']} tool calls, optimal ~{path['optimal_calls']}")
    if path["tool_errors"] and not case.expect_tool_error:
        reasons.append(f"tool errors: {'; '.join(path['tool_errors'])}")
    return ("WARN" if reasons else "PASS"), reasons


# =============================================================================
# Diagnosis: rule-based hints + LLM root-cause analysis
# =============================================================================

def rule_hints(case: Case, result: dict) -> list[str]:
    """Cheap, deterministic pointers to where the problem probably is."""
    if "path" not in result:
        return ["API error: check DEEPSEEK_API_KEY, network and rate limits."]

    path, trace = result["path"], result["trace"]
    seq = path["tool_sequence"]
    expected = {t for g in case.expect for t in g}
    hints = []

    if path["over_budget"] and seq and seq[0] == "log_summary" and "log_summary" not in expected:
        hints.append("Unneeded log_summary first call: the system prompt rule 'Start with log_summary' "
                     "applies to every question. Make it conditional on broad questions (agent.py, SYSTEM_PROMPT).")
    if path["over_budget"] and "commands_by_ip" in seq and "commands_by_ip" not in expected:
        hints.append("commands_by_ip called on a question that doesn't ask about impact: the system prompt "
                     "says to run it for every external IP that logged in. Limit it to incident questions.")
    if path["over_budget"] and not hints:
        hints.append("Over-investigation: tell the agent to answer exactly what was asked and stop when it "
                     "has enough data (SYSTEM_PROMPT).")
    if path["duplicate_calls"]:
        hints.append("Same call repeated: the model may not trust or remember earlier results. Add "
                     "'never repeat a tool call with the same arguments' to SYSTEM_PROMPT.")
    if path["missing_expected_tools"]:
        missing = ", ".join(t for g in path["missing_expected_tools"] for t in g)
        hints.append(f"Expected tool(s) not used ({missing}): their description may not say clearly WHEN to "
                     "use them (tools.py, TOOLS). If the answer is still correct, the case may be too strict.")
    if any("Invalid arguments" in e for e in path["tool_errors"]):
        hints.append("Wrong argument names: check parameter names and descriptions in the tool schema (tools.py).")
    if trace["hit_max_steps"] or path["looping_calls"]:
        hints.append("Agent stuck: inspect results.jsonl for the repeated call. Usually a tool returns an error "
                     "or truncated data the model keeps retrying. Consider a hint in the error message itself.")
    if result["failed_checks"]:
        hints.append("Wrong/incomplete answer: check in results.jsonl whether the expected value was in any "
                     "tool result. If yes -> prompt/reasoning issue; if no -> tool or path issue.")
    return hints


JUDGE_MODEL = DEFAULT_MODEL
JUDGE_PROMPT = """You grade one answer of an assistant that analyzes SSH authentication logs
(auth.log) with tools. You receive the user's question, a grading criterion and the answer.
Decide only whether the answer meets the criterion; ignore style, length and language.
Return only JSON: {"pass": true|false, "reason": "<one sentence>"}"""


def apply_checks(case: Case, answer: str, judge=None) -> tuple[list[str], dict | None]:
    """Text checks plus, if the case has a criterion, the LLM judge."""
    failed = check_answer(case, answer)
    verdict = None
    if case.judge:
        verdict = (judge or judge_answer)(case, answer)
        if not verdict["pass"]:
            failed.append(f"judge: {verdict['reason']}")
    return failed, verdict


def judge_answer(case: Case, answer: str, model: str = JUDGE_MODEL) -> dict:
    """Grade an answer against case.judge with an LLM. Errors count as a failed check."""
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": json.dumps(
                    {"question": case.prompt, "criterion": case.judge, "answer": answer}, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        verdict = json.loads(response.choices[0].message.content)
        return {"pass": bool(verdict.get("pass")), "reason": str(verdict.get("reason", ""))}
    except Exception as e:
        return {"pass": False, "reason": f"judge error: {type(e).__name__}: {e}"}


DIAGNOSIS_PROMPT = """You review runs of an LLM agent that analyzes SSH auth logs using tools.
You receive the agent's system prompt, its tool descriptions, an evaluation case, and the
run (tool calls with their results, final answer, failed checks and path warnings).

Find the ROOT CAUSE of the failure or inefficiency and propose a concrete fix.

Categories:
- system_prompt: the agent's instructions caused or allowed the behavior
- tool_description: a tool's name/description/parameters misled the model or don't say when to use it
- tool_output: a tool returned too little, too much, or confusing data
- missing_tool: no tool answers this directly, so the agent had to improvise
- model_reasoning: the data was available and clear but the model misread or ignored it
- eval_case: the agent's behavior is actually fine; the expected checks or optimal path are wrong

Rules:
- Base every claim on the run data. Quote the instruction, description or result that matters.
- Some tool results are cut ONLY for this review (truncated_for_review: true). The agent always
  received the full result (result_chars characters). Never conclude that the agent lacked data,
  or that a tool truncated its output, because of this cut.
- The fix must be actionable: say which file and element to change and propose the new wording or code idea.
- If the answer is correct and the extra calls were reasonable, say so and use eval_case.
- Write all text fields in {language}.

Return only JSON:
{{"category": "...", "root_cause": "...", "evidence": "...", "fix": "...", "where": "...", "confidence": "high|medium|low"}}"""


def _review_result(call: dict) -> dict:
    """Tool result as shown to the diagnosis model, flagging any truncation."""
    full_size = call.get("result_chars", 0)
    shown = call.get("result", "")[:DIAG_RESULT_CHARS]
    return {
        "result": shown,
        "result_chars": full_size,
        "truncated_for_review": len(shown) < full_size,
    }


def diagnose(case: Case, result: dict, model: str, language: str) -> dict:
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    run = {
        "status": result["status"],
        "reasons": result["reasons"],
        "failed_checks": result.get("failed_checks", []),
        "steps": result["trace"]["steps"],
        "tool_calls": [
            {
                "step": c["step"],
                "name": c["name"],
                "arguments": c["arguments"],
                "error": c["error"],
                **_review_result(c),
            }
            for c in result["trace"]["tool_calls"]
        ],
        "answer": result["answer"][:DIAG_ANSWER_CHARS],
    }
    payload = {
        "agent_system_prompt": SYSTEM_PROMPT,
        "tools": [{"name": t["function"]["name"], "description": t["function"]["description"]} for t in TOOLS],
        "case": {
            "prompt": case.prompt,
            "expected_tools": case.expect,
            "optimal_calls": case.optimal_calls,
            "must_contain": case.contains,
            "must_contain_numbers": case.numbers,
            "must_contain_one_of_each_group": case.any_of,
            "must_not_contain": case.excludes,
            "judge_criterion": case.judge,
        },
        "run": run,
    }
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DIAGNOSIS_PROMPT.format(language=language)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


# =============================================================================
# Runner
# =============================================================================

def run_case(case: Case, log_path: str, model: str, diagnose_with: str | None = None,
             language: str = "Spanish") -> dict:
    result = {"id": case.id, "tool": case.tool, "prompt": case.prompt}
    last_error = None

    for attempt in range(1, API_RETRIES + 2):
        agent = LogAgent(log_path, model=model)
        started = time.perf_counter()
        try:
            answer = agent.ask(case.prompt)
        except Exception as e:  # API / network errors
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(2 * attempt)
            continue

        trace = agent.last_trace
        result.update({
            "answer": answer,
            "seconds": round(time.perf_counter() - started, 2),
            "attempts": attempt,
            "trace": trace,
            "path": analyze_path(case, trace),
        })
        result["failed_checks"], result["judge"] = apply_checks(case, answer)
        break
    else:
        result.update({"exception": last_error, "attempts": API_RETRIES + 1})

    result["status"], result["reasons"] = classify(result, case)

    if result["status"] != "PASS":
        result["hints"] = rule_hints(case, result)
        if diagnose_with and "trace" in result:
            try:
                result["diagnosis"] = diagnose(case, result, diagnose_with, language)
            except Exception as e:
                result["diagnosis"] = {"error": f"{type(e).__name__}: {e}"}
    return result


def select_cases(args, cases: list[Case]) -> list[Case]:
    if args.case:
        wanted = {c.upper() for c in args.case}
        cases = [c for c in cases if c.id in wanted]
    if args.tool:
        cases = [c for c in cases if c.tool in args.tool]
    if args.per_tool:
        counts = Counter()
        selected = []
        for c in cases:
            if counts[c.tool] < args.per_tool:
                selected.append(c)
                counts[c.tool] += 1
        cases = selected
    return cases


# =============================================================================
# Report
# =============================================================================

STATUS_ORDER = ["PASS", "WARN", "FAIL", "STUCK", "ERROR"]


# =============================================================================
# Scoring, history and comparison between runs
# =============================================================================

def _short_hash(obj) -> str:
    data = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:8]


def _git_info() -> dict:
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    dirty = [l for l in git("status", "--porcelain").splitlines() if "evals/results/" not in l
             and not l.endswith("evals/history.csv")]
    return {"git_commit": git("rev-parse", "--short", "HEAD") or "unknown", "git_dirty": bool(dirty)}


def case_record(r: dict) -> dict:
    record = {"status": r["status"], "score": STATUS_SCORE[r["status"]]}
    if "trace" in r:
        record.update({
            "tool_calls": r["path"]["tool_call_count"],
            "tokens": r["trace"]["prompt_tokens"] + r["trace"]["completion_tokens"],
            "seconds": r["seconds"],
        })
    return record


def aggregate(cases: dict) -> dict:
    """Metrics for a {case_id: record} dict."""
    n = len(cases)
    statuses = Counter(c["status"] for c in cases.values())
    measured = [c for c in cases.values() if "tool_calls" in c]
    avg = lambda key: round(sum(c[key] for c in measured) / len(measured), 2) if measured else 0  # noqa: E731
    return {
        "cases": n,
        "score": round(100 * sum(c["score"] for c in cases.values()) / n, 1) if n else 0.0,
        **{s.lower(): statuses.get(s, 0) for s in STATUS_ORDER},
        "avg_tool_calls": avg("tool_calls"),
        "avg_tokens": int(avg("tokens")),
        "avg_seconds": avg("seconds"),
    }


def build_summary(results: list[dict], meta: dict) -> dict:
    cases = {r["id"]: case_record(r) for r in results}
    return {"meta": meta, "totals": aggregate(cases), "cases": cases}


def load_summary(run_dir: Path) -> dict | None:
    """Load a run's summary. Older runs without summary.json are rebuilt from results.jsonl."""
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    jsonl = run_dir / "results.jsonl"
    if not jsonl.exists():
        return None
    results = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    return build_summary(results, {"run": run_dir.name, "label": "", "git_commit": "unknown",
                                   "prompt_hash": "unknown", "tools_hash": "unknown",
                                   "evals_hash": "unknown"})


def find_baseline(current_dir: Path, case_ids: set, explicit: str | None) -> tuple[Path, dict] | None:
    """The run to compare against: --baseline if given, else the latest earlier run sharing cases."""
    if explicit:
        path = Path(explicit) if Path(explicit).is_dir() else RESULTS_DIR / explicit
        summary = load_summary(path)
        return (path, summary) if summary else None

    for run_dir in sorted((d for d in RESULTS_DIR.iterdir() if d.is_dir()), reverse=True):
        if run_dir == current_dir or run_dir.name > current_dir.name:
            continue
        summary = load_summary(run_dir)
        if summary and case_ids & summary["cases"].keys():
            return run_dir, summary
    return None


def compare(current: dict, baseline: dict) -> dict:
    common = sorted(current["cases"].keys() & baseline["cases"].keys())
    before = aggregate({c: baseline["cases"][c] for c in common})
    after = aggregate({c: current["cases"][c] for c in common})

    improved, regressed, fewer_calls, more_calls = [], [], [], []
    for cid in common:
        b, a = baseline["cases"][cid], current["cases"][cid]
        change = f"{cid}: {b['status']} → {a['status']}"
        if a["score"] > b["score"]:
            improved.append(change)
        elif a["score"] < b["score"]:
            regressed.append(change)
        elif "tool_calls" in a and "tool_calls" in b and a["tool_calls"] != b["tool_calls"]:
            target = fewer_calls if a["tool_calls"] < b["tool_calls"] else more_calls
            target.append(f"{cid}: {b['tool_calls']} → {a['tool_calls']} calls ({a['status']})")

    bm, cm = baseline["meta"], current["meta"]

    def differs(key):  # None = can't tell (older run without this info)
        if bm.get(key, "unknown") == "unknown" or cm.get(key, "unknown") == "unknown":
            return None
        return bm[key] != cm[key]

    return {
        "baseline_run": bm.get("run"),
        "baseline_label": bm.get("label", ""),
        "common_cases": len(common),
        "before": before,
        "after": after,
        "improved": improved,
        "regressed": regressed,
        "fewer_calls": fewer_calls,
        "more_calls": more_calls,
        "changed": {
            "system_prompt": differs("prompt_hash"),
            "tools": differs("tools_hash"),
            "model": differs("model"),
            "evals": differs("evals_hash"),
            "commit": f"{bm.get('git_commit')} → {cm.get('git_commit')}",
        },
    }


def verdict(cmp: dict) -> str:
    delta = cmp["after"]["score"] - cmp["before"]["score"]
    n_changed = len(cmp["improved"]) + len(cmp["regressed"])
    if n_changed == 0:
        return "No status changes: same result as the baseline."
    if cmp["improved"] and cmp["regressed"]:
        return (f"Mixed: {len(cmp['improved'])} improved, {len(cmp['regressed'])} regressed "
                f"(score {delta:+.1f}). Check the regressions before keeping the change.")
    if n_changed <= 2:
        return (f"Score {delta:+.1f} from only {n_changed} case(s): could be LLM randomness. "
                "Re-run the affected cases before concluding.")
    return f"{'Improvement' if delta > 0 else 'Regression'}: score {delta:+.1f} across {n_changed} cases."


def append_history(summary: dict) -> None:
    meta, totals = summary["meta"], summary["totals"]
    row = {
        "run": meta["run"], "label": meta.get("label", ""), "git_commit": meta["git_commit"],
        "git_dirty": meta["git_dirty"], "model": meta["model"], "prompt_hash": meta["prompt_hash"],
        "tools_hash": meta["tools_hash"], "evals_hash": meta["evals_hash"], **totals,
    }
    new_file = not HISTORY_FILE.exists()
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def comparison_lines(cmp: dict | None) -> list[str]:
    if not cmp:
        return ["## Comparison with previous run", "", "No previous run with overlapping cases.", ""]

    b, a = cmp["before"], cmp["after"]
    label = f" ({cmp['baseline_label']})" if cmp["baseline_label"] else ""
    ch = cmp["changed"]
    names = ("system_prompt", "tools", "model", "evals")
    changed = [n for n in names if ch[n]]
    unknown = [n for n in names if ch[n] is None]
    changed_str = ", ".join(changed) or ("unknown" if unknown else "nothing tracked")
    if changed and unknown:
        changed_str += f" (unknown: {', '.join(unknown)})"
    lines = [
        "## Comparison with previous run",
        "",
        f"Baseline: `{cmp['baseline_run']}`{label} · {cmp['common_cases']} common cases · "
        f"commit {ch['commit']} · changed: {changed_str}",
        "",
        *(["> ⚠️ The eval cases or scoring changed since the baseline, so scores are not directly comparable.", ""]
          if ch["evals"] else []),
        f"**{verdict(cmp)}**",
        "",
        "| Metric | Before | After | Δ |",
        "|---|---|---|---|",
    ]
    for key, name in [("score", "Score (%)"), ("pass", "PASS"), ("warn", "WARN"), ("fail", "FAIL"),
                      ("stuck", "STUCK"), ("error", "ERROR"), ("avg_tool_calls", "Avg tool calls"),
                      ("avg_tokens", "Avg tokens"), ("avg_seconds", "Avg seconds")]:
        delta = a[key] - b[key]
        delta_str = f"{delta:+.2f}".rstrip("0").rstrip(".") if isinstance(delta, float) else f"{delta:+d}"
        lines.append(f"| {name} | {b[key]} | {a[key]} | {delta_str if delta else '='} |")
    for title, items in [("Improved", cmp["improved"]), ("Regressed", cmp["regressed"]),
                         ("Same status, fewer tool calls", cmp["fewer_calls"]),
                         ("Same status, more tool calls", cmp["more_calls"])]:
        if items:
            lines += ["", f"**{title}:** " + " · ".join(items)]
    lines.append("")
    return lines


def write_report(results: list[dict], out_dir: Path, meta: dict, summary: dict,
                 comparison: dict | None) -> Path:
    results = sorted(results, key=lambda r: r["id"])
    by_status = Counter(r["status"] for r in results)
    ok = [r for r in results if "trace" in r]

    total_prompt = sum(r["trace"]["prompt_tokens"] for r in ok)
    total_completion = sum(r["trace"]["completion_tokens"] for r in ok)
    total_calls = sum(r["path"]["tool_call_count"] for r in ok)

    lines = [
        f"# Eval report — {meta['started']}" + (f" — {meta['label']}" if meta.get("label") else ""),
        "",
        f"**Score: {summary['totals']['score']}%** (PASS = 1, WARN = 0.5, others = 0)",
        "",
        f"- Model: `{meta['model']}` · commit `{meta['git_commit']}`"
        + (" (uncommitted changes)" if meta["git_dirty"] else "")
        + f" · prompt `{meta['prompt_hash']}` · tools `{meta['tools_hash']}` · evals `{meta['evals_hash']}`",
        f"- Log: `{meta['log']}`",
        f"- Cases: {len(results)} · Duration: {meta['duration']}s",
        f"- Tokens: {total_prompt:,} prompt + {total_completion:,} completion",
        f"- Tool calls: {total_calls} (avg {total_calls / max(len(ok), 1):.1f} per case)",
        "",
        "| " + " | ".join(STATUS_ORDER) + " |",
        "|" + "---|" * len(STATUS_ORDER),
        "| " + " | ".join(str(by_status.get(s, 0)) for s in STATUS_ORDER) + " |",
        "",
        "**PASS** correct and efficient · **WARN** correct but suboptimal path · "
        "**FAIL** wrong or incomplete answer · **STUCK** loop or step limit · **ERROR** API failure",
        "",
        *comparison_lines(comparison),
        "## By tool",
        "",
        "| Tool | Cases | PASS | WARN | FAIL | STUCK | ERROR | Avg calls | Avg efficiency | Avg seconds |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    groups = defaultdict(list)
    for r in results:
        groups[r["tool"]].append(r)
    for tool, rs in groups.items():
        st = Counter(r["status"] for r in rs)
        good = [r for r in rs if "trace" in r]
        avg = lambda key: sum(key(r) for r in good) / max(len(good), 1)  # noqa: E731
        lines.append(
            f"| `{tool}` | {len(rs)} | " + " | ".join(str(st.get(s, 0)) for s in STATUS_ORDER)
            + f" | {avg(lambda r: r['path']['tool_call_count']):.1f}"
            + f" | {avg(lambda r: r['path']['efficiency']):.2f}"
            + f" | {avg(lambda r: r['seconds']):.1f} |"
        )

    issues = [r for r in results if r["status"] != "PASS"]

    diagnosed = [r for r in issues if r.get("diagnosis") and "error" not in r["diagnosis"]]
    if diagnosed:
        by_category = defaultdict(list)
        for r in diagnosed:
            by_category[r["diagnosis"].get("category", "unknown")].append(r)
        lines += ["", "## Suggested fixes by category", ""]
        for category, rs in sorted(by_category.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"### `{category}` — {len(rs)} case(s)")
            lines.append("")
            for r in rs:
                d = r["diagnosis"]
                lines.append(f"- **{r['id']}** ({d.get('confidence', '?')}): {d.get('fix', '')}  ")
                lines.append(f"  _Where:_ {d.get('where', '')}")
            lines.append("")

    if issues:
        lines += ["", "## Cases needing attention", ""]
        for status in ["ERROR", "STUCK", "FAIL", "WARN"]:
            for r in (r for r in issues if r["status"] == status):
                lines.append(f"### {r['id']} — {status}")
                lines.append(f"> {r['prompt']}")
                lines.append("")
                if "path" in r:
                    seq = " → ".join(r["path"]["tool_sequence"]) or "(no tool calls)"
                    lines.append(f"- Path: {seq}")
                    lines.append(f"- Steps: {r['trace']['steps']} · Seconds: {r['seconds']}")
                for reason in r["reasons"]:
                    lines.append(f"- {reason}")
                if r.get("hints"):
                    lines.append("")
                    lines.append("**Hints:**")
                    for hint in r["hints"]:
                        lines.append(f"- {hint}")
                d = r.get("diagnosis")
                if d and "error" in d:
                    lines += ["", f"**Diagnosis failed:** {d['error']}"]
                elif d:
                    lines += [
                        "",
                        f"**Diagnosis** — `{d.get('category', '?')}` · confidence: {d.get('confidence', '?')}",
                        f"- **Root cause:** {d.get('root_cause', '')}",
                        f"- **Evidence:** {d.get('evidence', '')}",
                        f"- **Fix:** {d.get('fix', '')}",
                        f"- **Where:** {d.get('where', '')}",
                    ]
                lines.append("")

    usage = Counter(c["name"] for r in ok for c in r["trace"]["tool_calls"])
    first = Counter(r["path"]["tool_sequence"][0] for r in ok if r["path"]["tool_sequence"])
    lines += ["## Tool usage", "", "| Tool | Total calls | Used as first call |", "|---|---|---|"]
    for name, n in usage.most_common():
        lines.append(f"| `{name}` | {n} | {first.get(name, 0)} |")

    lines += ["", "## All cases", "", "| Case | Status | Calls | Optimal | Path |", "|---|---|---|---|---|"]
    for r in results:
        if "path" in r:
            seq = " → ".join(r["path"]["tool_sequence"]) or "—"
            lines.append(f"| {r['id']} | {r['status']} | {r['path']['tool_call_count']} | "
                         f"{r['path']['optimal_calls']} | {seq} |")
        else:
            lines.append(f"| {r['id']} | {r['status']} | — | — | — |")

    path = out_dir / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Run the evaluation suite for the log agent.")
    parser.add_argument("--suite", choices=["main", "holdout"], default="main",
                        help="main: 105 cases on samples/auth.log; holdout: unseen log and cases (measure only)")
    parser.add_argument("--log", default=None, help="log file to evaluate against (default depends on --suite)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--tool", nargs="+", help="only cases for these tools")
    parser.add_argument("--case", nargs="+", help="only these case ids, e.g. CMD-03 SAF-07")
    parser.add_argument("--per-tool", type=int, help="max cases per tool")
    parser.add_argument("--workers", type=int, default=4, help="cases run in parallel")
    parser.add_argument("--diagnose", action="store_true",
                        help="run the LLM root-cause analysis of non-passing cases (extra API calls)")
    parser.add_argument("--diagnose-model", default=DEFAULT_MODEL, help="model used for diagnosis")
    parser.add_argument("--lang", default="Spanish", help="language of the diagnosis text")
    parser.add_argument("--label", help="short description of this run, e.g. 'stricter system prompt'")
    parser.add_argument("--baseline", help="run to compare against (folder name in evals/results/); "
                                           "default: latest earlier run sharing cases")
    parser.add_argument("--no-compare", action="store_true", help="skip the comparison")
    args = parser.parse_args()
    diagnose_with = args.diagnose_model if args.diagnose else None

    suite_cases = load_suite(args.suite)
    if args.log is None:
        args.log = str(HOLDOUT_LOG if args.suite == "holdout" else DEFAULT_LOG)
    cases = select_cases(args, suite_cases)
    if not cases:
        parser.error("no cases selected")

    started = datetime.now()
    out_dir = RESULTS_DIR / started.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "results.jsonl"

    print(f"Running {len(cases)} cases with {args.workers} workers -> {out_dir}\n")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool, open(jsonl_path, "w", encoding="utf-8") as jsonl:
        futures = {
            pool.submit(run_case, c, args.log, args.model, diagnose_with, args.lang): c for c in cases
        }
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            results.append(r)
            jsonl.write(json.dumps(r, ensure_ascii=False) + "\n")
            jsonl.flush()
            calls = r["path"]["tool_call_count"] if "path" in r else "-"
            detail = f" — {r['reasons'][0]}" if r["reasons"] else ""
            print(f"[{i:>2}/{len(cases)}] {r['id']:<7} {r['status']:<5} calls={calls}{detail}")
            d = r.get("diagnosis")
            if d and "fix" in d:
                print(f"           [{d.get('category')}] {d['fix']}")

    meta = {
        "run": out_dir.name,
        "label": (f"[holdout] {args.label}" if args.suite == "holdout" else args.label) or "",
        "suite": args.suite,
        "started": started.strftime("%Y-%m-%d %H:%M:%S"),
        "model": args.model,
        "log": args.log,
        "duration": round((datetime.now() - started).total_seconds(), 1),
        "prompt_hash": _short_hash(SYSTEM_PROMPT),
        "tools_hash": _short_hash(TOOLS),
        "evals_hash": _short_hash([[asdict(c) for c in suite_cases], STATUS_SCORE, CALL_SLACK, LOOP_THRESHOLD]),
        **_git_info(),
    }
    summary = build_summary(results, meta)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    baseline = None if args.no_compare else find_baseline(out_dir, set(summary["cases"]), args.baseline)
    comparison = compare(summary, baseline[1]) if baseline else None
    report = write_report(results, out_dir, meta, summary, comparison)
    append_history(summary)

    totals = summary["totals"]
    print("\n" + " · ".join(f"{s}: {totals[s.lower()]}" for s in STATUS_ORDER) + f" · Score: {totals['score']}%")
    if comparison:
        delta = comparison["after"]["score"] - comparison["before"]["score"]
        print(f"vs {comparison['baseline_run']} ({comparison['common_cases']} common cases): "
              f"{comparison['before']['score']}% → {comparison['after']['score']}% ({delta:+.1f})")
        print(f"  {verdict(comparison)}")
        if comparison["changed"]["evals"]:
            print("  Warning: eval cases or scoring changed since the baseline; scores are not directly comparable.")
        for item in comparison["regressed"]:
            print(f"  regressed: {item}")
    print(f"Report:  {report}\nDetails: {jsonl_path}\nHistory: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
