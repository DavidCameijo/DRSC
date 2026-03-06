import json
import random

def generate_dynamic_users(num_users, total_nodes, total_apps):
    """
    Gera um ficheiro JSON de utilizadores com base em parâmetros.
    
    :param num_users: Quantidade de utilizadores/fontes de tráfego a criar
    :param total_nodes: Número de nós existentes na tua topologia (ex: 10, 50, 100)
    :param total_apps: Número de aplicações que definiste no appDefinition
    """
    
    user_data = {"sources": []}

    for i in range(num_users):
        # Escolhe um nó aleatório da rede (assumindo que os IDs começam em 0)
        node_id = random.randint(0, total_nodes - 1)
        
        # Escolhe uma aplicação aleatória entre as disponíveis
        app_id = random.randint(0, total_apps - 1)
        
        # Define o nome da mensagem inicial (deve bater certo com o teu JSON de apps)
        message_name = f"M.USER.APP.{app_id}"
        
        # Gera um valor de lambda aleatório (frequência de pedidos)
        # Ex: entre 100 e 1000 unidades de tempo
        lambda_val = random.randint(100, 1000)

        # Cria a entrada do utilizador
        user_entry = {
            "id_resource": node_id,
            "app": str(app_id),
            "message": message_name,
            "lambda": lambda_val
        }
        
        user_data["sources"].append(user_entry)

    # Guarda o resultado no ficheiro obrigatório
    with open('dynamicUsersDefinition.json', 'w') as f:
        json.dump(user_data, f, indent=4)

    print(f"Sucesso! Ficheiro 'dynamicUsersDefinition.json' gerado com {num_users} utilizadores.")

# --- CONFIGURAÇÃO ---
# Se a tua topologia tem 10 nós e criaste 3 apps no appDefinition3.json:
generate_dynamic_users(num_users=15, total_nodes=10, total_apps=3) 