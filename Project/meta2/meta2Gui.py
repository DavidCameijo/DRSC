"""
    Final Phase - DSRC Project
    Two topologies, all 6 algorithms (3 routing x 2 placement x random),
    Uniform + Exponential distributions, complex app patterns, network failure.

    Topologies:
        - Topology 1: TODO - choose and justify
        - Topology 2: TODO - choose and justify

    Authors: TODO
"""

import os
import time
import json
import random
import logging
import logging.config
import warnings

import networkx as nx
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from yafs.core import Sim
from yafs.application import create_applications_from_json
from yafs.topology import Topology
from yafs.distribution import exponential_distribution, uniform_distribution
from yafs.placement import Placement
from yafs.selection import Selection


# =============================================================================
# STATIC APP WIRING — update to match your final app definitions
# =============================================================================

APP_SRC_NODES = {
    "App0": 0,
    "App1": 1,
    "App2": 2,
    "App3": 3,
    "App4": 4,
}

APP_SINK_NODES = {
    "App0": {"Sink1": 39, "Sink2": 40},
    "App1": {"Sink1": 41, "Sink2": 42},
    "App2": {"Sink1": 43, "Sink2": 44},
    "App3": {"Sink1": 45, "Sink2": 46},
    "App4": {"Sink1": 47, "Sink2": 48},
}


# =============================================================================
# ROUTING ALGORITHMS
# =============================================================================

class MinimizeLatencyRouting(Selection):
    def get_path(self, sim, app_name, message, topology_src,
                 alloc_DES, alloc_module, traffic, from_des):
        node_src = topology_src

        if message.dst not in alloc_module[app_name]:
            return [], []

        DES_dst = alloc_module[app_name][message.dst]
        best_path, best_des, min_lat = [], None, float('inf')

        for des in DES_dst:
            node_dst = alloc_DES[des]
            try:
                lat = nx.shortest_path_length(
                    sim.topology.G, source=node_src, target=node_dst, weight='PR')
                if lat < min_lat:
                    min_lat = lat
                    best_path = nx.shortest_path(
                        sim.topology.G, source=node_src, target=node_dst, weight='PR')
                    best_des = des
            except nx.NetworkXNoPath:
                continue

        return ([best_path], [best_des]) if best_path else ([], [])

    def get_path_from_failure(self, sim, message, link,
                              alloc_DES, alloc_module, traffic, ctime, from_des):
        idx = message.path.index(link[0])
        if idx == len(message.path) - 1:
            return [], []
        node_src = message.path[idx]
        path, des = self.get_path(sim, message.app_name, message, node_src,
                                  alloc_DES, alloc_module, traffic, from_des)
        if path and path[0]:
            concat = message.path[:message.path.index(path[0][0])] + path[0]
            return [concat], des
        return [], []



class MaximizeBandwidthRouting(Selection):
    """
    Selects the path that maximises available bandwidth.
    Since nx.shortest_path minimises cost, bandwidth is inverted (1/BW)
    so that higher bandwidth links have lower cost.
    """

    def get_path(self, sim, app_name, message, topology_src,
                 alloc_DES, alloc_module, traffic, from_des):
        
        node_src = topology_src

        if message.dst not in alloc_module[app_name]:
            return [], []
        

        DES_dst = alloc_module[app_name].get(message.dst, [])

        best_path, best_dest, max_bw =[], None , -float('inf')

        for u,v in sim.topology.G.edges():
            

        # TODO: implement
        # Hint: set edge attribute 'inv_BW' = 1/BW for each edge,
        #       then use nx.shortest_path(..., weight='inv_BW')
        
        
            raise NotImplementedError

    def get_path_from_failure(self, sim, message, link,
                              alloc_DES, alloc_module, traffic, ctime, from_des):
        # TODO: implement (same pattern as MinimizeLatencyRouting)
        raise NotImplementedError


class RandomPathRouting(Selection):
    """
    Selects a completely random valid simple path between source and destination.
    Uses nx.all_simple_paths with a cutoff to avoid exponential blowup.
    """

    def get_path(self, sim, app_name, message, topology_src,
                 alloc_DES, alloc_module, traffic, from_des):
        # TODO: implement
        # Hint: use nx.all_simple_paths(..., cutoff=8), then random.choice()
        raise NotImplementedError

    def get_path_from_failure(self, sim, message, link,
                              alloc_DES, alloc_module, traffic, ctime, from_des):
        # TODO: implement
        raise NotImplementedError


