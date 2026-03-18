# Exercício 3:

Number of nodes:101, number of edges: 197

# Exercício 4:

* **`appDefinition.json`** : Describes very simple, linear applications. Each application typically contains only one module and one message. The transmission flow is a direct 1-to-1 mapping from an entry message to a single module.
* **`appDefinition2.json`** : Describes complex, branching topologies. Applications often have multiple modules (e.g., App 0 has 3 modules, App 1 has 7). The transmissions include many-to-one and sequential flows where messages trigger subsequent messages (e.g., `0_0` sends messages to both `0_1` and `0_2`).

# Exercício 6:

1. Comparação: usersDefinition.json vs usersDefinition2.json
A análise comparativa entre os dois ficheiros revela uma transição de um cenário de teste controlado para uma simulação de carga realística e complexa.
| Característica | `usersDefinition.json` | `usersDefinition2.json` |
| **Volume de Fontes** | Pequena escala (apenas 4 fontes). | Larga escala (~70 fontes). |
| **Densidade de Apps** | 4 aplicações (ID 0 a 3). | 20 aplicações (ID 0 a 19). |
| **Relação Nó/App** | 1 para 1: Cada app tem apenas um utilizador. | N para 1: Múltiplos utilizadores por app (concorrência). |
| **Frequência (Lambda)** | Estática e previsível (200 ou 500). | Dinâmica e variável (ex: 229, 770, 939). |
| **Complexidade** | Ideal para depuração inicial. | Ideal para testes de stress e latência. |

2. Observações sobre a Distribuição (Ponto 101)
A. Concorrência e Localização

No ficheiro usersDefinition2.json, observa-se que aplicações como a App 1 são invocadas a partir de múltiplos nós (id_resource 33, 88, 93, 97 e 20). Isto permite ao simulador YAFS calcular o impacto da distância física (latência) e da carga simultânea no processamento dos módulos.
B. Intensidade de Tráfego

A variação do parâmetro lambda no segundo ficheiro introduz um comportamento estocástico. Valores de lambda mais elevados representam utilizadores mais "agressivos", o que pode levar à saturação dos links de comunicação ou ao overflow da capacidade de IPT (instruções por segundo) dos nós de computação.
3. Implementação no Simulador

A integração destes ficheiros no ambiente YAFS é feita no script principal (main.py), especificamente na secção marcada como "DEPLOY USERS".

    [!IMPORTANT]
    Compatibilidade de Ficheiros:
    Para utilizar o usersDefinition2.json com sucesso, o ficheiro de definição de aplicações (ex: appDefinition.json) deve obrigatoriamente conter as definições para as 20 aplicações mencionadas. Caso contrário, o simulador irá falhar ao tentar encaminhar mensagens para serviços inexistentes.

4. Conclusão da Atividade

A utilização de populações dinâmicas e densas é fundamental para validar a robustez da topologia desenhada nas atividades anteriores. Enquanto o primeiro ficheiro valida a conectividade, o segundo valida a performance e escalabilidade do sistema Fog proposto.