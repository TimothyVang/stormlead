"""storm-watcher: polls public weather/disaster feeds, normalizes events.

sources (in priority order):
  1. nhc rss + atcf      tropical (hurricanes, ts) — fastest signal
  2. nws cap alerts       severe wx warnings (county polygons)
  3. fema openfema v2     disaster declarations (lagging, but unlocks pricing)
  4. poweroutage.us       damage proxy (real impact)

each poller writes to storms table; downstream consumers read via
postgres listen/notify or a hatchet event trigger fan-out (when
agent-runtime lands). hatchet cron schedule is in worker.py.
"""
