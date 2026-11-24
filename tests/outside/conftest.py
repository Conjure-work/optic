"""Keeps the outside runner out of every pytest collection.

tests/outside/ holds a script run by hand against a deployed evaluation copy (outside_run.py); it is not a test module
and needs the network, the gate and the evaluation key file. No file here is named test_*.py, so neither pytest's
default collection nor tests/support/shards.py picks one up; this conftest makes that explicit for any glob.
"""

collect_ignore_glob = ["*.py"]
