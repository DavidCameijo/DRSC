import sys
import random
import networkx as nx
from yafs.core import Sim
from yafs.application import Application, Message, fractional_selectivity
from yafs.distribution import deterministic_distribution, exponential_distribution, uniformDistribution
from yafs.placement import Placement
from yafs.topology import Topology
from utils import Statical, MinimumPath
import os

THRESHOLD = 1.0
LAMBDA = 5
UNIFORM_MIN = 2
UNIFORM_MAX = 10

# Custom placement strategy to place specific modules on predefined target nodes
class FixedPlacement(Placement):
    def __init__(self, target_nodes, module_names, **kwargs):
        super(FixedPlacement, self).__init__(**kwargs)
        self.target_nodes = target_nodes
        self.module_names = module_names

    def initial_allocation(self, sim, app_name):
        app = sim.apps[app_name]
        for i in range(len(self.module_names)):
            module = self.module_names[i]
            service = app.services[module]
            sim.deploy_module(app_name, module, service, [self.target_nodes[i]])

def create_application(name):
    # Create a 3-tier application consisting of a Source, a Processing Module, and a Sink
    app = Application(name=name)
    app.set_modules([{"Generator": {"Type": Application.TYPE_SOURCE}},
                {"DataProcess": {"Type": Application.TYPE_MODULE}},
                {"Actuator": {"Type": Application.TYPE_SINK}}])

    # Define the message emitted by the Source to the Processing Module (requires 500 instructions to be processed)
    msg_generator = Message("M.Action", "Generator", "DataProcess", instructions=500, bytes=1024*1024)
    app.add_source_messages(msg_generator)
    
    # Define the output message emitted from the Processing Module to the Sink Actuator
    msg_result = Message("M.Result", "DataProcess", "Actuator", bytes=1024*1024)
    app.add_service_module("DataProcess", msg_generator, msg_result, fractional_selectivity, threshold=THRESHOLD)
    return app

def main(seed_value, sim_time, num_apps, run, folder, dist_type="deterministic"):
    random.seed(seed_value)
    t = Topology()
    # Create a star topology with 1 center node (0) and 6 peripheral nodes (1-6)
    t.G = nx.star_graph(7)

    # Network attributes
    # IPT (Instructions Per Tick): processing speed/capacity of each computational node
    nx.set_node_attributes(t.G, name="IPT", values={n: random.uniform(500, 1000) for n in t.G.nodes()})
    nx.set_edge_attributes(t.G, name="BW", values={e: random.uniform(0.5, 1) for e in t.G.edges()})
    nx.set_edge_attributes(t.G, name="PR", values={e: random.uniform(0.1, 0.5) for e in t.G.edges()})

    # Pre-allocate nodes for 3 different applications
    # All compute processes are centralized at node 0 (the hub of the star graph)       
    source_nodes = [1, 3, 5]
    destination_nodes = [2, 4, 6]
    compute_nodes = [0, 0, 0]

    selectorPath = MinimumPath()
    # File name includes the run and type to avoid overlapping
    output_name = f"sim_trace_{dist_type}_run_{run}"
    s = Sim(t, default_results_path=f"{folder}/{output_name}")

    for i in range(num_apps):
        app = create_application(f"App_{i}")
        pop = Statical(name=f"Statical_App_{i}")

        # Choose the probability distribution and its parameters for message generation
        if dist_type == "deterministic":
            dist = deterministic_distribution(name=f"Det_{i}", time=5)
        elif dist_type == "exponential":
            dist = exponential_distribution(name=f"Exp_{i}", lambd=0.2)
        elif dist_type == "uniform":
            dist = uniformDistribution(name=f"Uni_{i}", min=UNIFORM_MIN, max=UNIFORM_MAX)
        elif dist_type == "poisson":
            dist = exponential_distribution(name=f"Poisson_{i}", lambd=0.2, seed=seed_value)  # Poisson approximation

        # Define where the Sink (Actuator) and Source (Generator) will be physically placed in the topology
        pop.set_sink_control({"id_node": destination_nodes[i], "number": 1, "module": app.get_sink_modules()})
        pop.set_src_control({"id_node": source_nodes[i], "number": 1, "message": app.get_message("M.Action"), "distribution": dist})

        # Deploy the DataProcess module of the app on its designated centralized compute node
        placement = FixedPlacement(target_nodes=[compute_nodes[i]], module_names=["DataProcess"], name=f"Place_App_{i}")
        s.deploy_app2(app, placement, pop, selectorPath)

    # Run the simulator engine for 'sim_time' ticks
    s.run(sim_time)

if __name__ == '__main__':
    # Global simulation parameters
    sim_time = 1000
    num_apps = 3
    num_runs = 1000
    results_folder = 'ex2/results_ex2_3'

    os.makedirs(results_folder, exist_ok=True)

    # Run the experiment suite varying the traffic generation distribution and random seeds
    for d in ["uniform", "poisson"]:
        for run_idx in range(num_runs):
            main(seed_value=42 + run_idx, sim_time=sim_time, num_apps=num_apps, run=run_idx, folder=results_folder, dist_type=d)
