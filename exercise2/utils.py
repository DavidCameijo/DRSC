import networkx as nx
from yafs.population import Population
from yafs.selection import Selection


"""
    Generates a source and sink control module of an app in a specific topology node
"""
class Statical(Population):
    def __init__(self, **kwargs):
        super(Statical, self).__init__(**kwargs)

        self.src_control = []
        self.sink_control = []


    def initial_allocation(self, sim, app_name):
        # Deploy the Sink (Actuator) exactly where we tell it to
        for ctrl in self.sink_control:
            sim.deploy_sink(app_name, node=ctrl["id_node"], module=ctrl["module"])

        # Deploy the Source (Generator) exactly where we tell it to
        for ctrl in self.src_control:
            sim.deploy_source(app_name, id_node=ctrl["id_node"], msg=ctrl["message"], distribution=ctrl["distribution"])



"""
    Computes the minimum hop path among the source element of the topology and the locations of the module

    Returns the path and identifier of the module deployed in the last element of that path
"""
class MinimumPath(Selection):
    def __init__(self, **kwargs):
        super(MinimumPath, self).__init__(**kwargs)


    def get_path(self, sim, app_name, message, topology_src, alloc_DES, alloc_module, traffic, from_des):
        node_src = topology_src
        des_dst = alloc_module[app_name][message.dst]

        """
        print(("GET PATH"))
        print(("\tNode _ src (id_topology): %i" %node_src))
        print(("\tRequest service: %s " %message.dst))
        print(("\tProcess serving that service: %s " %des_dst))
        """

        bestPath = []
        bestDES = []

        for des in des_dst: ## In this case, there are only one deployment
            dst_node = alloc_DES[des]
            # print(("\t\t Looking the path to id_node: %i" %dst_node))

            path = list(nx.shortest_path(sim.topology.G, source=node_src, target=dst_node))

            bestPath = [path]
            bestDES = [des]

        return bestPath, bestDES
