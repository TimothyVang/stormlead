from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from hatchet_sdk import Hatchet
from stormlead_core import PipelineState, ReplayPlan, build_replay_plan
from stormlead_db import get_session, has_active_transition, latest_state


def print_plan(plan: ReplayPlan, *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"Replay mode: {mode}")
    print(f"Lead ID: {plan.lead_id}")
    print(f"From state: {plan.from_state.value if plan.from_state else 'none'}")
    print(f"Event: {plan.event_name or 'none'}")
    print(f"Executable: {plan.executable}")
    print(f"Reason: {plan.reason}")


async def resolve_plan(lead_id: UUID, requested_state: PipelineState | None) -> ReplayPlan:
    async with get_session() as session:
        if await has_active_transition(session, lead_id):
            return ReplayPlan(
                lead_id=lead_id,
                from_state=requested_state,
                event_name=None,
                reason="lead has an active in-flight transition; refusing replay",
                executable=False,
            )
        state = (
            requested_state if requested_state is not None else await latest_state(session, lead_id)
        )
    return build_replay_plan(lead_id, state)


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or execute lead workflow replay.")
    parser.add_argument("--lead-id", required=True)
    parser.add_argument("--from-state", choices=[state.value for state in PipelineState])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    lead_id = UUID(args.lead_id)
    requested_state = PipelineState(args.from_state) if args.from_state else None
    plan = await resolve_plan(lead_id, requested_state)
    print_plan(plan, execute=args.execute)
    if not args.execute:
        return 0 if plan.executable else 2
    if not plan.executable or plan.event_name is None:
        return 2
    Hatchet(debug=False).event.push(plan.event_name, {"lead_id": str(lead_id), "replay": True})
    print(f"Pushed Hatchet event: {plan.event_name}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
