"""
Exercise 5 – Dynamic Workload Generator (dynamicAppDefinition.json)

This script generates a list of YAFS applications following the same
JSON structure as appDefinition2.json:
- Each application is a set of modules (microservices),
- Connected by messages (data dependencies),
- With transmissions defining how input messages are transformed
  into output messages inside each module. [web:3][web:9]

The workload is:
- PARAMETRISED via the CONFIG block (number of apps, min/max modules
  per app, RAM range, message size, instructions, deadline, etc.),
- RANDOMISED via Python's random module (module counts, tree topology,
  and message attributes), with an optional fixed SEED for reproducible
  experiments.

Parameters - edit the CONFIG block below:
  RANDOMISE       - if True, ignores SEED and uses a random seed each run
  NUM_APPS        - total number of apps to generate
  MIN_MODULES     - minimum modules per app
  MAX_MODULES     - maximum modules per app
  MAX_FANOUT      - max children a single module can branch to
  RAM_RANGE       - (min, max) RAM value per module
  BYTES_RANGE     - (min, max) bytes per message
  INSTR_RANGE     - (min, max) instructions per message
  DEADLINE        - deadline value (float) shared across all apps, like in
                    appDefinition2.json where every app has 487203.22
  SEED            - integer for reproducibility (only used when RANDOMISE=False)
"""

import json
import random
from pathlib import Path
from collections import defaultdict

# ── CONFIG ───────────────────────────────────────────────────────────────────
RANDOMISE   = False      # True  -> different output every run (ignores SEED)
                         # False -> reproducible output using SEED
NUM_APPS    = 5
MIN_MODULES = 2
MAX_MODULES = 7
MAX_FANOUT  = 3
RAM_RANGE   = (1, 8)
BYTES_RANGE = (500_000, 5_000_000)
INSTR_RANGE = (10_000, 100_000)
DEADLINE    = 487203.22
SEED        = 42
OUTPUT_FILE = Path(__file__).parent / "MYdynamicAppDefinition.json"
# ─────────────────────────────────────────────────────────────────────────────


def build_tree(mod_ids: list, max_fanout: int) -> list:
    """
    Build a random tree over mod_ids (directed edges parent->child).
    mod_ids[0] is the root. Each parent gets 1..max_fanout children until
    all nodes are placed, replicating the fan-out pattern in appDefinition2.json.
    Returns list of (parent_id, child_id) tuples.
    """
    if len(mod_ids) == 1:
        return []

    edges = []
    frontier = [mod_ids[0]]
    remaining = list(mod_ids[1:])
    random.shuffle(remaining)

    while remaining:
        # Breadth-first expansion: take next parent from frontier.
        parent = frontier.pop(0)
        # Keep branching bounded by max_fanout and remaining nodes.
        fanout = random.randint(1, min(max_fanout, len(remaining)))
        children = remaining[:fanout]
        remaining = remaining[fanout:]
        for child in children:
            edges.append((parent, child))
            # New children can become parents in subsequent iterations.
            frontier.append(child)

    return edges


def build_app(app_idx: int, global_id: int) -> tuple:
    """Return (app_dict, next_global_id)."""
    # Allocate a contiguous global id range so module ids stay unique across apps.
    num_modules = random.randint(MIN_MODULES, MAX_MODULES)
    mod_ids     = list(range(global_id, global_id + num_modules))
    root_id     = mod_ids[0]

    # modules
    modules = [
        {
            "RAM":  random.randint(*RAM_RANGE),
            "type": "MODULE",
            "id":   mid,
            "name": f"{app_idx}_{mid}",
        }
        for mid in mod_ids
    ]

    # build random tree topology between modules
    edges = build_tree(mod_ids, MAX_FANOUT)

    # messages
    entry_msg = f"M.USER.APP.{app_idx}"
    messages = [
        {
            "d":            f"{app_idx}_{root_id}",
            "bytes":        random.randint(*BYTES_RANGE),
            "name":         entry_msg,
            "s":            "None",
            "id":           0,
            "instructions": random.randint(*INSTR_RANGE),
        }
    ]
    for msg_id, (src, dst) in enumerate(edges, start=1):
        messages.append(
            {
                "d":            f"{app_idx}_{dst}",
                "bytes":        random.randint(*BYTES_RANGE),
                "name":         f"{app_idx}_({src}-{dst})",
                "s":            f"{app_idx}_{src}",
                "id":           msg_id,
                "instructions": random.randint(*INSTR_RANGE),
            }
        )

    # transmissions
    # parent_outputs maps each module to the outgoing messages it must emit.
    parent_outputs: dict = defaultdict(list)
    # child_input stores the unique incoming message that activates each child.
    child_input:    dict = {}
    for src, dst in edges:
        parent_outputs[src].append(f"{app_idx}_({src}-{dst})")
        child_input[dst] = f"{app_idx}_({src}-{dst})"

    transmissions = []

    if root_id in parent_outputs:
        # Root consumes user message and fans out to its children.
        for out_msg in parent_outputs[root_id]:
            transmissions.append(
                {
                    "message_out": out_msg,
                    "module":      f"{app_idx}_{root_id}",
                    "message_in":  entry_msg,
                }
            )
    else:
        # Single-module app: root only consumes the user entry message.
        transmissions.append(
            {
                "module":     f"{app_idx}_{root_id}",
                "message_in": entry_msg,
            }
        )

    for mid in mod_ids[1:]:
        in_msg = child_input[mid]
        if mid in parent_outputs:
            # Internal node: consumes parent message and emits one or more outputs.
            for out_msg in parent_outputs[mid]:
                transmissions.append(
                    {
                        "message_out": out_msg,
                        "module":      f"{app_idx}_{mid}",
                        "message_in":  in_msg,
                    }
                )
        else:
            # Leaf node: consumes input and terminates the flow.
            transmissions.append(
                {
                    "module":     f"{app_idx}_{mid}",
                    "message_in": in_msg,
                }
            )

    app = {
        "name":         str(app_idx),
        "transmission": transmissions,
        "module":       modules,
        "deadline":     DEADLINE,
        "message":      messages,
        "id":           app_idx,
    }
    return app, global_id + num_modules


if __name__ == "__main__":
    # Apply seed based on RANDOMISE flag
    if RANDOMISE:
        random.seed(None)    # different result every run
        print("Mode: RANDOM (no fixed seed)")
    else:
        random.seed(SEED)
        print(f"Mode: REPRODUCIBLE (seed={SEED})")

    apps = []
    gid  = 0
    # gid carries the next available global module id between applications.
    for i in range(NUM_APPS):
        app, gid = build_app(i, gid)
        apps.append(app)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=4)

    print(f"Generated {NUM_APPS} apps -> {OUTPUT_FILE}")
    for app in apps:
        print(
            f"  App {app['id']:>2}: "
            f"{len(app['module'])} modules, "
            f"{len(app['message'])} messages, "
            f"deadline={app['deadline']}"
        )
