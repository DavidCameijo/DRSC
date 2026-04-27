"""
    Intermediate Phase - DSRC Project
    Barabasi-Albert topology (50 nodes), 5 applications, 
    MinimizeExecutionTime placement + MinimizeLatency routing,
    Exponential distribution (lambd=4), seed=42.

    @author: Isaac Lera (modified)
"""
import os
import time
import json
import random
import logging.config

import networkx as nx
from pathlib import Path
import matplotlib.pyplot as plt

import pandas as pd
import numpy as np

from yafs.core import Sim
from yafs.application import create_applications_from_json
from yafs.topology import Topology

from yafs.placement import JSONPlacement
from yafs.path_routing import DeviceSpeedAwareRouting
from yafs.distribution import deterministic_distribution, exponential_distribution
from yafs.placement import Placement
from yafs.selection import Selection

# Sink node assigned to each app (nodes 39-43, within the 39-48 sink range)
APP_SINK_NODES = {
    "App0": 39,
    "App1": 40,
    "App2": 41,
    "App3": 42,
    "App4": 43
}

class MinimizeExecutionTimePlacement(Placement):
    def __init__(self, name, **kwargs):
        super(MinimizeExecutionTimePlacement, self).__init__(name, **kwargs)

    def initial_allocation(self, sim, app_name):
        # Find the node with the highest IPT (Cloud node 49)
        
        best_compute_node = None
        max_ipt = -1
        for node in sim.topology.G.nodes():
            ipt = sim.topology.G.nodes[node].get('IPT', 0)
            if ipt > max_ipt:
                max_ipt = ipt
                best_compute_node = node

        # Each app gets its own dedicated sink node
        sink_node = APP_SINK_NODES.get(app_name, 39)

        app = sim.apps[app_name]
        for module in app.services:
            if module == "Sink":
                # Sinks go to their designated node (39-43)
                sim.deploy_module(app_name, module, app.services[module], [sink_node])
            elif module == "Source":
                # Sources are handled by deploy_source
                continue
            else:
                # COMP modules go to the fastest node (Cloud, node 49)
                sim.deploy_module(app_name, module, app.services[module], [best_compute_node])


class MinimizeLatencyRouting(Selection):
    def get_path(self, sim, app_name, message, topology_src, alloc_DES, alloc_module, traffic, from_des):
        node_src = topology_src
        DES_dst = alloc_module[app_name][message.dst]

        best_path = []
        best_des = None
        min_latency = 1000000000

        for des in DES_dst:
            node_dst = alloc_DES[des]
            try:
                # Use PR (propagation delay) as latency weight
                path = nx.shortest_path(sim.topology.G, source=node_src, target=node_dst, weight='PR')
                latency = nx.shortest_path_length(sim.topology.G, source=node_src, target=node_dst, weight='PR')
                if latency < min_latency:
                    min_latency = latency
                    best_path = path
                    best_des = des
            except nx.NetworkXNoPath:
                continue

        if best_path:
            return [best_path], [best_des]
        return [], []

    def get_path_from_failure(self, sim, message, link, alloc_DES, alloc_module, traffic, ctime, from_des):
        idx = message.path.index(link[0])
        if idx == len(message.path):
            return [], []
        node_src = message.path[idx]
        path, des = self.get_path(sim, message.app_name, message, node_src, alloc_DES, alloc_module, traffic, from_des)
        if len(path) > 0 and len(path[0]) > 0:
            concPath = message.path[0:message.path.index(path[0][0])] + path[0]
            return [concPath], des
        return [], []


def main(stop_time, it, folder_results):

    """
    TOPOLOGY
    """
    t = Topology()

    # Barabasi-Albert graph: 50 nodes, m=1 for ~49 edges (closest to spec's 25-edge target)
    size = 50
    t.G = nx.generators.barabasi_albert_graph(size, m=1, seed=42)

    # Edge attributes
    attPR = {x: 2 for x in t.G.edges()}
    attBW = {x: 75000 for x in t.G.edges()}
    nx.set_edge_attributes(t.G, name="PR", values=attPR)
    nx.set_edge_attributes(t.G, name="BW", values=attBW)

    # Node attributes
    attIPT = {}
    attRAM = {}
    for x in t.G.nodes():
        if 0 <= x <= 4:
            # GW nodes - no compute capability
            attIPT[x] = 0
            attRAM[x] = 0
        elif 5 <= x <= 48:
            # Fog nodes (39-48 are sink-eligible)
            attRAM[x] = 8192
            attIPT[x] = 1000
        elif x == 49:
            # Cloud node - effectively infinite resources
            attIPT[x] = 1000000000
            attRAM[x] = 1000000000

    nx.set_node_attributes(t.G, name="IPT", values=attIPT)
    nx.set_node_attributes(t.G, name="RAM", values=attRAM)

    nx.write_gexf(t.G, folder_results + "graph_binomial_tree_%i.gexf" % size)
    print(t.G.nodes())

    # Plot the topology
    pos = nx.spring_layout(t.G, seed=42)
    nx.draw_networkx(t.G, pos, with_labels=True)
    nx.draw_networkx_edge_labels(t.G, pos, alpha=0.5, font_size=5, verticalalignment="top")
    plt.axis('off')
    plt.savefig(folder_results + "topology.png")
    plt.show()

    """
    APPLICATIONS
    """
    data_folder = os.path.join(os.path.dirname(__file__), 'data')
    dataApp = json.load(open(os.path.join(data_folder, 'appDefinition3.json')))
    apps = create_applications_from_json(dataApp)

    """
    PLACEMENT
    """
    placement = MinimizeExecutionTimePlacement(name="Placement")

    """
    ROUTING
    """
    selectorPath = MinimizeLatencyRouting()

    """
    SIMULATION ENGINE
    """
    s = Sim(t, default_results_path=folder_results + "sim_trace")

    """
    Deploy apps
    """
    for aName in apps.keys():
        s.deploy_app(apps[aName], placement, selectorPath)

    """
    Deploy users (one source per GW node, one per app)
    """
    userJSON = json.load(open(os.path.join(data_folder, 'usersDefinition2.json')))
    for user in userJSON["sources"]:
        app_name = user["app"]
        if app_name in apps:
            app = s.apps[app_name]
            msg = app.get_message(user["message"])
            node = user["id_resource"]
            dist = exponential_distribution(name="Exp", lambd=4)
            s.deploy_source(app_name, id_node=node, msg=msg, distribution=dist)
        else:
            print(f"Error: App {app_name} not found in simulator!")

    """
    RUN
    """
    logging.info(" Performing simulation: %i " % it)
    s.run(stop_time)
    s.print_debug_assignaments()


