"""
    This is the most simple scenario with a basic topology, some users and a set of apps with only one service.

    @author: Isaac Lera
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

class MinimizeExecutionTimePlacement(Placement):
    def __init__(self, name, **kwargs):
        super(MinimizeExecutionTimePlacement, self).__init__(name, **kwargs)

    def initial_allocation(self, sim, app_name):
        best_compute_node = None
        max_ipt = -1
        for node in sim.topology.G.nodes():
            ipt = sim.topology.G.nodes[node].get('IPT', 0)
            if ipt > max_ipt:
                max_ipt = ipt
                best_compute_node = node
        
        sink_node = 39
        app = sim.apps[app_name]
        for module in app.services:
            if module == "Sink":
                # Mandatory: Sinks go to nodes 39-48
                sim.deploy_module(app_name, module, app.services[module], [sink_node])
            elif module == "Source":
                # Sources are handled by the deploy_source call, 
                # but we can deploy a dummy here if needed
                continue 
            else:
                # COMP modules go to the fastest node (Cloud)
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
            concPath = message.path[0 : message.path.index(path[0][0])] + path[0]
            return [concPath], des
        return [], []

def main(stop_time, it,folder_results):

    """
    TOPOLOGY
    """
    t = Topology()

    # You also can create a topology using JSONs files. Check out examples folder
    size = 50
    t.G = nx.generators.barabasi_albert_graph(size, m=2) # In NX-lib there are a lot of Graphs generators

    # Definition of mandatory attributes of a Topology
    ## Attr. on edges
    #PR = 2
    #BW = 75000
    attPR = {x: 2 for x in t.G.edges()}
    attBW = {x: 75000 for x in t.G.edges()}
    nx.set_edge_attributes(t.G, name="PR", values=attPR)
    nx.set_edge_attributes(t.G, name="BW", values=attBW)
    ## Attr. on nodes
    attIPT = {}
    attRAM = {}
    for x in t.G.nodes():
        if 0 <= x <= 4:
            attIPT[x] = 0
            attRAM[x] = 0
        elif 5 <= x <= 48:
            attRAM[x] = 8192
            attIPT[x] = 1000
        elif x == 49:
            attIPT[x] = 1000000000
            attRAM[x] = 1000000000
            
    nx.set_node_attributes(t.G, name="IPT", values=attIPT)
    nx.set_node_attributes(t.G, name="RAM", values=attRAM)

    nx.write_gexf(t.G,folder_results+"graph_binomial_tree_%i.gexf"%size) # you can export the Graph in multiples format to view in tools like Gephi, and so on.

    print(t.G.nodes()) # nodes id can be str or int

    # Plotting the graph
    pos=nx.spring_layout(t.G)
    nx.draw_networkx(t.G, pos, with_labels=True)
    nx.draw_networkx_edge_labels(t.G, pos,alpha=0.5,font_size=5,verticalalignment="top")
    plt.axis('off')
    plt.show()

    """
    APPLICATION or SERVICES
    """
    data_folder = os.path.join(os.path.dirname(__file__), 'data')
    dataApp = json.load(open(os.path.join(data_folder, 'appDefinition3.json')))
    apps = create_applications_from_json(dataApp)
    for name, app in apps.items():
        print(f"App carregada: {name}")
        print(f"Mensagens disponíveis: {app.messages.keys()}")
    """
    SERVICE PLACEMENT 
    """
    placement = MinimizeExecutionTimePlacement(name="Placement")

    """
    Defining ROUTING algorithm to define how path messages in the topology among modules
    """
    selectorPath = MinimizeLatencyRouting()

    """
    SIMULATION ENGINE
    """
    s = Sim(t, default_results_path=folder_results+"sim_trace")

    """
    Deploy services == APP's modules
    """
    for aName in apps.keys():
        s.deploy_app(apps[aName], placement, selectorPath) # Note: each app can have a different routing algorithm

    """
    Deploy users
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
            print(f"Erro: Aplicação {app_name} não encontrada no simulador!")

    """
    RUNNING - last step
    """
    logging.info(" Performing simulation: %i " % it)
    s.run(stop_time)  # To test deployments put test_initial_deploy a TRUE
    s.print_debug_assignaments()


