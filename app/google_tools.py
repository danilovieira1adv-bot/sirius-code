from google_integration import (
    gmail_send, gmail_read,
    drive_upload, drive_list, drive_read,
    calendar_list_events, calendar_create_event, calendar_delete_event,
    sheets_read, sheets_write, sheets_append, sheets_create,
    is_connected,
)

GOOGLE_TOOLS = [
    {"name": "gmail_send", "description": "Envia e-mail via Gmail", "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "html": {"type": "boolean", "default": False}}, "required": ["to", "subject", "body"]}},
    {"name": "gmail_read", "description": "Lê e-mails do Gmail. Queries: 'is:unread', 'from:email', 'subject:assunto'", "input_schema": {"type": "object", "properties": {"query": {"type": "string", "default": "is:unread"}, "max_results": {"type": "integer", "default": 10}}}},
    {"name": "drive_upload", "description": "Faz upload de arquivo para o Google Drive", "input_schema": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}, "mime_type": {"type": "string", "default": "text/plain"}}, "required": ["filename", "content"]}},
    {"name": "drive_list", "description": "Lista arquivos do Google Drive", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 20}}}},
    {"name": "drive_read", "description": "Lê conteúdo de arquivo do Drive pelo ID", "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}}, "required": ["file_id"]}},
    {"name": "calendar_list_events", "description": "Lista eventos do Google Calendar nos próximos N dias", "input_schema": {"type": "object", "properties": {"days_ahead": {"type": "integer", "default": 7}}}},
    {"name": "calendar_create_event", "description": "Cria evento no Google Calendar", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "start": {"type": "string", "description": "ISO 8601 ex: 2025-06-15T10:00:00-03:00"}, "end": {"type": "string"}, "description": {"type": "string"}, "location": {"type": "string"}}, "required": ["title", "start", "end"]}},
    {"name": "calendar_delete_event", "description": "Remove evento do Google Calendar", "input_schema": {"type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]}},
    {"name": "sheets_read", "description": "Lê dados de planilha Google Sheets", "input_schema": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range_name": {"type": "string", "default": "Sheet1"}}, "required": ["spreadsheet_id"]}},
    {"name": "sheets_write", "description": "Escreve dados em planilha Google Sheets", "input_schema": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range_name": {"type": "string"}, "values": {"type": "array"}}, "required": ["spreadsheet_id", "range_name", "values"]}},
    {"name": "sheets_append", "description": "Adiciona linhas ao final de planilha Google Sheets", "input_schema": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range_name": {"type": "string"}, "values": {"type": "array"}}, "required": ["spreadsheet_id", "range_name", "values"]}},
    {"name": "sheets_create", "description": "Cria nova planilha Google Sheets", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
]

GOOGLE_TOOL_NAMES = {t["name"] for t in GOOGLE_TOOLS}

def handle_google_tool(tool_name, tool_input):
    if not is_connected():
        return "Google não conectado. Acesse sirius.retificapro.com.br para conectar sua conta."
    try:
        if tool_name == "gmail_send":
            r = gmail_send(**tool_input)
            return f"E-mail enviado para {r['to']}" if r["success"] else f"Erro: {r['error']}"
        elif tool_name == "gmail_read":
            emails = gmail_read(**tool_input)
            if not emails: return "Nenhum e-mail encontrado."
            return "\n\n".join([f"De: {e['from']}\nAssunto: {e['subject']}\nData: {e['date']}\nTrecho: {e['snippet'][:150]}" for e in emails])
        elif tool_name == "drive_upload":
            r = drive_upload(**tool_input)
            return f"Arquivo '{r['name']}' enviado. URL: {r['url']}" if r["success"] else f"Erro: {r['error']}"
        elif tool_name == "drive_list":
            files = drive_list(**tool_input)
            if not files: return "Nenhum arquivo encontrado."
            return "\n".join([f"- {f['name']} (ID: {f['id']})" for f in files])
        elif tool_name == "drive_read":
            return drive_read(**tool_input)[:3000]
        elif tool_name == "calendar_list_events":
            events = calendar_list_events(**tool_input)
            if not events: return "Nenhum evento encontrado."
            return "\n\n".join([f"{e['title']}\nInício: {e['start']}\nFim: {e['end']}\nLocal: {e.get('location') or '-'}" for e in events])
        elif tool_name == "calendar_create_event":
            r = calendar_create_event(**tool_input)
            return f"Evento '{r['title']}' criado. Link: {r['link']}" if r["success"] else f"Erro: {r['error']}"
        elif tool_name == "calendar_delete_event":
            r = calendar_delete_event(**tool_input)
            return "Evento removido." if r["success"] else f"Erro: {r['error']}"
        elif tool_name == "sheets_read":
            rows = sheets_read(**tool_input)
            if not rows: return "Planilha vazia."
            return "\n".join([" | ".join(str(c) for c in row) for row in rows])
        elif tool_name == "sheets_write":
            r = sheets_write(**tool_input)
            return f"{r['updated_cells']} células atualizadas." if r["success"] else f"Erro: {r['error']}"
        elif tool_name == "sheets_append":
            r = sheets_append(**tool_input)
            return f"Linhas adicionadas: {r['updated_cells']} células." if r["success"] else f"Erro: {r['error']}"
        elif tool_name == "sheets_create":
            r = sheets_create(**tool_input)
            return f"Planilha '{r['title']}' criada. URL: {r['url']}" if r["success"] else f"Erro: {r['error']}"
        return f"Ferramenta desconhecida: {tool_name}"
    except Exception as e:
        return f"Erro em {tool_name}: {e}"
