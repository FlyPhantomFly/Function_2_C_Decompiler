# Test fixtures

`db-0.10.6.sqlite` is a real database written by **upstream decomp.wtf 0.10.6** (git tag `upstream-0.10.6`), made by
`make_db_0_10_6.py` with the untouched upstream code, not with this fork's. It is what an unversioned upstream database looks like
(`PRAGMA user_version` is 0): one agent (only a hash of its token), the demo project's 13 functions (1 matched, 12 open), attempts,
notes, events and two versions of the shared header. It exists so `test_maint_schema.py` can prove that a database from before
this fork still opens, migrates and keeps its data.

To regenerate it (only if the generator changes; the test pins what it expects):

    git worktree add /tmp/upstream upstream-0.10.6 && cd /tmp/upstream && uv sync --locked
    uv run python <this folder>/make_db_0_10_6.py projects/demo <this folder>/db-0.10.6.sqlite

It holds no personal data. `projects.root` is a temporary directory path from the machine that made it; opening the database
never reads it.
