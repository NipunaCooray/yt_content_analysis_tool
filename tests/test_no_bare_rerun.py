"""No page may call st.rerun() directly while holding a database Session.

st.rerun() raises RerunException, so a db.close() further down the page never
executes -- and the raised exception references the frame holding the Session,
forming a reference cycle that refcounting cannot break. The connection is
then only returned when the cyclic garbage collector next runs, so in
production this leaked one pooled connection per interaction until the pool
was exhausted and every page failed on checkout with
sqlalchemy.exc.TimeoutError.

Pages must use components.navigation.close_and_rerun(db) instead. This test
exists because the failure is invisible locally (SQLite uses NullPool, and a
short test run collects garbage often enough to hide it) and only shows up in
production under sustained clicking.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PAGES = sorted((Path(__file__).resolve().parent.parent / "pages").glob("*.py"))

# Matches a call to st.rerun(), but not close_and_rerun(db).
BARE_RERUN = re.compile(r"\bst\.rerun\s*\(")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_does_not_call_st_rerun_directly(page: Path):
    offenders = [
        f"{page.name}:{i}: {line.strip()}"
        for i, line in enumerate(page.read_text().splitlines(), start=1)
        if BARE_RERUN.search(line)
    ]
    assert not offenders, (
        "Use close_and_rerun(db) from components.navigation instead of st.rerun() "
        "so the pooled connection is returned:\n  " + "\n  ".join(offenders)
    )


def test_pages_holding_a_session_import_the_helper():
    """A page that opens a Session and reruns must import the helper -- this
    catches a page that reruns via some other spelling."""
    for page in PAGES:
        src = page.read_text()
        if "get_session()" in src and "close_and_rerun" in src:
            assert "from components.navigation import" in src, page.name
            assert "close_and_rerun" in src.split("db = get_session()")[0], (
                f"{page.name}: close_and_rerun used but not imported"
            )


def test_helper_closes_before_rerunning():
    """Order matters: closing after st.rerun() would never execute."""
    import ast
    import inspect

    from components import navigation

    tree = ast.parse(inspect.getsource(navigation.close_and_rerun))
    func = tree.body[0]
    # Compare the statements themselves, not the docstring -- which mentions
    # both calls and would otherwise decide the ordering.
    calls = [
        ast.unparse(node.value)
        for node in func.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert calls == ["db.close()", "st.rerun()"], calls
