"""compare.js task polling must suspend in hidden tabs (B13 F7 / FL-D557).

A browser-level check would need tab-visibility emulation; these source pins
lock the two invariants the fix introduced: the 2.5 s refetch is scheduled
only while the page is visible, and returning to the foreground re-arms it.
"""

from pathlib import Path


def test_compare_polling_is_visibility_gated():
    source = Path("frontend/compare.js").read_text(encoding="utf-8")
    assert "function schedulePoll(id)" in source
    assert "document.visibilityState!=='visible'" in source
    assert "state.poll=setTimeout(()=>openTask(id),2500)" in source
    # The unconditional scheduling is gone from openTask.
    assert source.count("setTimeout(()=>openTask(id),2500)") == 1


def test_compare_polling_resumes_on_foreground():
    source = Path("frontend/compare.js").read_text(encoding="utf-8")
    assert "visibilitychange" in source
    assert "state.pollTaskId" in source
    resume = source.index("visibilitychange")
    assert "schedulePoll(state.pollTaskId)" in source[resume:]