if __name__ == '__main__':
    LOGGING_CONFIG = Path(__file__).parent / 'logging.ini'
    logging.config.fileConfig(LOGGING_CONFIG)

    folder_results = Path("results/")
    folder_results.mkdir(parents=True, exist_ok=True)
    folder_results = str(folder_results) + "/"

    simulationDuration = 20000

    random.seed(42)
    logging.info("Running experiment it: - %i" % 42)

    start_time = time.time()
    main(stop_time=simulationDuration, it=0, folder_results=folder_results)

    print("\n--- %s seconds ---" % (time.time() - start_time))
    print("Simulation Done!")

    # -----------------------
    # RESULTS ANALYSIS
    # -----------------------
    dfl = pd.read_csv(folder_results + "sim_trace" + "_link.csv")
    print("Number of total messages between nodes: %i" % len(dfl))

    df = pd.read_csv(folder_results + "sim_trace.csv")
    print("Number of requests handled by deployed services: %i" % len(df))

    # Per-app breakdown example (App2)
    dfapp2 = df[df.app == 2].copy()
    print(dfapp2.head())
    dfapp2["latency"] = dfapp2["time_reception"] - dfapp2["time_emit"]     
    dfapp2["service_time"] = dfapp2["time_out"] - dfapp2["time_in"]        
    print("Average service time of App2: %0.3f " % dfapp2["service_time"].mean())
    print("App2 deployed on nodes: %s" % np.unique(dfapp2["TOPO.dst"]))
    print("Number of App2 instances: %s" % np.unique(dfapp2["DES.dst"]))

    # -----------------------
    # EVALUATION METRICS PLOTS
    # -----------------------
    print("\n--- Generating Evaluation Metrics Plots ---")

    # 1. Average latency per application
    df['total_latency'] = df['time_out'] - df['time_emit']
    avg_latency = df.groupby('app')['total_latency'].mean()
    plt.figure()
    avg_latency.plot(kind='bar', title='Average Latency per Application', ylabel='Latency (ms)')
    plt.tight_layout()
    plt.savefig(folder_results + "avg_latency_per_app.png")

    # 2. Physical link usage
    plt.figure()
    link_usage = dfl.groupby(['src', 'dst']).size()
    if len(link_usage) > 20:
        link_usage.sort_values(ascending=False).head(20).plot(kind='bar', title='Top 20 Physical Links Usage', ylabel='Messages')
    else:
        link_usage.plot(kind='bar', title='Physical Link Usage', ylabel='Messages')
    plt.tight_layout()
    plt.savefig(folder_results + "link_usage.png")

    # 3. Node usage
    plt.figure()
    node_usage = df.groupby('TOPO.dst').size()
    node_usage.plot(kind='bar', title='Node Usage (Task Allocations)', ylabel='Tasks Processed')
    plt.tight_layout()
    plt.savefig(folder_results + "node_usage.png")

    # 4. Bandwidth consumption per application
    plt.figure()
    if 'size' in dfl.columns:
        bw_app = dfl.groupby('app')['size'].sum()
        bw_app.plot(kind='bar', title='Bandwidth Consumption per App', ylabel='Total Bytes')
    else:
        dfl.groupby('app').size().plot(kind='bar', title='Bandwidth (Message Counts) per App', ylabel='Total Messages')
    plt.tight_layout()
    plt.savefig(folder_results + "bandwidth_per_app.png")

    # 5. CPU consumption per application
    plt.figure()
    if 'inst' in df.columns:
        cpu_app = df.groupby('app')['inst'].sum()
        cpu_app.plot(kind='bar', title='CPU (Instructions) Consumption per App', ylabel='Total Instructions')
    else:
        df.groupby('app').size().plot(kind='bar', title='CPU proxy (Requests) per App', ylabel='Total Requests')
    plt.tight_layout()
    plt.savefig(folder_results + "cpu_per_app.png")

    plt.show()