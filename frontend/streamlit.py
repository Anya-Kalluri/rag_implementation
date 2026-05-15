"""Streamlit frontend for the RAG application.

This file contains the browser UI for authentication, chat workspaces, file/URL
ingestion, reusable sources, audit views, metrics, and question answering. It
talks to the FastAPI backend through the endpoints listed below.
"""

import os
import json
from datetime import datetime
from urllib.parse import unquote

import requests
import streamlit as st
import streamlit.components.v1 as components


API_URL = os.getenv("RAG_API_URL", "http://127.0.0.1:8000")

# Auth values are mirrored into browser cookies so a page refresh can restore
# the Streamlit session without forcing the user through login again.
AUTH_ACCESS_COOKIE = "rag_access_token"
AUTH_REFRESH_COOKIE = "rag_refresh_token"
AUTH_USERNAME_COOKIE = "rag_username"
AUTH_ROLE_COOKIE = "rag_role"
LOGOUT_QUERY_PARAM = "logged_out"
AUTH_COOKIE_MAX_AGE_SECONDS = int(os.getenv("RAG_AUTH_COOKIE_MAX_AGE_SECONDS", 7 * 24 * 60 * 60))
UPLOAD_ROLES = {"admin", "manager", "analyst"}
DEFAULT_SHARED_ROLES = ["manager", "analyst", "viewer", "guest"]
SHARED_LIBRARY_ROLES = set(DEFAULT_SHARED_ROLES)
ADMIN_ROLES = {"admin"}
USER_MANAGEMENT_ROLES = {"admin", "manager"}
MANAGER_MANAGED_ROLES = ["analyst", "viewer", "guest"]
ADMIN_MANAGED_ROLES = ["manager", "analyst", "viewer", "guest"]

# Kept in sync with backend.ingestion.pipeline.SUPPORTED_FILE_TYPES so the UI
# only offers extensions that the backend can actually ingest.
SUPPORTED_UPLOAD_TYPES = [
    "pdf", "docx", "pptx", "csv", "json", "txt", "md", "html", "htm",
    "xlsx", "xls", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp",
]

# Streamlit session_state keys used across the app. Each rerun starts from this
# shape, then request handlers and UI callbacks update individual values.
DEFAULT_SESSION = {
    "page": "login",
    "token": None,
    "refresh_token": None,
    "username": None,
    "role": None,
    "logged_out": False,
    "chat_id": None,
    "history": [],
    "users": {},
    "telemetry": None,
    "upload_notice": None,
    "uploaded_file_key": 0,
    "editing_chat_id": None,
}

# Rendered in the UI as a lightweight API reference for operators/admins.
ENDPOINT_DOCS = [
    {"Method": "POST", "Endpoint": "/login", "Purpose": "Authenticate user and return JWT access and refresh tokens"},
    {"Method": "POST", "Endpoint": "/refresh-token", "Purpose": "Exchange a valid refresh token for a new JWT pair"},
    {"Method": "POST", "Endpoint": "/change-password", "Purpose": "Change password for the logged-in user"},
    {"Method": "GET", "Endpoint": "/get-chats", "Purpose": "List chats for current user"},
    {"Method": "GET", "Endpoint": "/health", "Purpose": "System health monitoring"},
    {"Method": "POST", "Endpoint": "/create-chat", "Purpose": "Create a document chat workspace"},
    {"Method": "POST", "Endpoint": "/rename-chat", "Purpose": "Rename active chat"},
    {"Method": "DELETE", "Endpoint": "/delete-chat/{chat_id}", "Purpose": "Delete chat metadata"},
    {"Method": "POST", "Endpoint": "/upload", "Purpose": "Extract, chunk, embed, and index a file"},
    {"Method": "POST", "Endpoint": "/ingest-url", "Purpose": "Scrape URL, chunk, embed, and index text"},
    {"Method": "GET", "Endpoint": "/files?chat_id=...", "Purpose": "List indexed files for active chat"},
    {"Method": "POST", "Endpoint": "/query", "Purpose": "Retrieve context and generate answer"},
    {"Method": "GET", "Endpoint": "/chat-history/{chat_id}", "Purpose": "Load saved conversation"},
    {"Method": "GET", "Endpoint": "/metrics", "Purpose": "Read telemetry counters"},
    {"Method": "GET", "Endpoint": "/users", "Purpose": "Admin-only user list"},
    {"Method": "POST", "Endpoint": "/create-user", "Purpose": "Admin-only user creation"},
    {"Method": "DELETE", "Endpoint": "/delete-user/{username}", "Purpose": "Admin-only user deletion"},
]


# === Inline SVG icons (Lucide-style) ===
def _icon(path_d, size=16, stroke=1.75):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px;">{path_d}</svg>'
    )

IC_CHATS = _icon('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>')
IC_DOC = _icon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/>')
IC_CLOUD = _icon('<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 0 1 0 9z"/>')
IC_SHIELD = _icon('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>')
IC_MSG = _icon('<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>')
IC_FOLDER = _icon('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>')
IC_UPLOAD = _icon('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>')
IC_GLOBE = _icon('<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>')
IC_DATABASE = _icon('<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>')
IC_ZAP = _icon('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>')

ROLE_STYLES = {
    "admin":   {"bg": "#FEF2F2", "fg": "#991B1B", "bd": "#FECACA"},
    "manager": {"bg": "#EFF6FF", "fg": "#1E40AF", "bd": "#BFDBFE"},
    "analyst": {"bg": "#EEF2FF", "fg": "#4338CA", "bd": "#C7D2FE"},
    "viewer":  {"bg": "#F1F5F9", "fg": "#334155", "bd": "#E2E8F0"},
    "guest":   {"bg": "#FFFBEB", "fg": "#92400E", "bd": "#FDE68A"},
}


def role_pill(role):
    if not role:
        return ""
    s = ROLE_STYLES.get(role.lower(), ROLE_STYLES["viewer"])
    return (
        f'<span class="rag-role-pill" style="background:{s["bg"]};color:{s["fg"]};'
        f'border:1px solid {s["bd"]};">{role.upper()}</span>'
    )


