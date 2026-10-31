"""Interpreta pedidos dos usuários e executa as ações do Google"""

import json #converter os dados da ferramenta do Google em JSON
import os #interage com o sistema operacional
import unicodedata #normaliza strings Unicode

from dotenv import load_dotenv #carrega variáveis de ambiente do arquivo .env
from openai import OpenAI #acessa a API do OpenAI

from google_tools import autenticar_google, agendar_entrevista_com_meet, registrar_candidato #importa funções do Google

#carregar a groq_api_key
load_dotenv() #carrega variáveis de ambiente do arquivo .env
groq_api_key = os.getenv("GROQ_API_KEY")
#ERRO: groq_api_key não foi definida, crregue-a com os.getenv("GROQ_API_KEY") antes desse ponto
client = OpenAI(
    api_key=groq_api_key,
    base_url="https://api.groq.com/openai/v1",
) if groq_api_key else None


#definir o modelo e indicar o id da planilha
MODELO_GROQ = "openai/gpt-oss-20b"
PLANILHA_ID = os.environ.get("PLANILHA_ID")

#criando as ferramentas do agente

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "agendar_entrevista_com_meet",
            "description": "Agendar uma entrevista no Google Calendar com link do Google Meet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_candidato": {"type": "string"},
                    "email_candidato": {"type": "string"},
                    "data_hora_inicio": {
                        "type": "string",
                        "description": "Data e hora de início da entrevista no formato ISO 8601 (ex: 2023-10-01T14:00:00)",
                    },
                    "data_hora_fim": {
                        "type": "string",
                        "description": "Data e hora de término da entrevista no formato ISO 8601 (ex: 2023-10-01T15:00:00)",
                    },
                },
                "required": [
                    "nome_candidato",
                    "email_candidato",
                    "data_hora_inicio",
                    "data_hora_fim",
                ],
            },
        },
    },
    {
        #crie a função para registrar o candidato na planilha do Google Sheets
        "type": "function",
        "function": {
            "name": "registrar_candidato_planilha",
            "description": "Registrar informações do candidato em uma planilha do Google Sheets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "email": {"type": "string"},
                    "vaga": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["nome", "email"],
            },
        },
    },
]

#prompt para definir as regras do agente e os padrões para os dados informados

PROMPT = (
"Você é um agente de recrutamento e seleção. Sua função é interpretar os pedidos dos usuários e executar as ações do Google, como agendar entrevistas no Google Calendar com link do Google Meet e registrar informações de candidatos em uma planilha do Google Sheets."
"Siga as instruções abaixo:"
"1. Solicite o nome completo do candidato. \n"
"2. Solicite o e-mail do candidato. \n"
"3. Solicite a vaga para a qual o candidato está se candidatando. \n"
"4. Solicite o status do candidato (ex: aprovado, reprovado, em análise). \n"
"5. Solicite a data e hora de início da entrevista no formato ISO 8601 (ex: 2023-10-01T14:00:00). \n"
"6. Solicite a data e hora de término da entrevista no formato ISO 8601 (ex: 2023-10-01T15:00:00). \n"
"Após coletar todas as informações, utilize as funções disponíveis para agendar a entrevista e registrar o candidato na planilha. \n"
 )
#função para normalizar os dados d entrada
def normalizar(texto):
    """Função para normalizar,removendo acentos e caracteres especiais."""
    sem_acento = unicodedata.normalize('NFKD', texto)
    return "".join(letra for letra in sem_acento if not unicodedata.combining(letra)).lower()

#função para executar o agente
def executar_agente_rh(mensagem_usuario):
    if client is None:
        return [{"erro": "Configure chave API do Groq para usar o agente."}]
    #enviar a mensagem do usuário para o modelo do Groq
    resposta = client.chat.completions.create(
        model=MODELO_GROQ,
        messages=[
            {"role": "system" , "content": PROMPT},
            {"role": "user" , "content": mensagem_usuario},
        ],
        tools = FERRAMENTAS, #ferramenta disponível para o agente
        tool_choice = "auto", #o agente escolhe automaticamente a ferramenta apropriada
    )

    #extrair a mensagem retornada pela IA dentro da resposta da API.
    mensagem = resposta.choices[0].message
    #buscar as ferramentas disponíveis; se nenhuma for chamada, retorna uma lista vazia.
    tool_calls = mensagem.tool_calls or []

    if not tool_calls:
        return [{"texto": mensagem.content or "Não sei fazer isso."}]

    resultados = [] #lista para armazenar os resultados das chamadas de ferramentas
    #executar cada ferramenta que o modelo decidiu chamar
    for chamada in tool_calls:
        nome = chamada.function.name 
        args = json.loads(chamada.function.arguments) #pega os argumentos da funcao a ser executada

        if nome == "agendar_entrevista_com_meet":
            resultado = agendar_entrevista_com_meet(
                args["nome_candidato"],
                args["email_candidato"],
                args["data_horario_inicio"],
                args["data_horario_fim"],
            )