# =============================================================================
# PLACEMENT ALGORITHMS
# =============================================================================

class MinimizeExecutionTimePlacement(Placement):
    def __init__(self, name, **kwargs):
        super(MinimizeExecutionTimePlacement, self).__init__(name, **kwargs)

    def initial_allocation(self, sim, app_name):
        best_compute_node = max(
            sim.topology.G.nodes(),
            key=lambda n: sim.topology.G.nodes[n].get('IPT', 0)
        )
        app = sim.apps[app_name]
        for module in app.services:
            sim.deploy_module(app_name, module, app.services[module], [best_compute_node])


class MinimizeResourceUsagePlacement(Placement):
    """
    Places each module on the node with the least combined CPU + RAM usage
    along the selected path. Encourages load spreading across Fog nodes.
    """

    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)

    def initial_allocation(self, sim, app_name):
        best_compute_node = min(
            sim.topology.G.nodes(),
            key=lambda n: sim.topology.G.nodes[n].get('CPU_usage', 0) + sim.topology.G.nodes[n].get('RAM_usage', 0)
        )
        app = sim.apps[app_name]
        for module in app.services:
            sim.deploy_module(app_name, module, app.services[module], [best_compute_node])


class RandomNodePlacement(Placement):
    """
    Places each module on a completely random node in the topology.
    Baseline / lower-bound strategy for comparison.
    """

    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)

    def initial_allocation(self, sim, app_name):
        nodes = list(sim.topology.G.nodes())
        app = sim.apps[app_name]
        for module in app.services:
            chosen_node = random.choice(nodes)
            sim.deploy_module(app_name, module, app.services[module], [chosen_node])

class CloudPlacement(Placement):
    """
    Places each module on a cloud node.
    They go search for the node with the highest RAM capacity and place all modules there, in this case is node 49
    """
    def initial_allocation(self, sim, app_name):
        cloud_node = 49
        application = sim.apps[app_name]
        for module in application.services:
            if module not in ["Source", "Sink"]:
                self.set_initial_allocation(sim, app_name, module, cloud_node)

class EdgePlacement(Placement):
    """
    Places each module on an edge node.
    """
    def initial_allocation(self, sim, app_name):
        source_node = APP_SRC_NODES[app_name]
        application = sim.apps[app_name]
        topology = sim.topology.G

        for module in application.services:
            if module not in ["Source", "Sink"]:
                nodes_by_proximity = sorted(topology.nodes(), key=lambda n: nx.shortest_path_length(topology, source=source_node, target=n))
                placed = False
                for node in nodes_by_proximity:
                    if node != 49 and topology.nodes[node].get('RAM', 0) > 100:
                        self.set_initial_allocation(sim, app_name, module, node)
                        placed = True
                        break
                if not placed:
                    self.set_initial_allocation(sim, app_name, module, 49)  # Fallback to cloud if no edge node has enough RAM
                

# =============================================================================
# NETWORK FAILURE
# =============================================================================

def inject_failure(sim, target_node, fail_time):
    """
    Removes a node (and all its links) from the topology at fail_time.
    Registered as a SimPy process before s.run().

    Args:
        sim:         the Sim instance
        target_node: node ID to remove (pick a high-degree hub for impact)
        fail_time:   simulation time at which failure occurs
    """
    # TODO: implement
    # Hint:
    #   yield sim.env.timeout(fail_time)
    #   sim.topology.G.remove_node(target_node)
    #   logging.info(f"[FAILURE] Node {target_node} removed at t={fail_time}")
    raise NotImplementedError


# =============================================================================
# TOPOLOGY BUILDERS
# =============================================================================

def build_topology_1(seed=42):
    """
    Topology 1: TODO — choose a NetworkX generator and justify the choice.
    Assign IPT, RAM, PR, BW attributes to nodes/edges.

    Returns:
        t (Topology): configured YAFS Topology object
    """
    t = Topology()

    # TODO: generate graph, e.g.:
    # t.G = nx.erdos_renyi_graph(n=50, p=0.1, seed=seed)

    # TODO: set edge attributes (PR, BW)
    # nx.set_edge_attributes(t.G, name="PR", values={e: ? for e in t.G.edges()})
    # nx.set_edge_attributes(t.G, name="BW", values={e: ? for e in t.G.edges()})

    # TODO: set node attributes (IPT, RAM) per node role
    # ipt, ram = {}, {}
    # for n in t.G.nodes():
    #     ...
    # nx.set_node_attributes(t.G, name="IPT", values=ipt)
    # nx.set_node_attributes(t.G, name="RAM", values=ram)

    raise NotImplementedError
    return t


