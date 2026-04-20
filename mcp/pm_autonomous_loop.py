"""
PM autonomous loop — runs until pending_total=0, executing tasks in parallel blocks.
Spawns concurrent _pm_execute_task calls when multiple tasks are ready.
"""
import asyncio
import json
import sys

sys.path.insert(0, r"c:/multiagent-system-suite")

from orchestrator.mcp.n8n_mcp_server import (
    pm_sync_backlog,
    pm_plan_backlog,
    _pm_execute_task_autonomously,
)

MAX_PARALLEL = 3          # execute up to 3 tasks in parallel
MAX_ITERATIONS = 20       # safety cap
WAIT_BETWEEN_BLOCKS = 5  # seconds between blocks


async def run_block(ready_items: list) -> list:
    """Execute a block of ready tasks in parallel, return results."""
    batch = ready_items[:MAX_PARALLEL]
    tasks = [
        _pm_execute_task_autonomously(
            issue_key=item["issue_key"],
            task_id=item["task_id"],
            summary=item["summary"],
        )
        for item in batch
        if item.get("issue_key")
    ]
    if not tasks:
        return []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for item, res in zip(batch, results):
        if isinstance(res, Exception):
            out.append({"task_id": item["task_id"], "issue_key": item["issue_key"], "ok": False, "error": str(res)})
        else:
            out.append(res)
    return out


async def main():
    print("=== PM AUTONOMOUS LOOP START ===", flush=True)

    # 1. Sync catalog to Jira (idempotent)
    sync = await pm_sync_backlog()
    print(f"[SYNC] created_epics={sync.get('created_epics',[])} created_tasks={sync.get('created_tasks',[])}", flush=True)

    all_results = []
    for iteration in range(1, MAX_ITERATIONS + 1):
        plan = await pm_plan_backlog(limit=MAX_PARALLEL)
        pending = plan.get("pending_total", 0)
        ready = plan.get("ready_total", 0)
        next_items = plan.get("next", [])

        print(f"\n[ITER {iteration}] pending={pending} ready={ready}", flush=True)

        if pending == 0:
            print("[DONE] All catalog tasks completed in Jira.", flush=True)
            break

        if ready == 0:
            print("[BLOCKED] No ready tasks — all remaining tasks are waiting on dependencies.", flush=True)
            # Print blocking summary
            for item in (plan.get("pending", []) or []):
                print(f"  - {item.get('task_id')} blocked by {item.get('deps')}", flush=True)
            break

        print(f"[EXEC] Running block: {[i['task_id'] + '/' + i['issue_key'] for i in next_items]}", flush=True)
        block_results = await run_block(next_items)
        all_results.extend(block_results)

        closed = [r for r in block_results if r.get("closed")]
        failed = [r for r in block_results if not r.get("closed")]
        print(f"  closed={[r.get('issue_key') for r in closed]}", flush=True)
        if failed:
            print(f"  failed={[r.get('issue_key') for r in failed]}", flush=True)

        if not closed and not failed:
            print("[WARN] Empty block result — stopping.", flush=True)
            break

        if iteration < MAX_ITERATIONS:
            await asyncio.sleep(WAIT_BETWEEN_BLOCKS)

    # Final state
    final_plan = await pm_plan_backlog(limit=50)
    print(f"\n=== FINAL STATE ===", flush=True)
    print(f"pending_total={final_plan['pending_total']} ready_total={final_plan['ready_total']}", flush=True)
    if final_plan["pending_total"] == 0:
        print("SUCCESS: Jira backlog is fully complete (0 pending).", flush=True)
    else:
        print("INCOMPLETE: remaining tasks:", flush=True)
        for item in final_plan.get("next", []):
            print(f"  {item['task_id']} / {item['issue_key']} — {item['summary']} | deps_ready={item['deps_ready']}", flush=True)

    print("\nALL_RESULTS=" + json.dumps(all_results, ensure_ascii=True), flush=True)


asyncio.run(main())
