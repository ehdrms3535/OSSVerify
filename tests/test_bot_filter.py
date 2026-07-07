"""봇 필터링 — _is_bot(), _BOT_LOGINS frozenset."""
from ossverify.collector.github_collector import _BOT_LOGINS, _is_bot


def test_known_bots_all_detected():
    for login in _BOT_LOGINS:
        assert _is_bot(login), f"{login!r} should be detected as bot"

def test_bot_suffix_pattern():
    assert _is_bot("some-custom[bot]")
    assert _is_bot("myapp[bot]")
    assert _is_bot("x[bot]")

def test_dependabot_variants():
    assert _is_bot("dependabot")
    assert _is_bot("dependabot[bot]")

def test_real_users_not_bot():
    for login in ["torvalds", "octocat", "ehdrms3535", "alice", "bob123"]:
        assert not _is_bot(login), f"{login!r} should not be a bot"

def test_empty_string_not_bot():
    assert not _is_bot("")

def test_substring_not_enough():
    # "[bot]"이 suffix가 아닌 경우
    assert not _is_bot("notabot")
    assert not _is_bot("robot")
    assert not _is_bot("mybot")
