"""
Simple logging API.
"""
import os
import sys
import traceback

import datetime

levels = ["error", "warn", "info", "debug"]

level = os.getenv("LOG_LEVEL", "info")
logfile = os.getenv("LOG_FILE", None)

listeners = []

debugging = level == levels[-1]

if not level in levels:
    levels.append(level)

def write(log_level, args):
    def dump(o):
        if isinstance(o, Exception) and debugging:
            return "%s: %s" % (str(o), traceback.format_exc())
        else:
            return str(o)

    if levels.index(log_level) > levels.index(level):
        return

    message = ": ".join(dump(v) for v in args)

    ts = datetime.datetime.utcnow()
    line = "%sZ: %s: %s\n" % (ts, log_level, message)

    if logfile:
        with open(logfile, 'a' if os.path.exists(logfile) else 'w') as f:
            f.write(line)
    else:
        sys.stderr.write(line)

    [l(ts, log_level, message) for l in listeners]

def add_listener(listener):
    global listeners

    if not listener in listeners:
        listeners.append(listener)

def remove_listener(listener=None):
    global listeners

    if not listener:
        listeners = []
    elif listener in listeners:
        listeners.remove(listener)


def _make_log_function(ll):
    def llt(*args):
        write(ll, args)

    return llt

module = sys.modules[__name__]
for ll in levels:
    setattr(module, ll, _make_log_function(ll))
