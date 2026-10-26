import os

# The apps these tests start never run the automatic-backup thread by themselves: it would wake up inside a temporary home in the middle of a test.
# test_maint_autobackup.py drives the scheduler directly, with its own clock.
os.environ.setdefault("DECOMP_NO_AUTO_BACKUP", "1")