if __name__ == '__main__':
    LOGGING_CONFIG = Path(__file__).parent / 'logging.ini'
    logging.config.fileConfig(LOGGING_CONFIG)

    folder_results = Path("results/")
    folder_results.mkdir(parents=True, exist_ok=True)
    folder_results = str(folder_results)+"/"

    simulationDuration = 20000  

    # Iteration for each experiment changing the seed of randoms
    random.seed(42)
    logging.info("Running experiment it: - %i" % 42)

    start_time = time.time()
    main(stop_time=simulationDuration,
        it=0,folder_results=folder_results)

    print("\n--- %s seconds ---" % (time.time() - start_time))

    print("Simulation Done!")
  
    # Analysing the results. 
    dfl = pd.read_csv(folder_results+"sim_trace"+"_link.csv")
    print("Number of total messages between nodes: %i"%len(dfl))

    df = pd.read_csv(folder_results+"sim_trace.csv")
    print("Number of requests handled by deployed services: %i"%len(df))

    dfapp2 = df[df.app == 2].copy() # a new df with the requests handled by app 2
    print(dfapp2.head())
    
    dfapp2.loc[:,"transmission_time"] = dfapp2.time_emit - dfapp2.time_reception # Transmission time
    dfapp2.loc[:,"service_time"] = dfapp2.time_out - dfapp2.time_in

    print("The average service time of app2 is: %0.3f "%dfapp2["service_time"].mean())

    print("The app2 is deployed in the folling nodes: %s"%np.unique(dfapp2["TOPO.dst"]))
    print("The number of instances of App2 deployed is: %s"%np.unique(dfapp2["DES.dst"]))
    
    # -----------------------
    # PLOTTING AND EVALUATION METRICS
    # -----------------------
    print("\n--- Generating Evaluation Metrics Plots ---")
    
    # 1. Average latency per application
    df['total_latency'] = df['time_out'] - df['time_emit']
    avg_latency = df.groupby('app')['total_latency'].mean()
    plt.figure()
    avg_latency.plot(kind='bar', title='Average Latency per Application', ylabel='Latency (ms)')
    plt.tight_layout()
    plt.savefig(folder_results + "avg_latency_per_app.png")
    
    # 2. Physical link and node usage
    plt.figure()
    link_usage = dfl.groupby(['src', 'dst']).size()
    if len(link_usage) > 20: 
        link_usage.sort_values(ascending=False).head(20).plot(kind='bar', title='Top 20 Physical Links Usage', ylabel='Messages')
    else:
        link_usage.plot(kind='bar', title='Physical Link Usage', ylabel='Messages')
    plt.tight_layout()
    plt.savefig(folder_results + "link_usage.png")

    plt.figure()
    node_usage = df.groupby('TOPO.dst').size()
    node_usage.plot(kind='bar', title='Node Usage (Task Allocations)', ylabel='Tasks Processed')
    plt.tight_layout()
    plt.savefig(folder_results + "node_usage.png")
    
    # 3. Bandwidth, CPU, and RAM consumption per application
    plt.figure()
    if 'size' in dfl.columns:
        bw_app = dfl.groupby('app')['size'].sum()
        bw_app.plot(kind='bar', title='Bandwidth Consumption per App', ylabel='Total Bytes')
    else:
        # Fallback to message counts if size is unavailable
        dfl.groupby('app').size().plot(kind='bar', title='Bandwidth (Message Counts) per App', ylabel='Total Messages')
    plt.tight_layout()
    plt.savefig(folder_results + "bandwidth_per_app.png")
    
    plt.figure()
    if 'inst' in df.columns:
        cpu_app = df.groupby('app')['inst'].sum()
        cpu_app.plot(kind='bar', title='CPU (Instructions) Consumption per App', ylabel='Total Instructions')
    else:
        # Fallback to request counts
        df.groupby('app').size().plot(kind='bar', title='CPU proxy (Requests) per App', ylabel='Total Requests')
    plt.tight_layout()
    plt.savefig(folder_results + "cpu_per_app.png")

    # Assuming RAM is correlated to message sizes/requests in this simulation context.
    # Note: Dedicated RAM calculation would depend on initial app deployment specs.
    
    plt.show()
