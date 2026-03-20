import sys
import random
import networkx as nx
from datetime import datetime
from yafs.application import fractional_selectivity
from yafs.core import Sim
from yafs.application import Application, Message
from yafs.distribution import deterministic_distribution, exponential_distribution, uniformDistribution
from yafs.placement import Placement
from yafs.topology import Topology

from utils import Statical, MinimumPath


"""
    Probability of how many outgoing messages are generated for each incoming message
    
    THRESHOLD >= 1.0 -> 1 to 1
    THRESHOLD < 1.0 -> less than 1 message generated
"""
THRESHOLD = 1.0


"""
    Generates a fixed module placement
"""
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
            # print(f"-> Deployed module '{module}' on node {self.target_nodes[i]}")


"""
    Creates a three-module application with source, computation module and destination
"""
def create_application(name):
    app = Application(name=name)

    app.set_modules([{"Generator": {"Type": Application.TYPE_SOURCE}},
                {"DataProcess": {"Type": Application.TYPE_MODULE}},
                {"Actuator": {"Type": Application.TYPE_SINK}}
                ])

    msg_generator = Message("M.Action", "Generator", "DataProcess", instructions=500, bytes=1024*1024)
    app.add_source_messages(msg_generator)
    
    msg_result = Message("M.Result", "DataProcess", "Actuator", bytes=1024*1024)
    app.add_service_module("DataProcess", msg_generator, msg_result, fractional_selectivity, threshold=THRESHOLD)

    return app


def main(seed_value, sim_time, num_apps, run, folder, dist_type="deterministic"):
    random.seed(seed_value)
    
    t = Topology()
    t.G = nx.star_graph(7)

    # Atributos da Topologia
    attIPT = {node: random.uniform(500, 1000) for node in t.G.nodes()}
    nx.set_node_attributes(t.G, name="IPT", values=attIPT)
    attBW = {edge: random.uniform(0.5, 1) for edge in t.G.edges()}
    attPR = {edge: random.uniform(0.1, 0.5) for edge in t.G.edges()}
    nx.set_edge_attributes(t.G, name="BW", values=attBW)
    nx.set_edge_attributes(t.G, name="PR", values=attPR)

    source_nodes = [1, 3, 5]
    destination_nodes = [2, 4, 6]
    compute_nodes = [0, 0, 0]

    selectorPath = MinimumPath()
    # Diferenciar o nome do ficheiro pelo tipo de distribuição
    s = Sim(t, default_results_path=f"{folder}/sim_trace_ex2_3_{dist_type}")

    # Ciclo ÚNICO para criar e fazer o deploy das apps
    for i in range(num_apps):
        app = create_application("App_" + str(i))
        pop = Statical(name=f"Statical_App_{i}")

        # Lógica da Atividade 2: Seleção da Distribuição
        if dist_type == "deterministic":
            dist = deterministic_distribution(name=f"Det_{i}", time=5)
        elif dist_type == "exponential":
            dist = exponential_distribution(name=f"Exp_{i}", lambd=0.2)
        elif dist_type == "uniform":
            # SOLUÇÃO: Usar INTEIROS (2 e 8) para evitar o TypeError no randint
            dist = uniformDistribution(name=f"Uni_{i}", min=2, max=8)
        
        pop.set_sink_control({
            "id_node": destination_nodes[i], 
            "number": 1, 
            "module": app.get_sink_modules()
        })
        
        pop.set_src_control({
            "id_node": source_nodes[i], 
            "number": 1, 
            "message": app.get_message("M.Action"), 
            "distribution": dist
        })

        placement = FixedPlacement(
            target_nodes=[compute_nodes[i]], 
            module_names=["DataProcess"], 
            name=f"Place_App_{i}"
        )
        
        # Faz o deploy imediatamente após configurar cada app
        s.deploy_app2(app, placement, pop, selectorPath)
    
    print(f"Starting simulation with {dist_type}...")
    s.run(sim_time)
    print("Simulation complete.")

if __name__ == '__main__':
    sim_time = 1000
    num_apps = 3
    num_runs = 1
    results_folder = '.'

    for d in ["deterministic", "exponential", "uniform"]:
        main(seed_value=42, sim_time=sim_time, num_apps=num_apps, run=0, folder=results_folder, dist_type=d)