def build_topology_2(seed=42):
    """
    Topology 2: TODO — choose a different NetworkX generator.
    Must differ structurally from Topology 1 (e.g. sparse vs. dense,
    random vs. small-world, etc.)

    Returns:
        t (Topology): configured YAFS Topology object
    """
    t = Topology()

    # TODO: generate graph, e.g.:
    # t.G = nx.watts_strogatz_graph(n=50, k=6, p=0.3, seed=seed)

    # TODO: set edge and node attributes

    raise NotImplementedError
    return t


def plot_topology(G, folder, name, seed=42):
    """Saves a visual PNG of the topology with colour-coded node roles."""
    pos = nx.spring_layout(G, seed=seed)
    app_colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0']
    node_colors = []
    for x in G.nodes():
        if x in APP_SRC_NODES.values():
            idx = list(APP_SRC_NODES.values()).index(x)
            node_colors.append(app_colors[idx % len(app_colors)])
        elif x in APP_SINK_NODES.values():
            node_colors.append('lightcoral')
        else:
            # colour by degree to visualise hub structure
            node_colors.append('gold' if G.degree(x) > np.percentile(
                [G.degree(n) for n in G.nodes()], 80) else 'darkgray')

    plt.figure(figsize=(12, 8))
    nx.draw_networkx(G, pos, with_labels=True,
                     node_color=node_colors, node_size=300, font_size=7)
    plt.axis('off')
    plt.title(f"Topology: {name}")
    plt.tight_layout()
    plt.savefig(folder + f"topology_{name}.png")
    plt.close()
    print(f"[PLOT] Topology saved: topology_{name}.png")


# =============================================================================
# APPLICATION LOADER
# =============================================================================

def load_applications(data_folder):
    """
    Loads application definitions from JSON.
    For the final phase, define complex app patterns (fork/join, parallel
    branches) in the JSON files — not just linear COMP1 -> COMP2 chains.
    """
    # TODO: update JSON filename(s) to match your final app definitions
    dataApp = json.load(open(os.path.join(data_folder, 'appDefinition_final.json')))
    apps = create_applications_from_json(dataApp)
    for name, app in apps.items():
        print(f"App loaded: {name} | Messages: {list(app.messages.keys())}")
    return apps


# =============================================================================
# DISTRIBUTION FACTORY
# =============================================================================

def get_distribution(dist_type, app_name, lambd=4, low=1, high=5):
    """
    Returns a YAFS distribution object.

    Args:
        dist_type: 'exponential' or 'uniform'
        app_name:  used to name the distribution instance
        lambd:     rate parameter for exponential
        low/high:  bounds for uniform
    """
    if dist_type == 'exponential':
        return exponential_distribution(name=f"Exp_{app_name}", lambd=lambd)
    elif dist_type == 'uniform':
        return uniform_distribution(name=f"Uni_{app_name}", min=low, max=high)
    else:
        raise ValueError(f"Unknown distribution type: {dist_type}")


# =============================================================================
# MAIN SIMULATION RUNNER
# =============================================================================