st.set_page_config(
    page_title="RAG Workspace",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        --primary: #6366F1;
        --primary-dark: #4F46E5;
        --primary-darker: #4338CA;
        --primary-light: #EEF2FF;
        --primary-lighter: #F5F3FF;
        --bg: #F8FAFC;
        --surface: #FFFFFF;
        --surface-2: #FAFAFA;
        --surface-hover: #F8FAFC;
        --border: #E5E7EB;
        --border-strong: #CBD5E1;
        --text-1: #0F172A;
        --text-2: #475569;
        --text-3: #64748B;
        --text-4: #94A3B8;
        --success: #10B981;
        --warning: #F59E0B;
        --error: #EF4444;
        --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
        --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
        --shadow-md: 0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -1px rgba(15, 23, 42, 0.04);
        --shadow-lg: 0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -2px rgba(15, 23, 42, 0.04);
        --radius-sm: 6px;
        --radius-md: 8px;
        --radius-lg: 12px;
        --radius-xl: 16px;
    }

    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    .main, .block-container, p, span, div, label, input, textarea, button, h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    .material-symbols-rounded, .material-symbols-outlined, .material-symbols-sharp,
    .material-icons, .material-icons-outlined, .material-icons-round,
    [class*="material-symbols"], [class*="material-icons"],
    [data-testid="stIconMaterial"], span[data-testid="stIconMaterial"],
    [data-testid="stExpanderToggleIcon"],
    [data-testid="collapsedControl"] *, [data-testid="stSidebarCollapseButton"] *,
    button[kind="header"] * {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
                     'Material Icons Rounded', 'Material Icons' !important;
        font-feature-settings: 'liga' !important;
        font-weight: normal !important;
    }

    .stApp { background: var(--bg); }
    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; height: 0; }

    .block-container { padding-top: 1.5rem; padding-bottom: 4rem; max-width: 1360px; }

    section[data-testid="stSidebar"] {
        background: var(--surface);
        border-right: 1px solid var(--border);
    }
    section[data-testid="stSidebar"] > div { padding-top: 0.85rem; }

    h1, h2, h3, h4, h5, h6 {
        color: var(--text-1) !important;
        letter-spacing: -0.02em !important;
        font-weight: 700 !important;
    }
    h1 { font-size: 1.625rem !important; line-height: 1.2 !important; }
    h2 { font-size: 1.25rem !important; }
    h3 { font-size: 1rem !important; font-weight: 600 !important; }
    h5 { font-size: 0.95rem !important; font-weight: 600 !important; }

    /* === Native metric cards === */
    div[data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 0.95rem 1.1rem 0.85rem 1.1rem;
        box-shadow: var(--shadow-xs);
        transition: all 0.18s ease;
        position: relative;
        overflow: hidden;
    }
    div[data-testid="stMetric"]::before {
        content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
        background: linear-gradient(180deg, var(--primary), var(--primary-darker));
        opacity: 0; transition: opacity 0.18s ease;
    }
    div[data-testid="stMetric"]:hover {
        border-color: #C7D2FE;
        box-shadow: var(--shadow-md);
        transform: translateY(-1px);
    }
    div[data-testid="stMetric"]:hover::before { opacity: 1; }
    div[data-testid="stMetric"] label[data-testid="stMetricLabel"] p {
        color: var(--text-3) !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.1em !important;
        margin-bottom: 0.35rem;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--text-1) !important;
        font-weight: 700 !important;
        font-size: 1.625rem !important;
        line-height: 1.1 !important;
        letter-spacing: -0.02em;
    }

    /* === Buttons === */
    .stButton > button, .stDownloadButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        border-radius: var(--radius-md) !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.15s ease !important;
        min-height: 38px;
    }
    .stButton > button[kind="primary"],
    .stButton > button[kind="primaryFormSubmit"],
    div[data-testid="stFormSubmitButton"] > button[kind="primary"],
    div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"],
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%) !important;
        background-color: #4F46E5 !important;
        color: #FFFFFF !important;
        border: 1px solid transparent !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 2px rgba(79, 70, 229, 0.3),
                    inset 0 1px 0 rgba(255,255,255,0.18) !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[kind="primaryFormSubmit"]:hover,
    div[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"]:hover,
    button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 16px rgba(79, 70, 229, 0.4) !important;
        filter: brightness(1.05);
    }
    .stButton > button[kind="secondary"],
    .stButton > button[kind="secondaryFormSubmit"],
    div[data-testid="stFormSubmitButton"] > button[kind="secondary"],
    div[data-testid="stFormSubmitButton"] > button[kind="secondaryFormSubmit"],
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-secondaryFormSubmit"] {
        background: var(--surface) !important;
        color: var(--text-2) !important;
        border: 1px solid var(--border) !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stButton > button[kind="secondaryFormSubmit"]:hover,
    div[data-testid="stFormSubmitButton"] > button[kind="secondary"]:hover,
    div[data-testid="stFormSubmitButton"] > button[kind="secondaryFormSubmit"]:hover,
    button[data-testid="stBaseButton-secondary"]:hover,
    button[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
        border-color: #C7D2FE !important;
        color: var(--primary-dark) !important;
        background: var(--primary-lighter) !important;
    }
    .stButton > button:disabled { opacity: 0.5; cursor: not-allowed; }

    /* === Expanders === */
    div[data-testid="stExpander"] {
        border-radius: var(--radius-lg) !important;
        border: 1px solid var(--border) !important;
        background: var(--surface) !important;
        overflow: hidden;
        box-shadow: var(--shadow-xs);
    }
    div[data-testid="stExpander"] details > summary {
        padding: 0.85rem 1.1rem !important;
        font-weight: 600 !important;
        color: var(--text-1) !important;
        font-size: 0.9rem !important;
    }
    div[data-testid="stExpander"] details > summary:hover { background: var(--surface-hover); }

    /* === Chat messages === */
    div[data-testid="stChatMessage"] {
        background: var(--surface);
        border-radius: var(--radius-lg);
        padding: 1rem 1.2rem;
        margin-bottom: 0.7rem;
        border: 1px solid var(--border);
        box-shadow: var(--shadow-xs);
    }
    div[data-testid="stChatMessage"]:has(div[data-testid="chatAvatarIcon-user"]) {
        background: linear-gradient(135deg, var(--surface) 0%, var(--primary-lighter) 100%);
        border-color: #E0E7FF;
    }
    div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] {
        background: linear-gradient(135deg, #6366F1, #4F46E5) !important;
        color: white !important;
    }
    div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"] {
        background: linear-gradient(135deg, #94A3B8, #64748B) !important;
        color: white !important;
    }

    /* === Chat input === */
    div[data-testid="stChatInput"] {
        border-radius: var(--radius-lg) !important;
        border: 1px solid var(--border) !important;
        box-shadow: var(--shadow-md) !important;
    }
    div[data-testid="stChatInput"]:focus-within {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.12), var(--shadow-md) !important;
    }

    /* === Inputs === */
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    div[data-baseweb="select"] > div {
        border-radius: var(--radius-md) !important;
        border-color: var(--border) !important;
        transition: all 0.15s ease;
        background: var(--surface) !important;
    }
    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="textarea"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12) !important;
    }

    div[data-testid="stAlert"] {
        border-radius: var(--radius-md) !important;
        border-left-width: 3px !important;
        padding: 0.75rem 1rem !important;
        font-size: 0.875rem;
    }

    div[data-baseweb="tab-list"] {
        gap: 0.1rem !important;
        border-bottom: 1px solid var(--border) !important;
    }
    button[data-baseweb="tab"] {
        border-radius: 8px 8px 0 0 !important;
        font-weight: 500 !important;
        color: var(--text-3) !important;
        padding: 0.55rem 1.1rem !important;
        font-size: 0.88rem !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--primary-dark) !important;
        font-weight: 600 !important;
    }
    div[data-baseweb="tab-highlight"] { background: var(--primary-dark) !important; }

    hr { border-color: var(--border) !important; margin: 1.1rem 0 !important; }
    [data-testid="stCaptionContainer"], .stCaption {
        color: var(--text-3) !important; font-size: 0.8rem !important;
    }

    [data-testid="stFileUploader"] section {
        border-radius: var(--radius-lg) !important;
        border: 1.5px dashed var(--border-strong) !important;
        background: var(--surface-2) !important;
        transition: all 0.15s ease;
        padding: 1.25rem !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: var(--primary) !important;
        background: var(--primary-lighter) !important;
    }

    div[data-testid="stForm"] {
        border-radius: var(--radius-lg);
        border: 1px solid var(--border);
        background: var(--surface);
        padding: 1.15rem;
        box-shadow: var(--shadow-xs);
    }

    div[data-testid="stDataFrame"] {
        border-radius: var(--radius-md);
        overflow: hidden;
        border: 1px solid var(--border);
    }

    .stSpinner > div { border-top-color: var(--primary) !important; }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: var(--radius-lg) !important;
        border-color: var(--border) !important;
        box-shadow: var(--shadow-xs) !important;
    }

    section[data-testid="stSidebar"] .stButton > button {
        min-height: 34px;
        font-size: 0.83rem !important;
    }

    /* === Custom components === */
    .rag-brand {
        display: flex; align-items: center; gap: 0.7rem;
        margin: 0.2rem 0 1rem 0;
    }
    .rag-brand-logo {
        width: 34px; height: 34px; border-radius: 9px;
        background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%);
        color: white; display: flex; align-items: center; justify-content: center;
        font-weight: 800; font-size: 1.05rem;
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3),
                    inset 0 1px 0 rgba(255,255,255,0.2);
    }
    .rag-brand-text {
        font-weight: 700; color: var(--text-1); font-size: 1.02rem;
        letter-spacing: -0.02em; line-height: 1.1;
    }
    .rag-brand-sub {
        font-size: 0.65rem; color: var(--text-3);
        margin-top: 0.15rem; letter-spacing: 0.12em; font-weight: 600;
    }

    .rag-user-card {
        display: flex; align-items: center; gap: 0.7rem;
        padding: 0.7rem 0.8rem;
        background: linear-gradient(135deg, var(--surface) 0%, var(--primary-lighter) 100%);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        margin-bottom: 0.85rem;
    }
    .rag-user-avatar {
        width: 36px; height: 36px; border-radius: 10px;
        background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%);
        color: white; display: flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 0.95rem; flex-shrink: 0;
        box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);
    }
    .rag-user-meta { flex: 1; min-width: 0; }
    .rag-user-name {
        font-weight: 600; color: var(--text-1); font-size: 0.9rem; line-height: 1.2;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }

    .rag-role-pill {
        display: inline-block;
        padding: 0.1rem 0.5rem;
        border-radius: 999px;
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.08em;
    }

    .rag-section-header {
        display: flex; align-items: center; gap: 0.45rem;
        font-size: 0.68rem; font-weight: 700; color: var(--text-3);
        text-transform: uppercase; letter-spacing: 0.12em;
        margin: 0.85rem 0 0.55rem 0;
    }
    .rag-section-count {
        margin-left: auto;
        background: var(--surface-2);
        color: var(--text-2);
        border: 1px solid var(--border);
        padding: 0.05rem 0.45rem;
        border-radius: 999px;
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0;
    }

    .rag-hero {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-xl);
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: var(--shadow-xs);
        position: relative;
        overflow: hidden;
    }
    .rag-hero::before {
        content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
        background: linear-gradient(90deg, #6366F1, #8B5CF6, #6366F1);
        background-size: 200% 100%;
        animation: rag-shimmer 6s linear infinite;
    }
    @keyframes rag-shimmer {
        0% { background-position: 0% 0; }
        100% { background-position: 200% 0; }
    }
    .rag-hero-row {
        display: flex; align-items: flex-start; justify-content: space-between;
        gap: 1.5rem; flex-wrap: wrap;
    }
    .rag-hero-left { min-width: 0; flex: 1; }
    .rag-hero-right {
        display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;
    }
    .rag-status-pill {
        display: inline-flex; align-items: center; gap: 0.4rem;
        padding: 0.28rem 0.7rem;
        background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0;
        border-radius: 999px;
        font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .rag-dot-pulse {
        width: 7px; height: 7px; border-radius: 999px; background: #10B981;
        animation: rag-pulse 2s infinite;
        display: inline-block;
    }
    @keyframes rag-pulse {
        0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.55); }
        70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
        100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
    .rag-hero-title {
        margin: 0.65rem 0 0.2rem 0 !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: var(--text-1) !important;
        letter-spacing: -0.025em !important;
        line-height: 1.2 !important;
    }
    .rag-hero-meta {
        display: flex; align-items: center; gap: 0.5rem;
        color: var(--text-3); font-size: 0.78rem;
        margin-top: 0.2rem; flex-wrap: wrap;
    }
    .rag-hero-id {
        background: var(--surface-2);
        border: 1px solid var(--border);
        padding: 0.12rem 0.5rem;
        border-radius: var(--radius-sm);
        color: var(--text-2);
        font-size: 0.72rem;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
    }
    .rag-meta-sep { color: var(--text-4); }

    .rag-section-title {
        display: flex; align-items: center; gap: 0.55rem;
        font-size: 0.95rem; font-weight: 600; color: var(--text-1);
        margin: 1.25rem 0 0.65rem 0;
        letter-spacing: -0.01em;
    }
    .rag-section-title svg { color: var(--primary-dark); }
    .rag-section-title .rag-subcount {
        background: var(--primary-light);
        color: var(--primary-darker);
        border: 1px solid #E0E7FF;
        font-size: 0.68rem; font-weight: 600;
        padding: 0.08rem 0.5rem; border-radius: 999px;
    }

    .rag-doc-item {
        display: flex; align-items: center; gap: 0.55rem;
        padding: 0.55rem 0.7rem;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        margin-bottom: 0.4rem;
        transition: all 0.12s ease;
    }
    .rag-doc-item:hover {
        border-color: #C7D2FE;
        background: var(--primary-lighter);
    }
    .rag-doc-icon {
        width: 28px; height: 28px; border-radius: 7px;
        background: var(--primary-light); color: var(--primary-darker);
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
    }
    .rag-doc-meta { flex: 1; min-width: 0; }
    .rag-doc-name {
        font-size: 0.82rem; font-weight: 500; color: var(--text-1);
        line-height: 1.2;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .rag-doc-sub {
        font-size: 0.68rem; color: var(--text-3); margin-top: 0.1rem;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }

    .rag-empty {
        text-align: center;
        padding: 1rem 0.5rem;
        color: var(--text-3);
    }
    .rag-empty-icon {
        display: inline-flex;
        width: 40px; height: 40px; border-radius: 11px;
        background: var(--primary-light); color: var(--primary-dark);
        align-items: center; justify-content: center;
        margin-bottom: 0.5rem;
    }
    .rag-empty-title {
        font-weight: 600; color: var(--text-1); font-size: 0.85rem;
        margin-bottom: 0.15rem;
    }
    .rag-empty-sub {
        font-size: 0.72rem; color: var(--text-3);
    }

    .rag-cite-row {
        display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;
        margin: 0.4rem 0 0.75rem 0;
    }
    .rag-cite-chip {
        display: inline-flex; align-items: center; justify-content: center;
        min-width: 22px; height: 22px; padding: 0 0.5rem;
        background: var(--primary-light); color: var(--primary-darker);
        border: 1px solid #E0E7FF;
        border-radius: 999px;
        font-size: 0.7rem; font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
    }
    .rag-cite-label {
        font-size: 0.72rem; color: var(--text-3); font-weight: 500;
        margin-left: 0.25rem;
    }

    .rag-source-num {
        width: 24px; height: 24px; flex-shrink: 0;
        background: var(--primary-light); color: var(--primary-darker);
        border: 1px solid #E0E7FF;
        border-radius: 7px;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 0.72rem;
        font-family: 'JetBrains Mono', monospace;
        margin-bottom: 0.35rem;
    }

    .rag-api-status {
        display: flex; align-items: center; gap: 0.5rem;
        padding: 0.55rem 0.75rem;
        margin-top: 0.75rem;
        background: var(--surface-2);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        font-size: 0.7rem; color: var(--text-3);
        font-family: 'JetBrains Mono', monospace;
    }
    .rag-api-status-dot {
        width: 6px; height: 6px; border-radius: 999px;
        background: #10B981;
        box-shadow: 0 0 0 3px rgba(16,185,129,0.15);
        flex-shrink: 0;
    }

    .rag-login-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-xl);
        padding: 2rem 2rem 1.75rem 2rem;
        box-shadow: var(--shadow-lg);
        position: relative;
        overflow: hidden;
    }
    .rag-login-card::before {
        content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
        background: linear-gradient(90deg, #6366F1, #8B5CF6, #EC4899);
    }
    .rag-login-brand {
        display: flex; align-items: center; gap: 0.85rem; margin-bottom: 1.5rem;
    }
    .rag-login-logo {
        width: 48px; height: 48px; border-radius: 14px;
        background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%);
        color: white; display: flex; align-items: center; justify-content: center;
        font-weight: 800; font-size: 1.35rem;
        box-shadow: 0 6px 18px rgba(79, 70, 229, 0.35),
                    inset 0 1px 0 rgba(255,255,255,0.2);
    }
    .rag-login-name {
        font-size: 1.35rem; font-weight: 700; color: var(--text-1);
        letter-spacing: -0.025em; line-height: 1.1;
    }
    .rag-login-sub {
        font-size: 0.8rem; color: var(--text-3); margin-top: 0.2rem;
    }
    .rag-login-title {
        font-size: 1.05rem; font-weight: 600; color: var(--text-1);
        margin-bottom: 0.2rem;
    }
    .rag-login-desc {
        font-size: 0.83rem; color: var(--text-3); margin-bottom: 1rem;
    }
    .rag-trust-row {
        display: flex; align-items: center; gap: 1rem;
        justify-content: center; margin-top: 1.3rem;
        font-size: 0.72rem; color: var(--text-4);
        flex-wrap: wrap;
    }
    .rag-trust-item {
        display: inline-flex; align-items: center; gap: 0.3rem;
    }

    .rag-telem-row {
        display: grid; grid-template-columns: repeat(3, 1fr);
        gap: 0.5rem; margin: 0.5rem 0;
    }
    .rag-telem {
        background: var(--surface-2); border: 1px solid var(--border);
        border-radius: var(--radius-sm); padding: 0.5rem 0.65rem;
    }
    .rag-telem-label {
        font-size: 0.62rem; color: var(--text-3); text-transform: uppercase;
        letter-spacing: 0.08em; font-weight: 600;
    }
    .rag-telem-value {
        font-size: 0.95rem; color: var(--text-1); font-weight: 700;
        margin-top: 0.1rem;
        font-family: 'JetBrains Mono', monospace;
    }

    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 999px; }
    ::-webkit-scrollbar-thumb:hover { background: #9CA3AF; }
    </style>
    """,
    unsafe_allow_html=True,
)


for key, value in DEFAULT_SESSION.items():
    if key not in st.session_state:
        st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value


# ============================================================
# Helpers (UNCHANGED logic from original)
# ============================================================

def reset_session(reload_page=False):
    for key, value in DEFAULT_SESSION.items():
        st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value
    clear_auth_cookies(reload_page=reload_page)


def cookie_value(name):
    value = st.context.cookies.get(name)
    return unquote(value) if value else None


def sync_auth_cookies():
    if not st.session_state.token or not st.session_state.refresh_token:
        return
    cookies = {
        AUTH_ACCESS_COOKIE: st.session_state.token,
        AUTH_REFRESH_COOKIE: st.session_state.refresh_token,
        AUTH_USERNAME_COOKIE: st.session_state.username or "",
        AUTH_ROLE_COOKIE: st.session_state.role or "",
    }
    components.html(
        f"""
        <script>
        const cookies = {json.dumps(cookies)};
        let targetDocument = document;
        try {{ targetDocument = window.parent.document; }} catch (error) {{}}
        for (const [name, value] of Object.entries(cookies)) {{
            targetDocument.cookie =
                `${{name}}=${{encodeURIComponent(value)}}; path=/; max-age={AUTH_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
        }}
        </script>
        """,
        height=0,
    )


def clear_auth_cookies(reload_page=False):
    components.html(
        f"""
        <script>
        let targetDocument = document;
        let targetWindow = window;
        try {{
            targetDocument = window.parent.document;
            targetWindow = window.parent;
        }} catch (error) {{}}
        for (const name of {json.dumps([AUTH_ACCESS_COOKIE, AUTH_REFRESH_COOKIE, AUTH_USERNAME_COOKIE, AUTH_ROLE_COOKIE])}) {{
            targetDocument.cookie = `${{name}}=; path=/; max-age=0; SameSite=Lax`;
        }}
        if ({json.dumps(reload_page)}) {{
            setTimeout(() => targetWindow.location.reload(), 50);
        }}
        </script>
        """,
        height=0,
    )


def is_logout_route():
    return st.query_params.get(LOGOUT_QUERY_PARAM) == "1"


def mark_logout_route():
    st.query_params[LOGOUT_QUERY_PARAM] = "1"


def clear_logout_route():
    if LOGOUT_QUERY_PARAM in st.query_params:
        del st.query_params[LOGOUT_QUERY_PARAM]


def logout():
    reset_session()
    st.session_state.logged_out = True
    st.session_state.page = "login"
    mark_logout_route()
    st.rerun()
    st.stop()


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def error_detail(response):
    try:
        detail = response.json().get("detail")
        if isinstance(detail, dict):
            return (
                detail.get("message")
                or detail.get("detail")
                or response.text
                or f"HTTP {response.status_code}"
            )
        return detail or response.text or f"HTTP {response.status_code}"
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def guest_query_notice(guest_usage):
    if not guest_usage:
        return ""
    used = guest_usage.get("used", 0)
    limit = guest_usage.get("limit", 5)
    remaining = guest_usage.get("remaining", max(limit - used, 0))
    if remaining <= 0:
        return f"Guest query {used} of {limit} used. No more guest queries available."
    return f"Guest query {used} of {limit} used. {remaining} guest queries remaining."


def error_guest_usage(response):
    try:
        detail = response.json().get("detail")
    except Exception:
        return None
    if isinstance(detail, dict):
        return detail.get("guest_usage")
    return None


def format_time(timestamp):
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def refresh_access_token():
    if not st.session_state.refresh_token:
        return False
    try:
        res = request(
            "POST", "/refresh-token", auth=False,
            json={"refresh_token": st.session_state.refresh_token},
            timeout=30,
        )
    except requests.RequestException:
        return False
    if res.status_code != 200:
        reset_session()
        return False
    data = res.json()
    st.session_state.token = data["access_token"]
    st.session_state.refresh_token = data["refresh_token"]
    st.session_state.username = data.get("username") or st.session_state.username
    st.session_state.role = data["role"]
    return True


def request(method, path, auth=True, timeout=60, **kwargs):
    headers = kwargs.pop("headers", {})
    if auth:
        headers.update(auth_headers())
    response = requests.request(
        method, f"{API_URL}{path}", headers=headers, timeout=timeout, **kwargs,
    )
    if auth and response.status_code == 401 and refresh_access_token():
        headers.update(auth_headers())
        response = requests.request(
            method, f"{API_URL}{path}", headers=headers, timeout=timeout, **kwargs,
        )
    return response


def restore_auth_session():
    if st.session_state.logged_out or is_logout_route():
        st.session_state.logged_out = True
        st.session_state.page = "login"
        clear_auth_cookies()
        return
    if st.session_state.token:
        sync_auth_cookies()
        return
    access_token = cookie_value(AUTH_ACCESS_COOKIE)
    refresh_token = cookie_value(AUTH_REFRESH_COOKIE)
    if not access_token and not refresh_token:
        return
    st.session_state.token = access_token
    st.session_state.refresh_token = refresh_token
    st.session_state.username = cookie_value(AUTH_USERNAME_COOKIE)
    st.session_state.role = cookie_value(AUTH_ROLE_COOKIE)
    st.session_state.page = "chat"
    if not st.session_state.token:
        refresh_access_token()
    sync_auth_cookies()


def switch_chat(chat_id):
    st.session_state.chat_id = chat_id
    st.session_state.history = []
    st.session_state.upload_notice = None
    st.session_state.editing_chat_id = None
    st.session_state.uploaded_file_key += 1


def load_chats(show_errors=False):
    try:
        res = request("GET", "/get-chats")
        if res.status_code == 200:
            chats = res.json().get("chats", [])
            return sorted(
                chats,
                key=lambda chat: (
                    float(chat.get("created_at") or 0),
                    int(chat.get("position") or 0),
                ),
                reverse=True,
            )
        if show_errors:
            st.error(error_detail(res))
    except requests.RequestException:
        if show_errors:
            st.error("Backend not reachable.")
    return []


def create_chat():
    res = request("POST", "/create-chat")
    if res.status_code == 200:
        return res.json()["chat_id"]
    st.error(f"Could not create chat: {error_detail(res)}")
    return None


def ensure_chat():
    if st.session_state.chat_id:
        return st.session_state.chat_id
    chats = load_chats()
    if chats:
        st.session_state.chat_id = chats[0]["chat_id"]
        return st.session_state.chat_id
    chat_id = create_chat()
    if not chat_id:
        st.stop()
    st.session_state.chat_id = chat_id
    return chat_id


def active_chat(chats, chat_id):
    for chat in chats:
        if chat["chat_id"] == chat_id:
            return chat
    return {"chat_id": chat_id, "title": "Current Chat"}


def load_files(chat_id):
    try:
        res = request("GET", f"/files?chat_id={chat_id}")
        if res.status_code == 200:
            return res.json().get("files", [])
        st.sidebar.warning(f"Files unavailable: {error_detail(res)}")
    except requests.RequestException:
        st.sidebar.warning("Could not load files.")
    return []


def load_available_files():
    try:
        res = request("GET", "/available-files")
        if res.status_code == 200:
            return res.json().get("files", [])
        st.sidebar.warning(f"Available files unavailable: {error_detail(res)}")
    except requests.RequestException:
        st.sidebar.warning("Could not load available files.")
    return []


def load_audit(path, key):
    try:
        res = request("GET", path)
        if res.status_code == 200:
            return res.json().get(key, [])
        st.sidebar.warning(error_detail(res))
    except requests.RequestException:
        st.sidebar.warning("Could not load audit data.")
    return []


def load_users(show_errors=True):
    try:
        res = request("GET", "/users")
    except requests.RequestException:
        if show_errors:
            st.error("Could not load users. Backend is not reachable.")
        return {}
    if res.status_code == 200:
        users = res.json().get("users", {})
        st.session_state.users = users
        return users
    if show_errors:
        st.error(error_detail(res))
    return {}


def process_available_file(file_item, chat_id):
    role = (st.session_state.role or "").strip().lower()
    owner = file_item.get("uploaded_by") == st.session_state.username
    allowed_roles = file_item.get("shared_roles") or (DEFAULT_SHARED_ROLES if file_item.get("is_shared") else [])
    if role != "admin" and not owner and (not file_item.get("is_shared") or role not in allowed_roles):
        st.sidebar.warning("No permission to query this file.")
        return
    try:
        res = request(
            "POST", "/process-existing-file",
            json={"file_key": file_item.get("file_key"), "chat_id": chat_id},
            timeout=180,
        )
    except requests.RequestException:
        st.sidebar.error("Backend not reachable.")
        return
    if res.status_code == 200:
        data = res.json()
        st.session_state.upload_notice = {
            "file": data.get("file", file_item.get("file", "Selected file")),
            "chunks": data.get("chunks", 0),
            "chat_id": data.get("chat_id", chat_id),
            "already_processed": data.get("already_processed", False),
        }
        st.rerun()
    st.sidebar.error(f"Could not prepare file: {error_detail(res)}")


def available_file_label(item):
    filename = item.get("file", "Untitled file")
    owner = item.get("uploaded_by", "unknown")
    role = item.get("role", "")
    return f"{filename} | {owner} | {role}".strip(" |")


def load_history(chat_id):
    try:
        res = request("GET", f"/chat-history/{chat_id}")
        if res.status_code == 200:
            st.session_state.history = res.json().get("history", []) or []
            return
        if res.status_code == 401:
            reset_session()
            st.warning("Session expired. Please log in again.")
            st.stop()
        st.warning(f"History unavailable: {error_detail(res)}")
    except requests.RequestException:
        st.warning("Could not load chat history.")


def count_assistant_turns(history):
    return sum(1 for message in history if message.get("role") == "assistant")


def section_header(icon_html, label, count=None):
    count_html = f'<span class="rag-section-count">{count}</span>' if count is not None else ""
    st.markdown(
        f'<div class="rag-section-header">{icon_html}<span>{label}</span>{count_html}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# UI — Login
# ============================================================

def login_page():
    left, center, right = st.columns([1, 1.3, 1])
    with center:
        st.markdown("<div style='margin-top:3.5rem;'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <div style="display: inline-flex; align-items: center; gap: 0.85rem; margin-bottom: 1.5rem;">
                    <div class="rag-login-logo">R</div>
                    <div style="text-align: left;">
                        <div class="rag-login-name">RAG Workspace</div>
                        <div class="rag-login-sub">Document-grounded conversational AI</div>
                    </div>
                </div>
                <div class="rag-login-title">Sign in to your workspace</div>
                <div class="rag-login-desc">Use your credentials to access the secured document workspace.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="your.username")
            password = st.text_input("Password", type="password", placeholder="••••••••••")
            submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

        st.markdown(
            f"""
            <div class="rag-trust-row">
                <span class="rag-trust-item">{IC_SHIELD}<span>JWT secured</span></span>
                <span class="rag-trust-item">{IC_DATABASE}<span>Encrypted index</span></span>
                <span class="rag-trust-item">{IC_ZAP}<span>Low-latency retrieval</span></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if submitted:
            try:
                res = request(
                    "POST", "/login", auth=False,
                    json={"username": username.strip(), "password": password},
                    timeout=30,
                )
            except requests.RequestException:
                st.error("Backend not reachable. Start FastAPI first.")
                return

            if res.status_code == 200:
                data = res.json()
                st.session_state.token = data["access_token"]
                st.session_state.refresh_token = data["refresh_token"]
                st.session_state.username = data.get("username") or username.strip()
                st.session_state.role = data["role"]
                st.session_state.logged_out = False
                clear_logout_route()
                st.session_state.page = "chat"
                switch_chat(None)
                st.rerun()

            st.error(error_detail(res))


# ============================================================
# UI — Chat actions
# ============================================================

def rename_chat(chat_id, title):
    res = request(
        "POST", "/rename-chat",
        json={"chat_id": chat_id, "title": title.strip() or "Untitled"},
    )
    if res.status_code == 200:
        st.session_state.editing_chat_id = None
        st.rerun()
    st.error(error_detail(res))


def remove_chat(chat_id):
    res = request("DELETE", f"/delete-chat/{chat_id}", timeout=30)
    if res.status_code == 200:
        if st.session_state.chat_id == chat_id:
            switch_chat(None)
        st.session_state.editing_chat_id = None
        st.rerun()
    st.error(error_detail(res))


# ============================================================
# UI — Sidebar
# ============================================================

def sidebar(chats, chat_id):
    with st.sidebar:
        # Brand
        st.markdown(
            """
            <div class="rag-brand">
                <div class="rag-brand-logo">R</div>
                <div>
                    <div class="rag-brand-text">RAG Workspace</div>
                    <div class="rag-brand-sub">DOCUMENT INTELLIGENCE</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # User card with role pill
        initial = (st.session_state.username or "U")[0].upper()
        st.markdown(
            f"""
            <div class="rag-user-card">
                <div class="rag-user-avatar">{initial}</div>
                <div class="rag-user-meta">
                    <div class="rag-user-name">{st.session_state.username or "User"}</div>
                    <div style="margin-top: 0.25rem;">{role_pill(st.session_state.role or "viewer")}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Change Password
        with st.expander("Change Password", expanded=False):
            with st.form("change_password_form"):
                current_password = st.text_input("Current password", type="password")
                new_password = st.text_input("New password", type="password")
                confirm_password = st.text_input("Confirm new password", type="password")
                submitted = st.form_submit_button("Update Password", use_container_width=True, type="primary")

            if submitted:
                if new_password != confirm_password:
                    st.error("New passwords do not match.")
                elif current_password.strip() == new_password.strip():
                    st.error("Enter a different password from your current password.")
                else:
                    try:
                        res = request(
                            "POST", "/change-password",
                            json={
                                "current_password": current_password,
                                "new_password": new_password,
                            },
                            timeout=30,
                        )
                    except requests.RequestException:
                        st.error("Backend not reachable.")
                    else:
                        if res.status_code == 200:
                            st.success("Password changed.")
                        else:
                            st.error(error_detail(res))

        if st.button("Sign Out", use_container_width=True):
            logout()

        st.markdown("<hr style='margin: 0.9rem 0;'/>", unsafe_allow_html=True)

        # Chats section
        section_header(IC_CHATS, "Chats", count=len(chats))
        if st.button("+ New chat", use_container_width=True, type="primary", key="sidebar_new_chat"):
            new_chat_id = create_chat()
            if new_chat_id:
                switch_chat(new_chat_id)
                st.rerun()

        st.markdown("<div style='margin-top: 0.4rem;'></div>", unsafe_allow_html=True)

        if not chats:
            st.markdown(
                f'<div class="rag-empty"><div class="rag-empty-icon">{IC_MSG}</div>'
                f'<div class="rag-empty-title">No chats yet</div>'
                f'<div class="rag-empty-sub">Create one to get started.</div></div>',
                unsafe_allow_html=True,
            )

        for chat in chats:
            is_active = chat["chat_id"] == chat_id
            label = chat.get("title") or chat["chat_id"][:8]
            chat_col, edit_col, delete_col = st.columns([6, 1, 1])

            if chat_col.button(
                label,
                key=f"chat_select_{chat['chat_id']}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                switch_chat(chat["chat_id"])
                st.rerun()

            if edit_col.button("✎", key=f"chat_edit_{chat['chat_id']}", help="Rename chat"):
                st.session_state.editing_chat_id = chat["chat_id"]
                st.rerun()

            if delete_col.button("×", key=f"chat_delete_{chat['chat_id']}", help="Delete chat"):
                remove_chat(chat["chat_id"])

            if st.session_state.editing_chat_id == chat["chat_id"]:
                with st.form(f"rename_chat_form_{chat['chat_id']}"):
                    new_title = st.text_input(
                        "New chat name",
                        value=label,
                        key=f"rename_chat_title_{chat['chat_id']}",
                    )
                    save_col, cancel_col = st.columns([1, 1])
                    save = save_col.form_submit_button("Save", type="primary", use_container_width=True)
                    cancel = cancel_col.form_submit_button("Cancel", use_container_width=True)
                if save:
                    rename_chat(chat["chat_id"], new_title)
                if cancel:
                    st.session_state.editing_chat_id = None
                    st.rerun()

        st.markdown("<hr style='margin: 0.9rem 0;'/>", unsafe_allow_html=True)

        # Indexed Documents
        files = load_files(chat_id)
        section_header(IC_DOC, "Indexed Documents", count=len(files))

        if files:
            for item in files:
                owner = item.get("source_uploaded_by") or item.get("uploaded_by", "")
                fname = item.get("file", "Untitled file")
                fname_safe = (fname[:38] + "…") if len(fname) > 39 else fname
                meta_sub = f"{owner} · {item.get('role', '')}".strip(" ·")
                st.markdown(
                    f"""
                    <div class="rag-doc-item">
                        <div class="rag-doc-icon">{IC_DOC}</div>
                        <div class="rag-doc-meta">
                            <div class="rag-doc-name" title="{fname}">{fname_safe}</div>
                            <div class="rag-doc-sub">{meta_sub}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f'<div class="rag-empty"><div class="rag-empty-icon">{IC_FOLDER}</div>'
                f'<div class="rag-empty-title">No documents indexed</div>'
                f'<div class="rag-empty-sub">Upload to start querying.</div></div>',
                unsafe_allow_html=True,
            )

        available_files = None

        if st.session_state.role == "admin":
            st.markdown("<hr style='margin: 0.9rem 0;'/>", unsafe_allow_html=True)
            available_files = load_available_files()
            section_header(IC_CLOUD, "All Uploaded Files", count=len(available_files))
            if available_files:
                selected_file_key = st.selectbox(
                    "Choose a file to query",
                    [item.get("file_key") for item in available_files],
                    format_func=lambda key: available_file_label(
                        next((item for item in available_files if item.get("file_key") == key), {})
                    ),
                    label_visibility="collapsed",
                    key=f"admin_file_picker_{chat_id}",
                )
                selected_file = next(
                    (item for item in available_files if item.get("file_key") == selected_file_key),
                    None,
                )
                if selected_file and st.button("Use selected file in this chat", key=f"admin_use_file_{chat_id}", use_container_width=True):
                    process_available_file(selected_file, chat_id)
            else:
                st.caption("No uploaded files yet.")

        # Available shared files
        if st.session_state.role in SHARED_LIBRARY_ROLES:
            st.markdown("<hr style='margin: 0.9rem 0;'/>", unsafe_allow_html=True)
            if available_files is None:
                available_files = load_available_files()
            section_header(IC_CLOUD, "Shared Library", count=len(available_files))

            if available_files:
                for item in available_files:
                    key = f"use_file_{item.get('file_key')}_{chat_id}"
                    fname = item.get("file", "Untitled file")
                    fname_safe = (fname[:32] + "…") if len(fname) > 33 else fname
                    with st.container(border=True):
                        st.markdown(
                            f"""
                            <div style="display:flex; align-items:center; gap:0.55rem; margin-bottom: 0.55rem;">
                                <div class="rag-doc-icon">{IC_CLOUD}</div>
                                <div style="flex:1; min-width:0;">
                                    <div class="rag-doc-name" title="{fname}">{fname_safe}</div>
                                    <div class="rag-doc-sub">By {item.get('uploaded_by', '')} · {item.get('role', '')}</div>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if not item.get("is_shared"):
                            st.caption("Restricted")
                        if st.button("Use in this chat", key=key, use_container_width=True):
                            process_available_file(item, chat_id)
            else:
                st.caption("No shared files yet.")

        # Audit
        if st.session_state.role in ADMIN_ROLES:
            st.markdown("<hr style='margin: 0.9rem 0;'/>", unsafe_allow_html=True)
            section_header(IC_SHIELD, "Audit")

            with st.expander("Manager and Analyst Files", expanded=False):
                if available_files is None:
                    available_files = load_available_files()
                staff_files = [
                    item for item in available_files
                    if item.get("role") in {"manager", "analyst"}
                ]
                if staff_files:
                    for item in staff_files[:25]:
                        label = available_file_label(item)
                        if st.button(label, key=f"audit_use_file_{item.get('file_key')}_{chat_id}", use_container_width=True):
                            process_available_file(item, chat_id)
                else:
                    st.caption("No manager or analyst file records.")

            with st.expander("Queries", expanded=False):
                queries = load_audit("/audit/queries", "queries")
                if queries:
                    for item in queries[:25]:
                        st.write(item.get("query", ""))
                        st.caption(
                            f"{item.get('user', '')} | "
                            f"{item.get('chat_id', '')} | "
                            f"{format_time(item.get('time'))}"
                        )
                else:
                    st.caption("No query records.")

        # API status footer
        host = API_URL.replace("http://", "").replace("https://", "")
        st.markdown(
            f"""
            <div class="rag-api-status">
                <span class="rag-api-status-dot"></span>
                <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{host}</span>
                <span style="color: var(--text-4);">v1</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return files


# ============================================================
# UI — Ingestion
# ============================================================

def upload_panel(chat_id):
    if st.session_state.role not in UPLOAD_ROLES:
        return

    st.markdown(
        f'<div class="rag-section-title">{IC_UPLOAD}<span>Ingest Documents</span>'
        f'<span class="rag-subcount">UPLOAD &amp; INDEX</span></div>',
        unsafe_allow_html=True,
    )

    with st.expander("Open ingestion panel", expanded=True):
        notice = st.session_state.upload_notice
        if notice:
            if notice.get("already_processed"):
                st.success(f"**{notice['file']}** is already indexed for this chat.")
            else:
                st.success(
                    f"**{notice['file']}** indexed successfully · "
                    f"{notice['chunks']} chunks now retrievable."
                )
            if st.button("Dismiss"):
                st.session_state.upload_notice = None
                st.rerun()

        col_file, col_share = st.columns([2, 1])
        with col_file:
            uploaded_file = st.file_uploader(
                "Drop a file or browse",
                type=SUPPORTED_UPLOAD_TYPES,
                key=st.session_state.uploaded_file_key,
            )
        with col_share:
            st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
            st.markdown("**Sharing**")
            if st.session_state.role == "admin":
                share_manager = st.checkbox("Let managers view", value=True)
                share_analyst = st.checkbox("Let analysts view", value=True)
                share_viewer_guest = st.checkbox("Let viewers and guests view", value=True)
                st.caption("Choose one or more roles for the shared library.")
            elif st.session_state.role == "manager":
                share_analyst = st.checkbox("Let analysts view", value=True)
                share_viewer_guest = st.checkbox("Let viewers and guests view", value=True)
                st.caption("Choose who can use this from the shared library.")
            elif st.session_state.role == "analyst":
                share_viewer_guest = st.checkbox("Let viewers and guests view", value=True)
                st.caption("Choose whether viewers and guests can use this file.")
            else:
                share_file = st.radio(
                    "Allow other users to query this file?",
                    ["Yes", "No"],
                    horizontal=False,
                    index=0,
                    label_visibility="collapsed",
                )
                st.caption("Yes - visible in the shared library")

        disabled = uploaded_file is None
        process_col, _ = st.columns([1, 2])
        if process_col.button("Process Document", type="primary", disabled=disabled, use_container_width=True):
            file_type = uploaded_file.name.rsplit(".", 1)[-1].lower()
            if st.session_state.role == "admin":
                shared_roles = []
                if share_manager:
                    shared_roles.append("manager")
                if share_analyst:
                    shared_roles.append("analyst")
                if share_viewer_guest:
                    shared_roles.extend(["viewer", "guest"])
                is_shared = bool(shared_roles)
            elif st.session_state.role == "manager":
                shared_roles = []
                if share_analyst:
                    shared_roles.append("analyst")
                if share_viewer_guest:
                    shared_roles.extend(["viewer", "guest"])
                is_shared = bool(shared_roles)
            elif st.session_state.role == "analyst":
                shared_roles = ["viewer", "guest"] if share_viewer_guest else []
                is_shared = bool(shared_roles)
            else:
                is_shared = share_file == "Yes"
                shared_roles = DEFAULT_SHARED_ROLES if is_shared else []

            with st.spinner("Extracting · Chunking · Embedding · Indexing"):
                try:
                    res = request(
                        "POST",
                        "/upload",
                        params={
                            "file_type": file_type,
                            "chat_id": chat_id,
                            "is_shared": str(is_shared).lower(),
                            "shared_roles": ",".join(shared_roles),
                        },
                        files={
                            "file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                uploaded_file.type,
                            )
                        },
                        timeout=180,
                    )
                except requests.RequestException:
                    st.error("Upload failed. Backend is not reachable.")
                    return

            if res.status_code == 200:
                data = res.json()
                st.session_state.upload_notice = {
                    "file": data.get("file", uploaded_file.name),
                    "chunks": data.get("chunks", 0),
                    "chat_id": data.get("chat_id", chat_id),
                    "is_shared": data.get("is_shared", is_shared),
                    "shared_roles": data.get("shared_roles", shared_roles),
                }
                st.session_state.uploaded_file_key += 1
                st.rerun()

            st.error(f"Processing failed: {error_detail(res)}")

        st.markdown("<hr style='margin: 1rem 0 0.85rem 0;'/>", unsafe_allow_html=True)
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:0.5rem; '
            f'margin-bottom:0.5rem; color: var(--text-2); font-weight: 500; font-size: 0.88rem;">'
            f'{IC_GLOBE}<span>Or ingest from URL</span></div>',
            unsafe_allow_html=True,
        )
        url_col, btn_col = st.columns([3, 1])
        with url_col:
            url_to_ingest = st.text_input(
                "Web URL",
                placeholder="https://example.com/article",
                label_visibility="collapsed",
            )
        with btn_col:
            url_clicked = st.button(
                "Fetch & Index",
                disabled=not url_to_ingest.strip(),
                use_container_width=True,
            )

        if url_clicked:
            with st.spinner("Fetching and indexing URL content…"):
                try:
                    res = request(
                        "POST", "/ingest-url",
                        json={"url": url_to_ingest.strip(), "chat_id": chat_id},
                        timeout=180,
                    )
                except requests.RequestException:
                    st.error("URL ingestion failed. Backend is not reachable.")
                    return

            if res.status_code == 200:
                data = res.json()
                st.session_state.upload_notice = {
                    "file": data.get("url", url_to_ingest.strip()),
                    "chunks": data.get("chunks", 0),
                    "chat_id": data.get("chat_id", chat_id),
                }
                st.rerun()

            st.error(f"URL processing failed: {error_detail(res)}")


# ============================================================
# UI — Conversation
# ============================================================

def render_history():
    for message in st.session_state.history:
        role = message.get("role", "assistant")
        content = message.get("content", "")

        with st.chat_message(role):
            sources = message.get("sources") or []
            telemetry = message.get("telemetry") or {}

            if role == "assistant" and sources:
                chips = "".join(
                    f'<span class="rag-cite-chip">{i + 1}</span>'
                    for i in range(len(sources))
                )
                plural = "s" if len(sources) != 1 else ""
                st.markdown(
                    f'<div class="rag-cite-row">{chips}'
                    f'<span class="rag-cite-label">{len(sources)} source{plural} cited</span></div>',
                    unsafe_allow_html=True,
                )

            st.write(content)

            if sources:
                plural = "s" if len(sources) != 1 else ""
                with st.expander(f"View {len(sources)} retrieved source{plural}", expanded=False):
                    for index, source in enumerate(sources, start=1):
                        st.markdown(
                            f'<div class="rag-source-num">{index}</div>',
                            unsafe_allow_html=True,
                        )
                        st.write(source)
                        if index < len(sources):
                            st.markdown("<hr style='margin: 0.5rem 0;'/>", unsafe_allow_html=True)

            if telemetry:
                if telemetry.get("error"):
                    st.warning(f"Generation note: {telemetry['error']}")
                with st.expander("Answer telemetry", expanded=False):
                    st.markdown(
                        f"""
                        <div class="rag-telem-row">
                            <div class="rag-telem"><div class="rag-telem-label">Latency</div>
                                <div class="rag-telem-value">{telemetry.get('latency_ms', 0)} ms</div></div>
                            <div class="rag-telem"><div class="rag-telem-label">Chunks</div>
                                <div class="rag-telem-value">{telemetry.get('retrieved_chunks', 0)}</div></div>
                            <div class="rag-telem"><div class="rag-telem-label">Tokens</div>
                                <div class="rag-telem-value">{telemetry.get('total_tokens', 0)}</div></div>
                        </div>
                        <div class="rag-telem-row">
                            <div class="rag-telem"><div class="rag-telem-label">Precision@K</div>
                                <div class="rag-telem-value">{telemetry.get('retrieval_precision_at_k', 0)}</div></div>
                            <div class="rag-telem"><div class="rag-telem-label">Recall</div>
                                <div class="rag-telem-value">{telemetry.get('retrieval_recall_proxy', 0)}</div></div>
                            <div class="rag-telem"><div class="rag-telem-label">Relevance</div>
                                <div class="rag-telem-value">{telemetry.get('response_relevance', 0)}</div></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            notice = guest_query_notice(message.get("guest_usage"))
            if notice:
                st.info(notice)


def query_panel(chat_id, files):
    query = st.chat_input("Ask a question about the indexed documents…")
    if not query:
        return

    if not files:
        st.session_state.history.append({
            "role": "assistant",
            "content": "No documents are indexed in this chat yet. Upload a file to begin.",
            "sources": [],
        })
        st.rerun()

    st.session_state.history.append({"role": "user", "content": query})

    with st.spinner("Retrieving context and generating answer…"):
        try:
            res = request("POST", "/query", json={"query": query, "chat_id": chat_id}, timeout=180)
        except requests.RequestException:
            st.session_state.history.append({
                "role": "assistant",
                "content": "Backend not reachable.",
                "sources": [],
            })
            st.rerun()

    if res.status_code == 200:
        data = res.json()
        st.session_state.history.append({
            "role": "assistant",
            "content": data.get("answer", "No response generated."),
            "sources": data.get("sources", []),
            "telemetry": data.get("telemetry", {}),
            "guest_usage": data.get("guest_usage"),
        })
    else:
        guest_usage = error_guest_usage(res)
        detail = error_detail(res)
        if guest_usage:
            detail = "No more guest queries available."
        st.session_state.history.append({
            "role": "assistant",
            "content": f"Query failed: {detail}",
            "sources": [],
            "guest_usage": guest_usage,
        })

    st.rerun()


# ============================================================
# UI — Admin
# ============================================================

def admin_panel():
    if st.session_state.role not in USER_MANAGEMENT_ROLES:
        return

    title = "Admin Dashboard" if st.session_state.role == "admin" else "Manager Dashboard"
    manageable_roles = (
        ADMIN_MANAGED_ROLES
        if st.session_state.role == "admin"
        else MANAGER_MANAGED_ROLES
    )

    st.markdown(
        f'<div class="rag-section-title">{IC_SHIELD}<span>{title}</span>'
        f'<span class="rag-subcount">{st.session_state.role.upper()}</span></div>',
        unsafe_allow_html=True,
    )

    with st.expander("Open dashboard", expanded=False):
        user_tab, telemetry_tab = st.tabs(["Users", "Telemetry"])

        with user_tab:
            st.caption(
                "Managers can view, create, and delete analyst, viewer, and guest users."
                if st.session_state.role == "manager"
                else "Admins can manage managers, analysts, viewers, and guests."
            )

            if not st.session_state.users:
                load_users(show_errors=False)

            refresh_col, _ = st.columns([1, 4])
            if refresh_col.button("Refresh", use_container_width=True):
                load_users()

            st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

            for username, data in st.session_state.users.items():
                role = data.get("role", "")
                with st.container(border=True):
                    col1, col2, col3 = st.columns([4, 2, 1])
                    col1.markdown(f"**{username}**")
                    col2.markdown(role_pill(role), unsafe_allow_html=True)
                    can_delete = role in manageable_roles and username != st.session_state.username
                    if col3.button("Delete", key=f"delete_user_{username}", disabled=not can_delete, use_container_width=True):
                        res = request("DELETE", f"/delete-user/{username}", timeout=30)
                        if res.status_code == 200:
                            st.success("User deleted.")
                            load_users(show_errors=False)
                            st.rerun()
                        st.error(error_detail(res))

            st.markdown("<hr style='margin: 0.85rem 0;'/>", unsafe_allow_html=True)
            st.markdown("**Create new user**")
            with st.form("create_user_form"):
                c1, c2 = st.columns(2)
                new_username = c1.text_input("Username")
                new_password = c2.text_input("Password", type="password")
                new_role = st.selectbox("Role", manageable_roles)
                submitted = st.form_submit_button("Create User", type="primary")

            if submitted:
                res = request(
                    "POST", "/create-user",
                    json={
                        "username": new_username.strip(),
                        "password": new_password,
                        "role": new_role,
                    },
                )
                if res.status_code == 200:
                    st.success("User created.")
                    load_users(show_errors=False)
                    st.rerun()
                else:
                    st.error(error_detail(res))

        with telemetry_tab:
            col_a, col_b, _ = st.columns([1, 1, 3])
            if col_a.button("Load", type="primary", use_container_width=True):
                metrics_res = request("GET", "/metrics")
                health_res = request("GET", "/health", auth=False)
                st.session_state.telemetry = {
                    "metrics": metrics_res.json() if metrics_res.status_code == 200 else None,
                    "health": health_res.json() if health_res.status_code == 200 else None,
                    "error": (
                        None
                        if metrics_res.status_code == 200
                        else error_detail(metrics_res)
                    ),
                }

            if col_b.button("Clear", use_container_width=True):
                st.session_state.telemetry = None
                st.rerun()

            telemetry = st.session_state.telemetry
            if telemetry:
                if telemetry.get("error"):
                    st.warning(telemetry["error"])
                else:
                    metrics = telemetry.get("metrics", {})
                    health = telemetry.get("health", {})

                    st.markdown("##### System Health")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Status", health.get("status", "unknown"))
                    col2.metric("Service", health.get("service", "rag-app"))
                    col3.metric("Errors", metrics.get("errors", 0))

                    st.markdown("##### Usage")
                    col4, col5, col6, col7 = st.columns(4)
                    col4.metric("Queries", metrics.get("queries", 0))
                    col5.metric("Uploads", metrics.get("uploads", 0))
                    col6.metric("Tokens", metrics.get("total_tokens", 0))
                    col7.metric("Est. Cost", f"${metrics.get('estimated_cost_usd', 0):.6f}")

                    st.markdown("##### Performance")
                    col8, col9, col10 = st.columns(3)
                    col8.metric("Avg Latency", f"{metrics.get('avg_latency_ms', 0)} ms")
                    col9.metric("Last Latency", f"{metrics.get('last_latency_ms', 0)} ms")
                    col10.metric("Model Calls", sum(metrics.get("model_calls", {}).values()))

                    st.markdown("##### Retrieval Quality")
                    retrieval = metrics.get("retrieval", {})
                    col11, col12, col13 = st.columns(3)
                    col11.metric("Avg Precision@K", retrieval.get("avg_precision_at_k", 0))
                    col12.metric("Avg Recall", retrieval.get("avg_recall_proxy", 0))
                    col13.metric("Avg Relevance", retrieval.get("avg_response_relevance", 0))

                    with st.expander("Raw telemetry payload"):
                        st.json(metrics)

            st.markdown("##### API Reference")
            st.dataframe(
                ENDPOINT_DOCS,
                hide_index=True,
                use_container_width=True,
            )


# ============================================================
# UI — Chat page
# ============================================================

def chat_page():
    chat_id = ensure_chat()
    chats = load_chats(show_errors=True)
    chat = active_chat(chats, chat_id)
    files = sidebar(chats, chat_id)
    load_history(chat_id)

    title_text = chat.get("title", "RAG Chat") or "RAG Chat"
    n_files = len(files)
    n_answers = count_assistant_turns(st.session_state.history)
    f_plural = "s" if n_files != 1 else ""
    a_plural = "s" if n_answers != 1 else ""

    st.markdown(
        f"""
        <div class="rag-hero">
            <div class="rag-hero-row">
                <div class="rag-hero-left">
                    <span class="rag-status-pill">
                        <span class="rag-dot-pulse"></span> ACTIVE SESSION
                    </span>
                    <div class="rag-hero-title">{title_text}</div>
                    <div class="rag-hero-meta">
                        <span class="rag-hero-id">{chat_id}</span>
                        <span class="rag-meta-sep">·</span>
                        <span>{n_files} document{f_plural}</span>
                        <span class="rag-meta-sep">·</span>
                        <span>{n_answers} answer{a_plural}</span>
                    </div>
                </div>
                <div class="rag-hero-right">
                    {role_pill(st.session_state.role or "")}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Documents", n_files)
    col2.metric("Messages", len(st.session_state.history))
    col3.metric("Answers", n_answers)

    upload_panel(chat_id)
    admin_panel()

    st.markdown(
        f'<div class="rag-section-title">{IC_MSG}<span>Conversation</span>'
        f'<span class="rag-subcount">{len(st.session_state.history)} MESSAGES</span></div>',
        unsafe_allow_html=True,
    )

    if not files:
        st.markdown(
            f"""
            <div style="background: var(--surface); border: 1px dashed var(--border-strong);
                        border-radius: 12px; padding: 1.5rem; text-align: center; margin-bottom: 0.75rem;">
                <div style="display: inline-flex; width: 48px; height: 48px; border-radius: 12px;
                            background: var(--primary-light); color: var(--primary-dark);
                            align-items: center; justify-content: center; margin-bottom: 0.7rem;">
                    {IC_FOLDER}
                </div>
                <div style="font-weight: 600; color: var(--text-1); font-size: 1rem;">
                    No documents indexed yet
                </div>
                <div style="font-size: 0.85rem; color: var(--text-3); margin-top: 0.3rem;">
                    Use the ingestion panel above to upload a file or fetch from a URL.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_history()
    query_panel(chat_id, files)


# ============================================================
# Routing
# ============================================================

restore_auth_session()

if st.session_state.page == "chat":
    chat_page()
else:
    login_page()
