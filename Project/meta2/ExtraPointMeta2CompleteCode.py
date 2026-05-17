"""
    Final Phase - DSRC Project
    Two topologies, all 6 algorithms (3 routing x 2 placement x random),
    Uniform + Exponential distributions, complex app patterns, network failure.

    Topologies:
        - Topology 1: barabasi_albert - used the one from the intermediate phase as a baseline for comparison.
        - Topology 2: grid_2d_graph - used a 7x7 grid graph for the second topology.

    Authors: David Cameijo Pinheiro, Guilherme Fernandes Rodrigues
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
from yafs.distribution import deterministicDistributionStartPoint, exponential_distribution, uniformDistribution
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


def get_protected_nodes():
    """Nodes reserved for pure user sources/sinks in static wiring."""
    sources = set(APP_SRC_NODES.values())
    sinks = set()
    for app_sinks in APP_SINK_NODES.values():
        sinks.update(app_sinks.values())
    return sources.union(sinks)


def get_compute_nodes(topology, exclude_protected=True):
    """Return nodes that can execute modules safely (IPT > 0 and RAM > 0)."""
    protected = get_protected_nodes() if exclude_protected else set()
    return [
        n for n in topology.nodes()
        if n not in protected
        and topology.nodes[n].get('IPT', 0) > 0
        and topology.nodes[n].get('RAM', 0) > 0
    ]


# =============================================================================
# ROUTING ALGORITHMS
# =============================================================================

class MinimizeLatencyRouting(Selection):
    """
    Selects the path with the lowest total processing latency (PR) from source to destination.
    Uses Dijkstra's algorithm via networkx's shortest_path functions.
    """
    def get_path(self, sim, app_name, message, topology_src,
                 alloc_DES, alloc_module, traffic, from_des):
        node_src = topology_src

        if app_name not in alloc_module or message.dst not in alloc_module[app_name]:
            return [], []

        DES_dst = alloc_module[app_name][message.dst]
        best_path, best_des, min_lat = [], None, float('inf')

        for des in DES_dst:
            if des not in alloc_DES:
                continue

            node_dst = alloc_DES[des]
            try:
                lat = nx.shortest_path_length(
                    sim.topology.G, source=node_src, target=node_dst, weight='PR')
                
                if lat < min_lat:
                    min_lat = lat
                    best_path = nx.shortest_path(
                        sim.topology.G, source=node_src, target=node_dst, weight='PR')
                    best_des = des
            except (nx.NetworkXNoPath, nx.NodeNotFound):
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
            message.dst_int = -1
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

        if app_name not in alloc_module or message.dst not in alloc_module[app_name]:
            return [], []

        for u, v, data in sim.topology.G.edges(data=True):
            bw = data.get('BW', 1)
            data['inv_BW'] = 1.0 / bw if bw > 0 else float('inf')

        DES_dst = alloc_module[app_name][message.dst]
        best_path, best_des, min_cost = [], None, float('inf')

        for des in DES_dst:
            node_dst = alloc_DES[des]
            try:
                cost = nx.shortest_path_length(
                    sim.topology.G, source=node_src, target=node_dst, weight='inv_BW')
                if cost < min_cost:
                    min_cost = cost
                    best_path = nx.shortest_path(
                        sim.topology.G, source=node_src, target=node_dst, weight='inv_BW')
                    best_des = des
            except (nx.NetworkXNoPath, nx.NodeNotFound):
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
            concat = message.path[:idx] + path[0]
            message.dst_int = -1
            return [concat], des
        return [], []


class RandomPathRouting(Selection):
    """
    Selects a completely random valid simple path between source and destination.
    Uses nx.all_simple_paths with a cutoff to avoid exponential blowup.
    """

    def get_path(self, sim, app_name, message, topology_src,
                 alloc_DES, alloc_module, traffic, from_des):
        
        if app_name not in alloc_module or message.dst not in alloc_module[app_name]:
            return [], []

        DES_dst = alloc_module[app_name][message.dst]
        des = random.choice(DES_dst)
        node_dst = alloc_DES[des]

        
        try: 
            for u,v, d in sim.topology.G.edges(data=True):
                d['rand_weigth'] = random.random()

            path = nx.shortest_path(sim.topology.G, source=topology_src, target=node_dst, weight='rand_weigth')
            return [path], [des]
        
        except (IndexError, nx.NetworkXNoPath, nx.NodeNotFound):
            return [], []

    def get_path_from_failure(self, sim, message, link,
                              alloc_DES, alloc_module, traffic, ctime, from_des):
        idx = message.path.index(link[0])
        if idx == len(message.path) - 1:
            return [], []
        node_src = message.path[idx]
        path, des = self.get_path(sim, message.app_name, message, node_src,
                                  alloc_DES, alloc_module, traffic, from_des)
        
        if path and path[0]:
            concat = message.path[:idx] + path[0]
            message.dst_int = -1
            return [concat],des
        return [], []


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
        app = sim.apps[app_name]
        topology = sim.topology.G
        
        fog_nodes = [n for n in topology.nodes() if 5 <= n <= 47]

        for service_name in app.services:
            if "Source" not in service_name and "Sink" not in service_name:
                best_node = max(fog_nodes, key=lambda n: topology.nodes[n].get('RAM', 0))
                sim.deploy_module(app_name, service_name, app.services[service_name], [best_node])


class RandomNodePlacement(Placement):
    """
    Places each module on a completely random node in the topology.
    Baseline / lower-bound strategy for comparison.
    """

    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)

    def initial_allocation(self, sim, app_name):
        nodes = get_compute_nodes(sim.topology.G, exclude_protected=True)
        if not nodes:
            nodes = get_compute_nodes(sim.topology.G, exclude_protected=False)
        if not nodes:
            raise RuntimeError("No valid compute nodes available for RandomNodePlacement")

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
                self.deploy_module(app_name, module, application.services[module], [cloud_node])
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
                        self.initial_allocation(sim, app_name, module, node)
                        placed = True
                        break
                if not placed:
                    self.initial_allocation(sim, app_name, module, 49)  # Fallback to cloud if no edge node has enough RAM
                

# =============================================================================
# NETWORK FAILURE
# =============================================================================
"""
Class used in Exercise2 to generate a link failure at a specific time interval.
"""
class LinkFailure():
    def __init__(self, target_time, target_node):
        self.target_time = target_time
        self.target_node = target_node
        self.triggered = False

    def __call__(self, sim, routing):
        if sim.env.now >= self.target_time and not self.triggered:
            if self.target_node in sim.topology.G:
                sim.topology.G.remove_node(self.target_node)
                
                routing.invalid_cache_value = True
            else:
                pass
            
            self.triggered = True


def select_failure_node(topology, fixed_node=None):
    """
    Selects a valid failure node for the given topology.

    If fixed_node is provided but unavailable in this topology, it falls back to
    a valid candidate and logs a warning.
    """
    protected_nodes = get_protected_nodes()

    if fixed_node is not None:
        if fixed_node in topology.G and fixed_node not in protected_nodes:
            return fixed_node
        logging.warning(
            f"[FAILURE NODE INVALID] Requested node {fixed_node} is not valid for this topology. "
            "Selecting a fallback node."
        )

    # Prefer non-protected, compute-capable nodes.
    candidate_nodes = [
        n for n in topology.G.nodes()
        if n not in protected_nodes and topology.G.nodes[n].get('RAM', 0) > 0
    ]

    if candidate_nodes:
        # Prefer lower-degree nodes to reduce rerouting shock in highly dynamic policies.
        return min(candidate_nodes, key=lambda n: topology.G.degree(n))

    remaining = [n for n in topology.G.nodes() if n not in protected_nodes]
    if remaining:
        return min(remaining, key=lambda n: topology.G.degree(n))

    raise RuntimeError("No valid node available to inject failure in this topology")

class DynamicSourceMutation():
    """
    Extra credit: Dynamically changes the source node of an application at a specified time.
    """
    def __init__(self, target_time, app_name):
        self.target_time = target_time
        self.app_name = app_name
        self.triggered = False

    def __call__(self, sim, routing):
        if sim.env.now >= self.target_time and not self.triggered:
            # Select a new source node that is not currently used as a protected node (source/sink) and has compute capacity
            valid_nodes = get_compute_nodes(sim.topology.G, exclude_protected=False)
            if not valid_nodes:
                return
                
            new_source = random.choice(valid_nodes)
            old_source = APP_SRC_NODES[self.app_name]
            
            APP_SRC_NODES[self.app_name] = new_source
            
            # Invalidate routing caches to force re-evaluation of paths with the new source
            routing.invalid_cache_value = True
            logging.info(f"\n[EXTRA CREDIT] Traffic of {self.app_name} changed from Source {old_source} to Source {new_source} at t={sim.env.now}")
            
            self.triggered = True

# =============================================================================
# TOPOLOGY BUILDERS
# =============================================================================

def build_topology_meta1(seed=42):
    """
    Topology 1: Barabási-Albert (50 nodes, m=25)
    Dense scale-free graph — same as intermediate phase.
    Used as baseline for comparison.
    """
    t = Topology()
    size = 50
    t.G = nx.barabasi_albert_graph(size, m=25, seed=seed)

    nx.set_edge_attributes(t.G, name="PR", values={e: 2     for e in t.G.edges()})
    nx.set_edge_attributes(t.G, name="BW", values={e: 75000 for e in t.G.edges()})

    ipt, ram = {}, {}
    for x in t.G.nodes():
        if x <= 4:
            ipt[x], ram[x] = 0, 0
        elif x <= 48:
            ipt[x], ram[x] = 1000, 8192
        else:
            ipt[x], ram[x] = 100000000, 1000000000

    nx.set_node_attributes(t.G, name="IPT", values=ipt)
    nx.set_node_attributes(t.G, name="RAM", values=ram)
    return t

def build_topology_2(seed=42):
    """
    Topology 2: Grid graph (7x7) as we have 49 nodes
    Assign IPT, RAM, PR, BW attributes to nodes/edges.

    Returns:
        t (Topology): configured YAFS Topology object
    """
    t = Topology()

    t.G = nx.grid_2d_graph(7, 7)

    t.G = nx.convert_node_labels_to_integers(t.G)

    nx.set_edge_attributes(t.G, name="PR", values={e: 2 for e in t.G.edges()})
    nx.set_edge_attributes(t.G, name="BW", values={e: 75000 for e in t.G.edges()})

    for n in t.G.nodes():
        if n <= 4:
            t.G.nodes[n]['IPT'] = 0
            t.G.nodes[n]['RAM'] = 0
        elif n == 48:
            t.G.nodes[n]['IPT'] = 1000000
            t.G.nodes[n]['RAM'] = 1000000
        else:
            t.G.nodes[n]['IPT'] = 1000
            t.G.nodes[n]['RAM'] = 8192
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
        return uniformDistribution(name=f"Uni_{app_name}", min=low, max=high)
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

        sinks_map = APP_SINK_NODES.get(aName, {})
        for sink_module, node_id in sinks_map.items():
            s.deploy_sink(aName, node=node_id, module=sink_module)
            print(f"[OK] {aName}: src={APP_SRC_NODES[aName]}, "
            f"sink={APP_SINK_NODES[aName]}, dist={dist_type}")

    # Inject failure
    if inject_node_failure:
        failure_node = select_failure_node(topology, fixed_node=failure_node)

        dist_fail = deterministicDistributionStartPoint(failure_time, failure_time/2.0, name="DeterministicFailure")
        evol_fail = LinkFailure(target_time=failure_time, target_node=failure_node)

        dist_mut = deterministicDistributionStartPoint(failure_time, failure_time/2.0, name="DeterministicMutation")
        evol_mut = DynamicSourceMutation(target_time=12000, app_name=list(apps.keys())[0])  # Change source of the first app at t=12000

        s.deploy_monitor("SourceMutation", evol_mut, dist_mut, **{"sim": s, "routing": selectorPath})
        s.deploy_monitor("NodeFailureTopology", evol_fail, dist_fail, **{"sim": s, "routing": selectorPath})

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
    topo1 = build_topology_meta1(seed=42)
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
        (build_topology_meta1, "topo1", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "exponential"),
        (build_topology_meta1, "topo1", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "uniform"),
        (build_topology_meta1, "topo1", MinimizeExecutionTimePlacement, MaximizeBandwidthRouting,  "exponential"),
        (build_topology_meta1, "topo1", MinimizeResourceUsagePlacement, MinimizeLatencyRouting,    "exponential"),
        (build_topology_meta1, "topo1", RandomNodePlacement,            RandomPathRouting,         "exponential"),
        #~ --- Topology 2 ---
        (build_topology_2, "topo2", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "exponential"),
        (build_topology_2, "topo2", MinimizeExecutionTimePlacement, MinimizeLatencyRouting,    "uniform"),
        (build_topology_2, "topo2", MinimizeExecutionTimePlacement, MaximizeBandwidthRouting,  "exponential"),
        (build_topology_2, "topo2", MinimizeResourceUsagePlacement, MinimizeLatencyRouting,    "exponential"),
        (build_topology_2, "topo2", RandomNodePlacement,            RandomPathRouting,         "exponential"),
        
    ]

    for i, (topo_func, topo_label, placement_cls, routing_cls, dist_type) in enumerate(experiments):
        

        exp_label = f"{topo_label}_{placement_cls.__name__}_{routing_cls.__name__}_{dist_type}"
        exp_folder = folder_results + exp_label + "/"
        Path(exp_folder).mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"Experiment {i+1}/{len(experiments)}: {exp_label}")
        print(f"{'='*60}")

        current_topo = topo_func()

        start = time.time()

        run_simulation(
            topology=current_topo,
            apps=apps,
            placement_cls=placement_cls,
            routing_cls=routing_cls,
            dist_type=dist_type,
            stop_time=STOP_TIME,
            folder_results=exp_folder,
            inject_node_failure=True,
            failure_time=10000,  
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