def run_simulation(topology, apps, placement_cls, routing_cls,
                   dist_type, stop_time, folder_results,
                   inject_node_failure=True, failure_node=None, failure_time=5000):
    """
    Configures and runs one simulation experiment.

    Args:
        topology:            YAFS Topology object
        apps:                dict of Application objects
        placement_cls:       Placement subclass (not instance)
        routing_cls:         Selection subclass (not instance)
        dist_type:           'exponential' or 'uniform'
        stop_time:           simulation end time
        folder_results:      output folder path string
        inject_node_failure: whether to inject a node failure
        failure_node:        node ID to remove (default: highest-degree node)
        failure_time:        simulation time of the failure event
    """
    s = Sim(topology, default_results_path=folder_results + "sim_trace")
    selectorPath = routing_cls()

    for aName in apps.keys():
        app = apps[aName]
        placement = placement_cls(name=f"Placement_{aName}")

        s.deploy_app(app, placement, selectorPath)
        placement.initial_allocation(s, aName)

        msg  = s.apps[aName].get_message("M.User")   # TODO: update message name
        dist = get_distribution(dist_type, aName)
        s.deploy_source(aName, id_node=APP_SRC_NODES[aName], msg=msg, distribution=dist)

        for sink_module in s.apps[aName].get_sink_modules():
            s.deploy_sink(aName, node=APP_SINK_NODES[aName], module=sink_module)

        print(f"[OK] {aName}: src={APP_SRC_NODES[aName]}, "
              f"sink={APP_SINK_NODES[aName]}, dist={dist_type}")

    # Inject failure
    if inject_node_failure:
        if failure_node is None:
            # Default: remove the highest-degree node (biggest hub)
            failure_node = max(topology.G.nodes(), key=lambda n: topology.G.degree(n))
        s.env.process(inject_failure(s, failure_node, failure_time))
        print(f"[FAILURE SCHEDULED] Node {failure_node} will fail at t={failure_time}")

    s.run(stop_time)
    s.print_debug_assignaments()


# =============================================================================
# RESULTS & PLOTS
# =============================================================================

def generate_plots(folder_results):
    """
    Reads sim_trace CSVs and produces all required evaluation metric plots.
    Mirrors the intermediate phase analysis — extend as needed.
    """
    dfl = pd.read_csv(folder_results + "sim_trace_link.csv")
    df  = pd.read_csv(folder_results + "sim_trace.csv")

    print(f"Link messages: {len(dfl)} | Service events: {len(df)}")

    # ------------------------------------------------------------------
    # 1. End-to-end latency per application
    # ------------------------------------------------------------------
    df_e2e = df.groupby(['app', 'id']).agg(
        start=('time_emit', 'min'),
        end=  ('time_out',  'max')
    ).reset_index()
    df_e2e['latency'] = df_e2e['end'] - df_e2e['start']
    avg_latency = df_e2e.groupby('app')['latency'].mean()
    print("Average latency per app:\n", avg_latency)

    if not avg_latency.empty:
        plt.figure()
        avg_latency.plot(kind='bar',
                         title='Average Latency per Application',
                         ylabel='Latency (sim time units)', xlabel='App')
        plt.tight_layout()
        plt.savefig(folder_results + "avg_latency_per_app.png")
        plt.close()

    # ------------------------------------------------------------------
    # 2. Physical link usage
    # ------------------------------------------------------------------
    if not dfl.empty:
        link_usage = dfl.groupby(['src', 'dst']).size().sort_values(ascending=False)
        plt.figure(figsize=(14, 5))
        (link_usage.head(20) if len(link_usage) > 20 else link_usage).plot(
            kind='bar', title='Top 20 Physical Links Usage', ylabel='Messages')
        plt.tight_layout()
        plt.savefig(folder_results + "link_usage.png")
        plt.close()

    # ------------------------------------------------------------------
    # 3. Node usage
    # ------------------------------------------------------------------
    if not df.empty:
        plt.figure()
        df.groupby('TOPO.dst').size().plot(
            kind='bar', title='Node Usage (Task Allocations)',
            ylabel='Tasks Processed', xlabel='Node ID')
        plt.tight_layout()
        plt.savefig(folder_results + "node_usage.png")
        plt.close()

    # ------------------------------------------------------------------
    # 4. Bandwidth consumption per application
    # ------------------------------------------------------------------
    if not dfl.empty:
        plt.figure()
        if 'size' in dfl.columns:
            dfl.groupby('app')['size'].sum().plot(
                kind='bar', title='Bandwidth Consumption per App',
                ylabel='Total Bytes', xlabel='App')
        else:
            dfl.groupby('app').size().plot(
                kind='bar', title='Bandwidth (Message Count) per App',
                ylabel='Messages', xlabel='App')
        plt.tight_layout()
        plt.savefig(folder_results + "bandwidth_per_app.png")
        plt.close()

    # ------------------------------------------------------------------
    # 5. CPU consumption per application
    # ------------------------------------------------------------------
    if not df.empty:
        plt.figure()
        if 'inst' in df.columns:
            df.groupby('app')['inst'].sum().plot(
                kind='bar', title='CPU (Instructions) per App',
                ylabel='Total Instructions', xlabel='App')
        else:
            df.groupby('app').size().plot(
                kind='bar', title='CPU Proxy (Requests) per App',
                ylabel='Total Requests', xlabel='App')
        plt.tight_layout()
        plt.savefig(folder_results + "cpu_per_app.png")
        plt.close()

    # ------------------------------------------------------------------
    # 6. RAM consumption per application
    # ------------------------------------------------------------------
    if not df.empty:
        if 'RAM' in df.columns:
            df.groupby('app')['RAM'].sum().plot(
                kind='bar', title='RAM Consumption per App',
                ylabel='Total RAM (MB)', xlabel='App', color='mediumpurple')
        else:
            # Fallback: module instance count as proxy
            ram_by_app_module = df.groupby(['app', 'module']).size().unstack(fill_value=0)
            plt.figure(figsize=(10, 6))
            ram_by_app_module.plot(kind='bar',
                                   title='RAM Proxy: Module Instances per App',
                                   ylabel='Module Instances', xlabel='App',
                                   rot=0)
            plt.legend(title='Module')
        plt.tight_layout()
        plt.savefig(folder_results + "ram_per_app.png")
        plt.close()

    print(f"[PLOTS] All plots saved to {folder_results}")


