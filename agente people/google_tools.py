# ETAPA 1

# importa bibliotecas necessárias para o funcionamento do código
import os  # acessa os arquivos do sistema operacional
import unicodedata  # normaliza os caracteres unicode
import uuid  # gera identificadores únicos
from datetime import datetime  # manipula datas e horas

from google.auth.exceptions import RefreshError  # trata erros de autenticação do Google
from google.auth.transport.requests import Request  # faz requisições HTTP para autenticação
from google.oauth2.credentials import Credentials  # trabalha com credenciais do Google
from google_auth_oauthlib.flow import InstalledAppFlow  # gerencia o fluxo de autenticação OAuth 2.0
from googleapiclient.discovery import build  # constrói serviços da API do Google

# ETAPA 2 Criar os escopos de autenticação
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/spreadsheets',
]  # credenciais de acesso para o Google Calendar e Google Sheets

# dicionario com os nomes das colunas na planilha e seus respectivos ids
CAMPOS_DA_PLANILHA = {
    "nome": {"nome", "nomecandidato"},
    "vaga": {"vaga", "cargo"},
    "data": {"data", "datacandidato"},
    "hora": {"hora", "horario", "horarioentrevista"},
    "email": {"email", "emailcandidato"},
    "status": {"status", "situacao"},
}


def _normalizar_campo(valor):
    texto = unicodedata.normalize("NFKD", str(valor).lower())
    return texto.encode("ascii", "ignore").decode("ascii").strip()


# ETAPA 3: Função para autenticar google e retornar o serviço de planilhas e calendario
def autenticar_google():
    credenciais = None  # variavel para alocar as credenciais do google
    if os.path.exists('token.json'):  # verifica se o arquivo token existe
        credenciais = Credentials.from_authorized_user_file('token.json', SCOPES)  # carrega as credenciais do arquivo token.json

    if credenciais and credenciais.expired and credenciais.refresh_token:  # verifica se as credenciais estão expiradas e se existe um token de atualização
        try:
            credenciais.refresh(Request())  # atualiza as credenciais
        except RefreshError as erro:  # caso ocorra um erro de atualização
            if "invalid_grant" in str(erro):  # verifica se o erro é de concessão inválida
                raise
            credenciais = None  # se ocorrer um erro, define as credenciais como None

    if not credenciais or not credenciais.valid:  # não existem credenciais ou não são válidas
        fluxo = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)  # cria um fluxo de autenticação a partir do arquivo client_secret.json
        credenciais = fluxo.run_local_server(port=0)  # executa o fluxo de autenticação em um servidor local

    with open('token.json', 'w') as token:  # abre o arquivo token.json para escrita
        token.write(credenciais.to_json())  # escreve as credenciais no arquivo token.json
    return credenciais  # retorna as credenciais autenticadas


def agendar_entrevista_com_meet(
    nome_candidato,
    email_candidato,
    data_hora_inicio,
    data_hora_fim,
):
    """Função para agendar uma entrevista no Google Calendar com link do Google Meet."""
    servico = build('calendar', 'v3', credentials=autenticar_google())  # cria um serviço do Google Calendar usando as credenciais autenticadas

    evento = {
        'summary': f'Entrevista com {nome_candidato}',  # título do evento
        'description': 'Entrevista de alinhamento com o time do people',  # descrição do evento
        'start': {
            "dateTime": data_hora_inicio,  # data e hora de início do evento
            "timeZone": 'America/Sao_Paulo',  # fuso horário do evento
        },
        'end': {
            "dateTime": data_hora_fim,  # data e hora de término do evento
            "timeZone": 'America/Sao_Paulo',  # fuso horário do evento
        },
        "attendees": [
            {"email": email_candidato},  # adiciona o e-mail do candidato como participante do evento
        ],
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),  # gera um identificador único para a solicitação de criação da conferência
                "conferenceSolutionKey": {"type": "hangoutsMeet"},  # define o tipo de conferência como Google Meet
            }
        },
    }

    evento_criado = servico.events().insert(
        calendarId='primary',  # define o calendário principal do usuário
        body=evento,  # passa o dicionário do evento como corpo da solicitação
        conferenceDataVersion=1,
        sendUpdates='all',
    ).execute()  # executa a solicitação de criação do evento

    link_meet = evento_criado.get('hangoutLink')  # obtém o link do Google Meet do evento criado
    return link_meet  # retorna o link do Google Meet para o evento agendado


def registrar_candidat_planilha(
    id_planilha,
    nome,
    email,
    vaga,
    status,
    data_hora_inicio=None,
    data_hora_fim=None,
):
    """Função para registrar informações do candidato em uma planilha do Google Sheets."""
    servico = build('sheets', 'v4', credentials=autenticar_google())  # cria um serviço do Google Sheets usando as credenciais autenticadas

    planilha = servico.spreadsheets().get(
        spreadsheetId=id_planilha,
        fields='sheets(properties(sheetId,title))',
    ).execute()

    if not planilha.get("sheets"):
        raise ValueError("Aba não encontrada na planilha.")

    resposta = servico.spreadsheets().values().get(
        spreadsheetId=id_planilha,
        range='1:1',
        majorDimension='ROWS',
    ).execute()

    cabecalho = resposta.get("values", [[]])[0] if resposta.get("values") else []

    if not cabecalho:
        cabecalho = ["nome", "email", "vaga", "status", "data", "hora"]
        servico.spreadsheets().values().update(
            spreadsheetId=id_planilha,
            range='A1:F1',
            valueInputOption='RAW',
            body={'values': [cabecalho]},
        ).execute()

    colunas = {}
    for indice, titulo in enumerate(cabecalho):
        campo_normalizado = _normalizar_campo(titulo)
        for campo, aliases in CAMPOS_DA_PLANILHA.items():
            if campo_normalizado in aliases or campo_normalizado == campo:
                colunas[campo] = indice
                break

    dados = {
        "nome": nome,
        "email": email,
        "vaga": vaga,
        "status": status,
    }

    if data_hora_inicio:
        try:
            inicio = datetime.fromisoformat(data_hora_inicio)  # converte a string de data e hora de início para um objeto datetime
        except ValueError as exc:
            raise ValueError("Formato de data e hora inválido. Use o formato ISO 8601 (YYYY-MM-DDTHH:MM:SS).") from exc

        dados["data"] = inicio.strftime("%d/%m/%Y")  # formata a data de início para o formato dd/mm/aaaa
        hora = inicio.strftime("%H:%M")  # formata a hora de início para o formato hh:mm

        if data_hora_fim:
            try:
                fim = datetime.fromisoformat(data_hora_fim)  # converte a string de data e hora de fim para um objeto datetime
            except ValueError as exc:
                raise ValueError("Formato de data e hora inválido. Use o formato ISO 8601 (YYYY-MM-DDTHH:MM:SS).") from exc
            hora = f"{hora} - {fim.strftime('%H:%M')}"  # adiciona a hora de fim ao campo de hora, separada por um hífen

        dados["hora"] = hora

    max_coluna = max(colunas.values(), default=0) + 1
    quantidade_colunas = max(len(cabecalho), max_coluna)
    valores = [""] * quantidade_colunas

    for campo, indice in colunas.items():
        if campo in dados:
            valores[indice] = dados[campo]

    resultado = servico.spreadsheets().values().append(
        spreadsheetId=id_planilha,
        range='A1',
        valueInputOption='USER_ENTERED',
        body={'values': [valores]},
    ).execute()

    return resultado