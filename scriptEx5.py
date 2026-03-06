import json
import random

def generate_workload(num_apps, max_modules_per_app):
    apps = []

    for app_id in range(num_apps):
        app_name = f"App_{app_id}"
        num_modules = random.randint(1, max_modules_per_app) # Parametrização/Randomização
        deadline = random.randint(500, 2000)
        
        modules = []
        messages = []
        transmissions = []

        for m_id in range(1, num_modules + 1):
            mod_name = f"{app_id}_{m_id:02d}"
            
            # 1. Criar Módulo
            modules.append({
                "id": m_id,
                "name": mod_name,
                "type": "MODULE",
                "RAM": random.randint(1, 4) # RAM aleatória
            })

            # 2. Criar Mensagens e Transmissões
            if m_id == 1:
                # Mensagem inicial do utilizador
                msg_name = f"M.USER.APP.{app_id}"
                messages.append({
                    "id": 0,
                    "name": msg_name,
                    "s": "None",
                    "d": mod_name,
                    "bytes": random.randint(100, 500),
                    "instructions": random.randint(100, 1000)
                })
                
                trans_entry = {"message_in": msg_name, "module": mod_name}
                if num_modules > 1:
                    trans_entry["message_out"] = f"M.{mod_name}-{app_id}_{m_id+1:02d}"
                transmissions.append(trans_entry)
            
            else:
                # Mensagens entre módulos internos
                msg_in_name = f"M.{app_id}_{m_id-1:02d}-{mod_name}"
                messages.append({
                    "id": m_id - 1,
                    "name": msg_in_name,
                    "s": f"{app_id}_{m_id-1:02d}",
                    "d": mod_name,
                    "bytes": random.randint(50, 200),
                    "instructions": random.randint(50, 500)
                })
                
                trans_entry = {"message_in": msg_in_name, "module": mod_name}
                if m_id < num_modules:
                    trans_entry["message_out"] = f"M.{mod_name}-{app_id}_{m_id+1:02d}"
                transmissions.append(trans_entry)

        # Montar a aplicação
        apps.append({
            "id": app_id,
            "name": app_name,
            "deadline": deadline,
            "module": modules,
            "message": messages,
            "transmission": transmissions
        })

    # Guardar no ficheiro obrigatório
    with open('dynamicAppDefinition.json', 'w') as f:
        json.dump(apps, f, indent=2)
    
    print(f"Sucesso! Geradas {num_apps} aplicações em 'dynamicAppDefinition.json'.")

# Exemplo de uso: 3 apps, cada uma com no máximo 5 módulos
generate_workload(num_apps=3, max_modules_per_app=5)