# =============================================================================
# EXPERIMENT ORCHESTRATOR
# =============================================================================

def main():
    folder_results = Path(__file__).parent / "results_final/"
    folder_results.mkdir(parents=True, exist_ok=True)
    folder_results = str(folder_results) + "/"

    data_folder = os.path.join(os.path.dirname(__file__), 'data')

    random.seed(42)
    np.random.seed(42)

    STOP_TIME = 20000

    # ------------------------------------------------------------------
    # Build topologies
    # ------------------------------------------------------------------
    topo1 = build_topology_1(seed=42)
    topo2 = build_topology_2(seed=42)
    plot_topology(topo1.G, folder_results, "topo1")
    plot_topology(topo2.G, folder_results, "topo2")

    # ------------------------------------------------------------------
    # Load applications
    # ------------------------------------------------------------------
    apps = load_applications(data_folder)

    # ------------------------------------------------------------------
    # Experiment matrix
    # Each tuple: (topology, topo_label, placement_cls, routing_cls, dist_type)
    # Expand or reduce this list as needed for your comparative analysis.
    # ------------------------------------------------------------------
    experiments = [
        # --- Topology 1 ---
        (topo1, "topo1", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "exponential"),
        (topo1, "topo1", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "uniform"),
        (topo1, "topo1", MinimizeExecutionTimePlacement, MaximizeBandwidthRouting,  "exponential"),
        (topo1, "topo1", MinimizeResourceUsagePlacement, MinimizeLatencyRouting,    "exponential"),
        (topo1, "topo1", RandomNodePlacement,            RandomPathRouting,         "exponential"),
        # --- Topology 2 ---
        (topo2, "topo2", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "exponential"),
        (topo2, "topo2", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "uniform"),
        (topo2, "topo2", MinimizeExecutionTimePlacement, MaximizeBandwidthRouting,  "exponential"),
        (topo2, "topo2", MinimizeResourceUsagePlacement, MinimizeLatencyRouting,    "exponential"),
        (topo2, "topo2", RandomNodePlacement,            RandomPathRouting,         "exponential"),
        # TODO: add more combinations as needed
    ]

    for i, (topo, topo_label, placement_cls, routing_cls, dist_type) in enumerate(experiments):
        exp_label = f"{topo_label}_{placement_cls.__name__}_{routing_cls.__name__}_{dist_type}"
        exp_folder = folder_results + exp_label + "/"
        Path(exp_folder).mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"Experiment {i+1}/{len(experiments)}: {exp_label}")
        print(f"{'='*60}")

        start = time.time()

        run_simulation(
            topology=topo,
            apps=apps,
            placement_cls=placement_cls,
            routing_cls=routing_cls,
            dist_type=dist_type,
            stop_time=STOP_TIME,
            folder_results=exp_folder,
            inject_node_failure=True,
            failure_time=10000,   # fail midway through the simulation
        )

        generate_plots(exp_folder)
        print(f"[DONE] Experiment {i+1} completed in {time.time()-start:.1f}s")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    LOGGING_CONFIG = Path(__file__).parent / 'logging.ini'
    if LOGGING_CONFIG.exists():
        logging.config.fileConfig(LOGGING_CONFIG)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.info("Starting Final Phase simulation")
    main()
    print("\nAll experiments complete.")