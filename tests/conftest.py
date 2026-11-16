from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LOG = ROOT / "samples" / "auth.log"

# A tiny log that exercises every rule of the parser:
# - one failed attempt produces several lines, but must count once
# - invalid users, double-space days, sudo (allowed and denied), account changes
# - a session that closes and one that stays open
MINI_LOG = """\
Nov  9 08:00:01 srv sshd[100]: Invalid user admin from 1.2.3.4 port 5000
Nov  9 08:00:02 srv sshd[100]: pam_unix(sshd:auth): check pass; user unknown
Nov  9 08:00:03 srv sshd[100]: Failed password for invalid user admin from 1.2.3.4 port 5000 ssh2
Nov  9 08:00:04 srv sshd[100]: Connection closed by invalid user admin 1.2.3.4 port 5000 [preauth]
Nov  9 08:01:00 srv sshd[101]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=1.2.3.4  user=root
Nov  9 08:01:01 srv sshd[101]: Failed password for root from 1.2.3.4 port 5001 ssh2
Nov  9 08:02:00 srv sshd[102]: Failed password for alice from 1.2.3.4 port 5002 ssh2
Nov  9 08:03:00 srv sshd[103]: Accepted password for alice from 1.2.3.4 port 5003 ssh2
Nov  9 08:03:00 srv sshd[103]: pam_unix(sshd:session): session opened for user alice(uid=1001) by (uid=0)
Nov  9 08:05:00 srv sudo:    alice : TTY=pts/0 ; PWD=/home/alice ; USER=root ; COMMAND=/usr/bin/cat /etc/shadow
Nov  9 08:06:00 srv sudo:    alice : user NOT in sudoers ; TTY=pts/0 ; PWD=/home/alice ; USER=root ; COMMAND=/bin/bash
Nov  9 08:07:00 srv useradd[200]: new user: name=evil, UID=1999, GID=1999, home=/home/evil, shell=/bin/bash, from=/dev/pts/0
Nov  9 08:10:00 srv sshd[103]: pam_unix(sshd:session): session closed for user alice
Nov 10 09:00:00 srv sshd[104]: Accepted publickey for bob from 10.0.0.5 port 6000 ssh2: RSA SHA256:abc
Nov 10 09:00:01 srv CRON[300]: pam_unix(cron:session): session opened for user root(uid=0) by (uid=0)
"""


@pytest.fixture
def mini_log(tmp_path):
    path = tmp_path / "auth.log"
    path.write_text(MINI_LOG)
    return str(path)


@pytest.fixture
def write_log(tmp_path):
    """Write arbitrary log content and return its path."""
    def _write(content: str, name: str = "custom.log") -> str:
        path = tmp_path / name
        path.write_text(content)
        return str(path)
    return _write


@pytest.fixture(scope="session")
def sample_log():
    return str(SAMPLE_LOG)
