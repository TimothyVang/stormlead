"""agent-runtime: Hatchet workers for StormLead.

two hatchet workflows registered:
  qualify_lead            event-triggered (lead.captured); LiteLLM-routed model call
  hermes_self_evolution   weekly cron (mon 09:00 utc); LiteLLM-routed model call

All model traffic goes through the LiteLLM proxy. Do not add direct provider SDKs here.
"""
