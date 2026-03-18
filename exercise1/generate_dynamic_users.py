"""
Exercise 7 – Dynamic Population Generator (dynamicUsersDefinition.json)

This script generates a YAFS population definition following the same
JSON structure as usersDefinition2.json:
- A single top-level "sources" list,
- Each entry describes one user source: which network node generates
  requests ("id_resource"), for which application ("app"), which entry
  message it sends ("message"), and at what Poisson arrival rate ("lambda").

The workload is:
- PARAMETRISED via the CONFIG block (number of apps, node count,
  sources per app, lambda range, etc.),
- RANDOMISED via Python's random module (node selection, lambda values),
  with an optional fixed SEED for reproducible experiments.

Parameters – edit the CONFIG block below:
  RANDOMISE            - if True, ignores SEED and uses a random seed each run
  NUM_APPS             - number of applications to generate sources for;
                         must match the number of apps in your app definition
  NUM_NODES            - total nodes in the network topology (node IDs are
                         drawn from the range [0, NUM_NODES-1])
  MIN_SOURCES_PER_APP  - minimum number of distinct source nodes per app
  MAX_SOURCES_PER_APP  - maximum number of distinct source nodes per app
  LAMBDA_RANGE         - (min, max) Poisson arrival rate for each source
  SEED                 - integer for reproducibility (only used when RANDOMISE=False)
  OUTPUT_FILE          - path of the JSON file to write
"""

import json
import random
from pathlib import Path

# ── CONFIG ─────────────────────────────────────────────────────────────────
RANDOMISE           = False   # True  -> different output every run (ignores SEED)
                              # False -> reproducible output using SEED
NUM_APPS            = 5       # should match the number of apps in the app definition
NUM_NODES           = 100     # total nodes in the network (IDs: 0 .. NUM_NODES-1)
MIN_SOURCES_PER_APP = 1       # minimum distinct source nodes per app
MAX_SOURCES_PER_APP = 5       # maximum distinct source nodes per app
LAMBDA_RANGE        = (100, 1000)  # (min, max) Poisson arrival rate per source
SEED                = 42
OUTPUT_FILE         = Path(__file__).parent / "MYdynamicUsersDefinition.json"
# ───────────────────────────────────────────────────────────────────────────


def build_sources_for_app(app_idx: int) -> list:
    """
    Generate a list of source entries for a single application.

    A random subset of unique network nodes is chosen; each node gets
    its own independent lambda (arrival rate).  The entry message name
    follows the convention used across all YAFS examples:
    'M.USER.APP.<app_idx>'.

    Returns a list of source dicts ready to be placed in "sources".
    """
    app_str  = str(app_idx)
    msg_name = f"M.USER.APP.{app_idx}"

    # Determine how many distinct nodes will generate traffic for this app.
    num_sources = random.randint(
        MIN_SOURCES_PER_APP,
        min(MAX_SOURCES_PER_APP, NUM_NODES),  # can't exceed available nodes
    )

    # Draw unique node IDs so no node appears twice for the same app.
    node_ids = random.sample(range(NUM_NODES), num_sources)

    sources = []
    for node_id in sorted(node_ids):  # sorted for deterministic JSON ordering
        sources.append(
            {
                "id_resource": node_id,
                "app":         app_str,
                "message":     msg_name,
                "lambda":      random.randint(*LAMBDA_RANGE),
            }
        )

    return sources


if __name__ == "__main__":
    # Apply seed based on RANDOMISE flag.
    if RANDOMISE:
        random.seed(None)   # different result every run
        print("Mode: RANDOM (no fixed seed)")
    else:
        random.seed(SEED)
        print(f"Mode: REPRODUCIBLE (seed={SEED})")

    # Collect all source entries across every application.
    all_sources = []
    for app_id in range(NUM_APPS):
        entries = build_sources_for_app(app_id)
        all_sources.extend(entries)

    # Wrap in the top-level structure expected by YAFS.
    population = {"sources": all_sources}

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(population, f, indent=4)

    print(f"Generated {NUM_APPS} apps -> {OUTPUT_FILE}")
    # Per-app summary for quick inspection.
    for app_id in range(NUM_APPS):
        app_entries = [s for s in all_sources if s["app"] == str(app_id)]
        lambdas     = [s["lambda"] for s in app_entries]
        print(
            f"  App {app_id:>2}: "
            f"{len(app_entries)} source(s), "
            f"lambda range [{min(lambdas)}, {max(lambdas)}]"
        )
