import json
import random
import networkx as nx
from yafs.core import Sim
from yafs.application import Application, Message
from yafs.distribution import deterministic_distribution, deterministicDistributionStartPoint
from yafs.placement import NoPlacementOfModules
from yafs.topology import Topology
import matplotlib.pyplot as plt

from utils import Statical, MinimumPath

"""
    Generates a unique link failure with a specific link and a specific simulation time
"""
class LinkFailure():
    def __init__(self, target_time, edge_to_remove):
        self.target_time = target_time
        self.edge_to_remove = edge_to_remove
        self.triggered = False

    def __call__(self, sim, routing):
        # Check if the simulation clock has reached our target time
        if sim.env.now >= self.target_time and not self.triggered:
            u, v = self.edge_to_remove
            
            # Verify the edge actually exists in the network graph before cutting it
            if sim.topology.G.has_edge(u, v):
                sim.topology.G.remove_edge(u, v)
                # print(f"\n[{sim.env.now}] - Link between Node {u} and Node {v} REMOVED.")
                
                # Force YAFS to recalculate paths
                routing.invalid_cache_value = True
            else:
                # print(f"\n[{sim.env.now}] - Attempted to remove link {u}-{v}, but it does not exist!")
                pass
            
            # Lock the trigger so it doesn't fire again
            self.triggered = True


"""
    Creates a two-module application with source and destination
"""
def create_application(name):
    app = Application(name=name)

    app.set_modules([{"Generator": {"Type": Application.TYPE_SOURCE}},
                {"Actuator": {"Type": Application.TYPE_SINK}}
                ])

    msg_generator = Message("M.Action", "Generator", "Actuator", bytes=1024*1024)
    app.add_source_messages(msg_generator)

    return app


def main(sim_time, seed_value, num_apps, folder):
    # Set the seed to ensure reproducibility
    random.seed(seed_value) 
    
    t = Topology()
    t.G = nx.Graph()
    
    edges = [(0, 1), (0, 2), (1, 3), (2, 3), (2, 4), (3, 5), (4, 5)]
    t.G.add_edges_from(edges)

    # Assign heterogeneous Bandwidth and Propagation Delay
    attBW = {edge: random.uniform(0.5, 1) for edge in t.G.edges()}
    attPR = {edge: random.uniform(0.1, 0.5) for edge in t.G.edges()}
    
    nx.set_edge_attributes(t.G, name="BW", values=attBW)
    nx.set_edge_attributes(t.G, name="PR", values=attPR)
    
    source_nodes = [0, 2, 4]
    destination_nodes = [1, 3, 5]

    # Create Applications, Populations and Placement per application
    apps = []
    populations = []
    
    for i in range(num_apps):
        app = create_application("App_" + str(i))
        apps.append(app)
        
        # Create a population object for this specific app
        pop = Statical(name=f"Statical_App_{i}")
        
        if i == 0:
            dist = deterministic_distribution(name=f"Det_{i}", time=3)
        else:
            dist = deterministic_distribution(name=f"Det_{i}", time=5)
        
        pop.set_sink_control({
            "id_node": destination_nodes[i], 
            "number": 1, # We want exactly 1 sink
            "module": app.get_sink_modules()
        })
        
        pop.set_src_control({
            "id_node": source_nodes[i], 
            "number": 1, # We want exactly 1 source generating messages
            "message": app.get_message("M.Action"), 
            "distribution": dist
        })
        
        populations.append(pop)

    # Define placement and routing strategies
    placement = NoPlacementOfModules("NoPlacement")
    selectorPath = MinimumPath()

    # Simulation Setup
    s = Sim(t, default_results_path=f"{folder}/sim_trace_ex1")

    for i in range(num_apps):
        s.deploy_app2(apps[i], placement, populations[i], selectorPath)

    # Generates an edge failure in the topology in a specific interval
    dist = deterministicDistributionStartPoint(sim_time/4.0, sim_time/2.0/10.0, name="Deterministic")
    evol = LinkFailure(target_time=50, edge_to_remove=(0, 1))
    s.deploy_monitor("NodeFailureTopology",
                    evol,
                    dist,
                    **{"sim": s, "routing": selectorPath})


    print("Starting simulation...")
    s.run(sim_time)
    print("Simulation complete.")


if __name__ == '__main__':
    seed = 42
    sim_time = 100
    num_apps = 3

    main(sim_time, seed, num_apps, '.')
