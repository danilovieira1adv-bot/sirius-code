"""
Sirius — Integração Google
Suporta: Gmail, Google Drive, Google Calendar, Google Sheets
OAuth2 com refresh automático de tokens
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data/integrations")
TOKENS_DIR = DATA_DIR / "tokens"
CREDS_FILE = DATA_DIR / "credentials" / "google.json"
TOKEN_FILE = TOKENS_DIR / "google.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
TOKENS_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "credentials").mkdir(parents=True, exist_ok=True)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "https://sirius.retificapro.com.br/auth/google/callback"
)

def is_configured():
    return CREDS_FILE.exists()

def is_connected():
    if not TOKEN_FILE.exists():
        return False
    try:
        data = json.loads(TOKEN_FILE.read_text())
        return bool(data.get("access_token"))
    except Exception:
        return False

def get_status():
    status = {
        "configured": is_configured(),
        "connected": is_connected(),
        "email": None,
        "services": ["Gmail", "Drive", "Calendar", "Sheets"],
    }
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            status["email"] = data.get("email")
        except Exception:
            pass
    return status

def save_credentials(client_id, client_secret):
    try:
        creds = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        }
        CREDS_FILE.write_text(json.dumps(creds, indent=2))
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar credenciais: {e}")
        return False

def disconnect():
    try:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        return True
    except Exception:
        return False

def get_auth_url():
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(str(CREDS_FILE), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return auth_url

def handle_oauth_callback(code):
    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
        flow = Flow.from_client_secrets_file(str(CREDS_FILE), scopes=SCOPES, redirect_uri=REDIRECT_URI)
        flow.fetch_token(code=code)
        credentials = flow.credentials
        service = build("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()
        token_data = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or SCOPES),
            "email": user_info.get("email"),
            "connected_at": datetime.utcnow().isoformat(),
        }
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
        return {"success": True, "email": token_data["email"]}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _get_credentials():
    import requests as _req
    if not TOKEN_FILE.exists():
        raise RuntimeError("Google não conectado.")
    data = json.loads(TOKEN_FILE.read_text())
    # Sempre fazer refresh para garantir token válido
    r = _req.post("https://oauth2.googleapis.com/token", data={
        "client_id": data["client_id"],
        "client_secret": data["client_secret"],
        "refresh_token": data["refresh_token"],
        "grant_type": "refresh_token"
    })
    result = r.json()
    if "access_token" not in result:
        raise RuntimeError(f"Erro ao renovar token: {result}")
    data["access_token"] = result["access_token"]
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    print("[Google] Token refreshed via HTTP")
    from google.oauth2.credentials import Credentials
    return Credentials(
        token=data["access_token"],
        refresh_token=data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data.get("scopes", SCOPES),
    )

def gmail_send(to, subject, body, html=False):
    import base64
    from email.mime.text import MIMEText
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEText(body, "html" if html else "plain", "utf-8")
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"success": True, "message_id": result.get("id"), "to": to}
    except Exception as e:
        return {"success": False, "error": str(e)}

def gmail_read(query="is:unread", max_results=10):
    import base64
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("gmail", "v1", credentials=creds)
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", [])
        emails = []
        for msg in messages:
            full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            headers = {h["name"]: h["value"] for h in full["payload"].get("headers", [])}
            body = ""
            parts = full["payload"].get("parts", [])
            if parts:
                for part in parts:
                    if part.get("mimeType") == "text/plain":
                        data = part["body"].get("data", "")
                        body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                        break
            else:
                data = full["payload"]["body"].get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
            emails.append({"id": msg["id"], "from": headers.get("From",""), "subject": headers.get("Subject",""), "date": headers.get("Date",""), "snippet": full.get("snippet",""), "body": body[:2000]})
        return emails
    except Exception as e:
        return []

def drive_upload(filename, content, mime_type="text/plain"):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaInMemoryUpload
    try:
        creds = _get_credentials()
        service = build("drive", "v3", credentials=creds)
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type)
        result = service.files().create(body={"name": filename}, media_body=media, fields="id,name,webViewLink").execute()
        return {"success": True, "id": result.get("id"), "name": result.get("name"), "url": result.get("webViewLink")}
    except Exception as e:
        return {"success": False, "error": str(e)}

def drive_list(query="", max_results=20):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("drive", "v3", credentials=creds)
        q = f"name contains '{query}'" if query else "trashed = false"
        results = service.files().list(q=q, pageSize=max_results, fields="files(id,name,mimeType,modifiedTime,webViewLink,size)").execute()
        return results.get("files", [])
    except Exception as e:
        return []

def drive_read(file_id):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("drive", "v3", credentials=creds)
        content = service.files().get_media(fileId=file_id).execute()
        return content.decode("utf-8", errors="ignore")
    except Exception as e:
        return f"Erro: {e}"

def calendar_list_events(days_ahead=7):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        results = service.events().list(calendarId="primary", timeMin=now, timeMax=end, maxResults=50, singleEvents=True, orderBy="startTime").execute()
        events = []
        for e in results.get("items", []):
            start = e["start"].get("dateTime", e["start"].get("date"))
            events.append({"id": e.get("id"), "title": e.get("summary","Sem título"), "start": start, "end": e["end"].get("dateTime", e["end"].get("date")), "location": e.get("location",""), "description": e.get("description",""), "link": e.get("htmlLink","")})
        return events
    except Exception as e:
        return []

def calendar_create_event(title, start, end, description="", location=""):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)
        event = {"summary": title, "location": location, "description": description, "start": {"dateTime": start, "timeZone": "America/Sao_Paulo"}, "end": {"dateTime": end, "timeZone": "America/Sao_Paulo"}}
        result = service.events().insert(calendarId="primary", body=event).execute()
        return {"success": True, "id": result.get("id"), "title": result.get("summary"), "link": result.get("htmlLink")}
    except Exception as e:
        return {"success": False, "error": str(e)}

def calendar_delete_event(event_id):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def sheets_read(spreadsheet_id, range_name="Sheet1"):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        return result.get("values", [])
    except Exception as e:
        return []

def sheets_write(spreadsheet_id, range_name, values):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=range_name, valueInputOption="USER_ENTERED", body={"values": values}).execute()
        return {"success": True, "updated_cells": result.get("updatedCells"), "updated_range": result.get("updatedRange")}
    except Exception as e:
        return {"success": False, "error": str(e)}

def sheets_append(spreadsheet_id, range_name, values):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=range_name, valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body={"values": values}).execute()
        return {"success": True, "updated_cells": result.get("updates", {}).get("updatedCells")}
    except Exception as e:
        return {"success": False, "error": str(e)}

def sheets_create(title):
    from googleapiclient.discovery import build
    try:
        creds = _get_credentials()
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().create(body={"properties": {"title": title}}).execute()
        return {"success": True, "id": result.get("spreadsheetId"), "url": result.get("spreadsheetUrl"), "title": title}
    except Exception as e:
        return {"success": False, "error": str(e)}
