"""Which IPs count as internal (dev log 019)."""

import os
import subprocess
import sys

import pytest

import tools
from tools import _is_internal, parse_networks, set_internal_networks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def restore_networks(monkeypatch):
    # set_internal_networks changes a module global; put it back after the test.
    monkeypatch.setattr(tools, "INTERNAL_NETWORKS", tools.INTERNAL_NETWORKS)


@pytest.mark.parametrize("ip, internal", [
    ("10.20.0.5", True),
    ("172.16.5.16", True),
    ("172.31.255.1", True),
    ("172.32.0.1", False),          # just outside 172.16.0.0/12
    ("192.168.1.50", True),
    ("fd12:3456::1", True),         # IPv6 unique local
    ("8.8.8.8", False),
    # Documentation ranges: ipaddress.is_private says True, but they must be external.
    ("203.0.113.77", False),
    ("192.0.2.88", False),
    ("198.51.100.23", False),
    ("2001:db8:4f3a:12::17", False),
])
def test_default_internal_networks(ip, internal, restore_networks):
    set_internal_networks(tools.DEFAULT_INTERNAL_NETWORKS)  # independent of the environment
    assert _is_internal(ip) is internal


def test_set_internal_networks(restore_networks):
    set_internal_networks("192.168.0.0/16")
    assert _is_internal("192.168.1.50") is True
    assert _is_internal("10.20.0.5") is False


@pytest.mark.parametrize("spec", ["", "bogus", "10.0.0.0/33", " , "])
def test_invalid_networks_are_rejected(spec):
    with pytest.raises(ValueError):
        parse_networks(spec)


def test_environment_variable_configures_networks():
    env = {**os.environ, tools.INTERNAL_NETWORKS_ENV: "100.64.0.0/10"}
    code = "import tools; print(tools._is_internal('100.64.1.1'), tools._is_internal('10.0.0.1'))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert out.stdout.split() == ["True", "False"]


def test_agent_cli_rejects_invalid_networks():
    out = subprocess.run([sys.executable, "agent.py", "samples/auth.log", "--internal-networks", "bogus", "-q", "x"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 2
    assert "--internal-networks" in out.stderr
