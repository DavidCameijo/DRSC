"""
    Intermediate Phase - DSRC Project
    Barabasi-Albert topology (50 nodes, m=25), 5 applications,
    MinimizeExecutionTime placement + MinimizeLatency routing,
    Exponential distribution (lambd=4), seed=42.
"""
import os
import time
import json
import random
import logging.config
import warnings

import networkx as nx
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from yafs.core import Sim
from yafs.application import create_applications_from_json
from yafs.topology import Topology
from yafs.distribution import exponential_distribution
from yafs.placement import Placement
from yafs.selection import Selection


APP_SINK_NODES = {
    "App0": {"Sink1": 39, "Sink2": 40},
    "App1": {"Sink1": 41, "Sink2": 42},
    "App2": {"Sink1": 43, "Sink2": 44},
    "App3": {"Sink1": 45, "Sink2": 46},
    "App4": {"Sink1": 47, "Sink2": 48},
}

APP_SRC_NODES = {
    "App0": 0,
    "App1": 1,
    "App2": 2,
    "App3": 3,
    "App4": 4,
}


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


def main(stop_time, it, folder_results):

    # ------------------------------------------------------------------
    # TOPOLOGY
    # ------------------------------------------------------------------
    t = Topology()
    size = 50
    t.G = nx.generators.barabasi_albert_graph(size, m=25, seed=42)

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
    nx.write_gexf(t.G, folder_results + "graph_ba_%i.gexf" % size)
    print("Nodes:", list(t.G.nodes()))
    print("Number of edges:", t.G.number_of_edges())

    # Plot topology
    pos = nx.spring_layout(t.G, seed=42)
    plt.figure(figsize=(12, 8))
    app_colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0']
    node_colors = []
    for x in t.G.nodes():
        if x <= 4:
            node_colors.append(app_colors[x])
        elif 39 <= x <= 48:
            node_colors.append(app_colors[(x - 39) // 2])
        elif x == 49:
            node_colors.append('gold')
        else:
            node_colors.append('darkgray')

    nx.draw_networkx(t.G, pos, with_labels=True,
                     node_color=node_colors, node_size=300, font_size=7)
    plt.axis('off')
    plt.title("Barabasi-Albert Topology (50 nodes, m=25)")
    plt.tight_layout()
    plt.savefig(folder_results + "topology.png")
    plt.close()

    # ------------------------------------------------------------------
    # APPLICATIONS
    # ------------------------------------------------------------------
    data_folder = os.path.join(os.path.dirname(__file__), 'data')
    dataApp = json.load(open(os.path.join(data_folder, 'appDefinition3.json')))
    apps = create_applications_from_json(dataApp)
    for name, app in apps.items():
        print(f"App loaded: {name} | Messages: {list(app.messages.keys())}")

    # ------------------------------------------------------------------
    # SIMULATION ENGINE
    # ------------------------------------------------------------------
    s = Sim(t, default_results_path=folder_results + "sim_trace")

    selectorPath = MinimizeLatencyRouting()

    # ------------------------------------------------------------------
    # DEPLOY: register app + placement + selector, then manually wire
    # sources and sinks using the 3-arg deploy_app (confirmed working)
    # ------------------------------------------------------------------
    for aName in apps.keys():
        app = apps[aName]
        placement = MinimizeExecutionTimePlacement(name="Placement_%s" % aName)

        # Register app, placement, selector
        s.deploy_app(app, placement, selectorPath)

        # Trigger placement immediately (deploy COMP1, COMP2 on best node)
        placement.initial_allocation(s, aName)

        # Deploy source — pure source on gateway node
        msg  = s.apps[aName].get_message("M.User")
        dist = exponential_distribution(name="Exp_%s" % aName, lambd=4)
        s.deploy_source(aName, id_node=APP_SRC_NODES[aName], msg=msg, distribution=dist)

        # Deploy sink — pure sink on designated sink node
        for sink_module, sink_node in APP_SINK_NODES[aName].items():
            s.deploy_sink(aName, node=sink_node, module=sink_module)

        print(f"[OK] {aName}: src=node{APP_SRC_NODES[aName]}, "
              f"sink=node{APP_SINK_NODES[aName]}, compute=node49")

    # ------------------------------------------------------------------
    # RUN
    # ------------------------------------------------------------------
    logging.info(" Performing simulation: %i " % it)
    s.run(stop_time)
    s.print_debug_assignaments()


if __name__ == '__main__':
    LOGGING_CONFIG = Path(__file__).parent / 'logging.ini'
    logging.config.fileConfig(LOGGING_CONFIG)

    folder_results = Path(__file__).parent / "results/"
    folder_results.mkdir(parents=True, exist_ok=True)
    folder_results = str(folder_results) + "/"

    simulationDuration = 20000
    random.seed(42)
    logging.info("Running experiment it: - %i" % 42)

    start_time = time.time()
    main(stop_time=simulationDuration, it=0, folder_results=folder_results)

    print("\n--- %s seconds ---" % (time.time() - start_time))
    print("Simulation Done!")

    # ------------------------------------------------------------------
    # RESULTS ANALYSIS
    # ------------------------------------------------------------------
    dfl = pd.read_csv(folder_results + "sim_trace_link.csv")
    print("Number of total messages between nodes: %i" % len(dfl))

    df = pd.read_csv(folder_results + "sim_trace.csv")
    print("Number of requests handled by deployed services: %i" % len(df))

    dfapp2 = df[df.app == "App2"].copy()
    if not dfapp2.empty:
        dfapp2["service_time"] = dfapp2["time_out"] - dfapp2["time_in"]
        print("Average service time of App2: %0.3f" % dfapp2["service_time"].mean())
        print("App2 deployed on nodes: %s"           % np.unique(dfapp2["TOPO.dst"]))
        print("Number of App2 DES instances: %s"     % np.unique(dfapp2["DES.dst"]))
    else:
        print("No data for App2.")

    # ------------------------------------------------------------------
    # EVALUATION METRICS PLOTS
    # ------------------------------------------------------------------
    print("\n--- Generating Evaluation Metrics Plots ---")

    # 1. End-to-end latency: source emit to last module out per request
    df_e2e = df.groupby(['app', 'id']).agg(
        start=('time_emit', 'min'),
        end=  ('time_out',  'max')
    ).reset_index()
    df_e2e['latency'] = df_e2e['end'] - df_e2e['start']
    avg_latency = df_e2e.groupby('app')['latency'].mean()
    print(avg_latency)

    if not avg_latency.empty:
        plt.figure()
        avg_latency.plot(kind='bar',
                         title='Average Latency per Application',
                         ylabel='Latency (sim time units)', xlabel='App')
        plt.tight_layout()
        plt.savefig(folder_results + "avg_latency_per_app.png")
        plt.close()

    # 2. Physical link usage
    if not dfl.empty:
        plt.figure(figsize=(14, 5))
        link_usage = dfl.groupby(['src', 'dst']).size().sort_values(ascending=False)
        (link_usage.head(20) if len(link_usage) > 20 else link_usage).plot(
            kind='bar', title='Top 20 Physical Links Usage', ylabel='Messages')
        plt.tight_layout()
        plt.savefig(folder_results + "link_usage.png")
        plt.close()

    # 3. Node usage
    if not df.empty:
        plt.figure()
        df.groupby('TOPO.dst').size().plot(
            kind='bar', title='Node Usage (Task Allocations)',
            ylabel='Tasks Processed', xlabel='Node ID')
        plt.tight_layout()
        plt.savefig(folder_results + "node_usage.png")
        plt.close()

    # 4. Bandwidth per app
    if not dfl.empty:
        plt.figure()
        if 'size' in dfl.columns:
            dfl.groupby('app')['size'].sum().plot(
                kind='bar', title='Bandwidth Consumption per App',
                ylabel='Total Bytes', xlabel='App')
        else:
            dfl.groupby('app').size().plot(
                kind='bar', title='Bandwidth (Message Counts) per App',
                ylabel='Total Messages', xlabel='App')
        plt.tight_layout()
        plt.savefig(folder_results + "bandwidth_per_app.png")
        plt.close()

    # 5. CPU per app
    if not df.empty:
        plt.figure()
        if 'inst' in df.columns:
            df.groupby('app')['inst'].sum().plot(
                kind='bar', title='CPU (Instructions) per App',
                ylabel='Total Instructions', xlabel='App')
        else:
            df.groupby('app').size().plot(
                kind='bar', title='CPU proxy (Requests) per App',
                ylabel='Total Requests', xlabel='App')
        plt.tight_layout()
        plt.savefig(folder_results + "cpu_per_app.png")
        plt.close()
    
    # RAM Consumption per App
    if not df.empty and 'RAM' in df.columns:
        ram_per_app = df.groupby('app')['RAM'].sum()
        plt.figure()
        ram_per_app.plot(kind='bar',
                        title='RAM Consumption per Application',
                        ylabel='Total RAM Used (MB)', xlabel='App',
                        color='mediumpurple')
        plt.tight_layout()
        plt.savefig(folder_results + "ram_consumption_per_app.png")
        plt.close()
        print("RAM per app plot saved.")

    else:
        # Fallback: estimate RAM from number of module instances deployed
        print("[WARN] No RAM column in sim_trace — estimating from DES module count")
        ram_estimate = df.groupby('TOPO.dst').size()
        plt.figure()
        ram_estimate.plot(kind='bar',
                        title='RAM Proxy: Module Instances per Node',
                        ylabel='Module Instances', xlabel='Node ID',
                        color='steelblue')
        plt.tight_layout()
        plt.savefig(folder_results + "ram_consumption_per_node.png")
        plt.close()

        print("All plots saved to", folder_results)

    # RAM breakdown by module type across all apps
    ram_by_module = df.groupby('module').size()
    plt.figure()
    ram_by_module.plot(kind='bar',
                    title='Module Instance Count (RAM Proxy) by Type',
                    ylabel='Instances Processed', xlabel='Module',
                    color=['steelblue', 'darkorange'])
    plt.tight_layout()
    plt.savefig(folder_results + "ram_by_module.png")
    plt.close()

    
    # RAM Proxy: Module Instances per Application (COMP1 + COMP2 breakdown)
    if not df.empty:
        ram_by_app_module = df.groupby(['app', 'module']).size().unstack(fill_value=0)
        
        plt.figure(figsize=(10, 6))
        ram_by_app_module.plot(kind='bar',
                            title='RAM Proxy: Module Instances per Application',
                            ylabel='Module Instances', xlabel='Application',
                            color=['steelblue', 'darkorange'],
                            rot=0)
        plt.legend(title='Module')
        plt.tight_layout()
        plt.savefig(folder_results + "ram_consumption_per_app.png")
        plt.close()
        print("RAM per app plot saved.")
        print(ram_by_app_module)