# plugin_identity.py
# Plugin de personalizacao do Sirius Open
# Edite este arquivo para customizar nome, apresentacao e tratamento
# Ideal para comercializacao — cada cliente pode ter sua identidade

import os

def apply():
    """
    Aplica as configuracoes de identidade do agente.
    Voce pode sobrescrever via .env ou editando diretamente aqui.
    """
    configs = {
        # Nome do agente
        "AGENT_NAME": os.getenv("AGENT_NAME", "Sirius"),

        # Como o agente se dirige ao usuario principal
        "AGENT_TREATMENT": os.getenv("AGENT_TREATMENT", "usuário"),

        # Texto adicional de apresentacao (aparece no final do system prompt)
        "AGENT_PRESENTATION": os.getenv("AGENT_PRESENTATION", ""),

        # Identidade cosmica (True = mantém historia de Sirius/Maria, False = remove)
        "AGENT_COSMIC": os.getenv("AGENT_COSMIC", "true"),
    }
    for k, v in configs.items():
        os.environ.setdefault(k, v)
    return configs

# Exemplo de uso para um cliente diferente:
# No .env do cliente, defina:
# AGENT_NAME=Atlas
# AGENT_TREATMENT=Dr. Silva
# AGENT_PRESENTATION=Voce e especialista em direito tributario.
# AGENT_COSMIC=false
