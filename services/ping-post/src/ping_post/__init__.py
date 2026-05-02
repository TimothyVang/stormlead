"""ping-post: the auction engine.

flow:
  1. accept a Lead via http or NATS
  2. enrich (geocode, attom, photo classify) - delegated to enrich-worker via hatchet
  3. fan out parallel pings to all buyers whose cel filter matches
  4. wait up to 5s for bids
  5. pick highest bidder by tier-aware effective bid
  6. POST full lead to winner with hmac-signed payload
  7. write billing event, emit nats lead.sold
  8. on no-buyer, emit lead.unsold so voice-bridge can call
"""

from stormlead_core import PingPostResult

from ping_post.auction import run_auction

__all__ = ["PingPostResult", "run_auction"]
