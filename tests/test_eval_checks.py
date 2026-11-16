"""The evals' own answer checks. They are code too, and three false FAILs
(dev log 003, 008, 010) came from them."""

import pytest

from run_evals import CASES, Case, _number_pattern, analyze_path, check_answer, classify, detect_language


@pytest.mark.parametrize("n, text, matches", [
    (4147, "hubo 4.147 fallos", True),
    (4147, "4,147 failures", True),
    (4147, "4147", True),
    (15981, "15 981 líneas", True),
    (113, "203.0.113.77", False),       # part of an IP
    (16, "a las 04:03:16", False),       # part of a time
    (16, "16 fallos.", True),
    (9, "10.99.0.9", False),
])
def test_number_pattern(n, text, matches):
    assert bool(_number_pattern(n).search(text)) is matches


@pytest.mark.parametrize("text, lang", [
    ("No, none of the top 10 IPs is internal; all of them are external and were blocked.", "en"),
    ("No, ninguna de las IPs es interna: todas son externas y se han bloqueado por el firewall.", "es"),
    ("Nee — geen enkele van de 10 IP's is intern, het zijn allemaal externe adressen.", "nl"),
    ("Không — không có IP nội bộ nào trong top 10 của danh sách này.", "vi"),
    ("只尝试了 root 这一个用户名。", "non-latin"),
    ("Только два внешних IP-адреса вошли после попыток.", "non-latin"),
    ("185.220.101.47", "unknown"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


def test_detect_language_ignores_code_spans():
    assert detect_language("`el los las de del y que en con por`") == "unknown"


def _case(**kw):
    defaults = dict(id="X-01", tool="log_summary", prompt="Which IP attacked the most and was it blocked?",
                    expect=[["top_failed_ips"]], optimal_calls=1)
    return Case(**{**defaults, **kw})


def test_check_answer_flags_wrong_language():
    case = _case(contains=["185.220.101.47"])
    answer = "La IP con más fallos es 185.220.101.47 y no consiguió entrar en el sistema."
    assert any(f.startswith("wrong language") for f in check_answer(case, answer))


def test_check_answer_accepts_variants():
    case = _case(any_of=[["no ", "no.", "no*"]], numbers=[1850])
    assert check_answer(case, "**No.** It made 1,850 failed attempts and never got in.") == []


def _result(calls, answer_checks=None, hit_max=False):
    trace = {"tool_calls": [{"name": n, "arguments": a, "error": e} for n, a, e in calls],
             "hit_max_steps": hit_max, "steps": len(calls) + 1}
    return {"trace": trace, "failed_checks": answer_checks or []}


def test_classify_pass_and_warn():
    case = _case()
    ok = _result([("top_failed_ips", "{}", None)])
    ok["path"] = analyze_path(case, ok["trace"])
    assert classify(ok, case)[0] == "PASS"

    slow = _result([("log_summary", "{}", None)] + [("users_by_ip", f'{{"ip": "1.1.1.{i}"}}', None) for i in range(4)])
    slow["path"] = analyze_path(case, slow["trace"])
    status, reasons = classify(slow, case)
    assert status == "WARN"
    assert any("did not use expected tools" in r for r in reasons)


def test_classify_detects_loops():
    case = _case()
    looping = _result([("top_failed_ips", '{"n": 5}', None)] * 3)
    looping["path"] = analyze_path(case, looping["trace"])
    assert classify(looping, case)[0] == "STUCK"


def test_classify_expected_tool_error_is_not_penalized():
    calls = [("users_by_ip", '{"ip": "999.1.1.1"}', "not a valid IP address")]
    strict, lenient = _case(expect=[["users_by_ip"]]), _case(expect=[["users_by_ip"]], expect_tool_error=True)
    for case, expected in ((strict, "WARN"), (lenient, "PASS")):
        r = _result(calls)
        r["path"] = analyze_path(case, r["trace"])
        assert classify(r, case)[0] == expected


def test_cases_are_well_formed():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))
    from run_evals import HONESTY
    from tools import TOOL_FUNCTIONS
    assert {t for c in CASES for g in c.expect for t in g} <= set(TOOL_FUNCTIONS)
    assert {c.tool for c in CASES} <= set(TOOL_FUNCTIONS) | {HONESTY}


def test_spanish_cases_are_detected_as_spanish():
    # A Spanish prompt detected as English would make the language check fail
    # every correct Spanish answer (see UA-14 in dev log 014).
    spanish = [c for c in CASES if "¿" in c.prompt or c.prompt.startswith(("Un ", "Estoy", "Resume", "Hay", "Necesito", "La IP"))]
    assert spanish
    assert all(detect_language(c.prompt) == "es" for c in spanish)


def test_check_answer_excludes():
    case = _case(any_of=[["no "]], excludes=["194.26.29"])
    assert check_answer(case, "There was no coordinated subnet attack in this log.") == []
    assert any("unexpected text" in f for f in check_answer(case, "Yes, from 194.26.29.0/24 and no more."))


def test_holdout_cases_are_well_formed():
    from run_evals import load_suite
    from tools import TOOL_FUNCTIONS
    holdout = load_suite("holdout")
    assert len(holdout) == 25
    assert len({c.id for c in holdout}) == 25
    assert not {c.id for c in holdout} & {c.id for c in CASES}
    assert {t for c in holdout for g in c.expect for t in g} <= set(TOOL_FUNCTIONS)
    # Every case checks something.
    assert all(c.contains or c.numbers or c.any_of for c in holdout)


def test_holdout_spanish_cases_are_detected_as_spanish():
    from run_evals import load_suite
    spanish = [c for c in load_suite("holdout") if "¿" in c.prompt]
    assert spanish and all(detect_language(c.prompt) == "es" for c in spanish)


def test_judge_failures_become_failed_checks():
    from run_evals import apply_checks
    case = _case(judge="Must say the log can't answer this.")
    failed, verdict = apply_checks(case, "It can't be known.", judge=lambda c, a: {"pass": False, "reason": "too vague"})
    assert failed == ["judge: too vague"] and verdict["pass"] is False
    failed, _ = apply_checks(case, "It can't be known.", judge=lambda c, a: {"pass": True, "reason": "ok"})
    assert failed == []


def test_no_judge_call_without_criterion():
    from run_evals import apply_checks
    def explode(c, a):
        raise AssertionError("judge must not be called")
    assert apply_checks(_case(), "anything", judge=explode) == ([], None)
