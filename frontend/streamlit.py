import os
from datetime import datetime

import requests
import streamlit as st


API_URL = os.getenv("RAG_API_URL", "http://127.0.0.1:8000")
UPLOAD_ROLES = {"admin", "manager", "analyst"}
ADMIN_ROLES = {"admin", "manager"}
SUPPORTED_UPLOAD_TYPES = [
    "pdf",
    "docx",
    "pptx",
    "csv",
    "json",
    "txt",
    "md",
    "html",
    "htm",
    "xlsx",
    "xls",
    "png",
    "jpg",
    "jpeg",
    "tif",
    "tiff",
    "bmp",
    "webp",
]

DEFAULT_SESSION = {
    "page": "login",
    "token": None,
    "username": None,
    "role": None,
    "chat_id": None,
    "history": [],
    "users": {},
    "telemetry": None,
    "upload_notice": None,
    "uploaded_file_key": 0,
}

ENDPOINT_DOCS = [
    {"Method": "POST", "Endpoint": "/login", "Purpose": "Authenticate user and return JWT"},
    {"Method": "POST", "Endpoint": "/signup", "Purpose": "Create account"},
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
    {"Method": "GET", "Endpoint": "/users", "Purpose": "Admin/manager user list"},
    {"Method": "POST", "Endpoint": "/create-user", "Purpose": "Admin/manager user creation"},
    {"Method": "DELETE", "Endpoint": "/delete-user/{username}", "Purpose": "Admin/manager user deletion"},
]

st.set_page_config(
    page_title="RAG Workspace",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        max-width: 1280px;
    }
    section[data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb;
    }
    div[data-testid="stMetric"] {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 0.55rem 0.7rem;
        background: #fafafa;
    }
    div[data-testid="stExpander"] {
        border-radius: 8px;
    }
    .rag-muted {
        color: #6b7280;
        font-size: 0.88rem;
    }
    .rag-title {
        margin-bottom: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


for key, value in DEFAULT_SESSION.items():
    if key not in st.session_state:
        st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value


def reset_session():
    for key, value in DEFAULT_SESSION.items():
        st.session_state[key] = value.copy() if isinstance(value, (list, dict)) else value


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def error_detail(response):
    try:
        detail = response.json().get("detail")
        return detail or response.text or f"HTTP {response.status_code}"
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def format_time(timestamp):
    if not timestamp:
        return ""

    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def request(method, path, auth=True, timeout=60, **kwargs):
    headers = kwargs.pop("headers", {})
    if auth:
        headers.update(auth_headers())

    return requests.request(
        method,
        f"{API_URL}{path}",
        headers=headers,
        timeout=timeout,
        **kwargs,
    )


def switch_chat(chat_id):
    st.session_state.chat_id = chat_id
    st.session_state.history = []
    st.session_state.upload_notice = None
    st.session_state.uploaded_file_key += 1


def load_chats(show_errors=False):
    try:
        res = request("GET", "/get-chats")
        if res.status_code == 200:
            return res.json().get("chats", [])
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


def process_available_file(file_item, chat_id):
    try:
        res = request(
            "POST",
            "/process-existing-file",
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


def load_history(chat_id):
    try:
        res = request("GET", f"/chat-history/{chat_id}")
        if res.status_code == 200:
            st.session_state.history = res.json().get("history", []) or []
            return
        if res.status_code == 401:
            reset_session()
            st.rerun()
        st.warning(f"History unavailable: {error_detail(res)}")
    except requests.RequestException:
        st.warning("Could not load chat history.")


def count_assistant_turns(history):
    return sum(1 for message in history if message.get("role") == "assistant")


def login_page():
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.title("RAG Workspace")
        st.caption("Document-grounded chat")

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

        if submitted:
            try:
                res = request(
                    "POST",
                    "/login",
                    auth=False,
                    json={"username": username.strip(), "password": password},
                    timeout=30,
                )
            except requests.RequestException:
                st.error("Backend not reachable. Start FastAPI first.")
                return

            if res.status_code == 200:
                data = res.json()
                st.session_state.token = data["access_token"]
                st.session_state.username = username.strip()
                st.session_state.role = data["role"]
                st.session_state.page = "chat"
                switch_chat(None)
                st.rerun()

            st.error(error_detail(res))

        if st.button("Create Account", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()


def signup_page():
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.title("Create Account")

        with st.form("signup_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["admin", "manager", "analyst", "viewer", "guest"])
            submitted = st.form_submit_button("Signup", type="primary", use_container_width=True)

        if submitted:
            try:
                res = request(
                    "POST",
                    "/signup",
                    auth=False,
                    json={"username": username.strip(), "password": password, "role": role},
                    timeout=30,
                )
            except requests.RequestException:
                st.error("Backend not reachable.")
                return

            if res.status_code == 200:
                st.success("Account created.")
                st.session_state.page = "login"
                st.rerun()

            st.error(error_detail(res))

        if st.button("Back to Login", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()


def chat_controls(chat):
    with st.expander("Chat Settings", expanded=False):
        title = st.text_input("Title", value=chat.get("title", ""), key=f"title_{chat['chat_id']}")
        col1, col2 = st.columns([1, 1])

        if col1.button("Rename", use_container_width=True):
            res = request(
                "POST",
                "/rename-chat",
                json={"chat_id": chat["chat_id"], "title": title.strip() or "Untitled"},
            )
            if res.status_code == 200:
                st.success("Chat renamed.")
                st.rerun()
            st.error(error_detail(res))

        if col2.button("Delete", use_container_width=True):
            res = request("DELETE", f"/delete-chat/{chat['chat_id']}", timeout=30)
            if res.status_code == 200:
                switch_chat(None)
                st.rerun()
            st.error(error_detail(res))


def sidebar(chats, chat_id):
    with st.sidebar:
        st.markdown("### Workspace")
        st.write(f"{st.session_state.username} ({st.session_state.role})")

        if st.button("Logout", use_container_width=True):
            reset_session()
            st.rerun()

        st.divider()
        col1, col2 = st.columns([1, 1])
        col1.caption("Chats")
        if col2.button("New", use_container_width=True):
            new_chat_id = create_chat()
            if new_chat_id:
                switch_chat(new_chat_id)
                st.rerun()

        if not chats:
            st.caption("No chats yet.")

        for chat in chats:
            is_active = chat["chat_id"] == chat_id
            label = chat.get("title") or chat["chat_id"][:8]
            if st.button(
                label,
                key=f"chat_select_{chat['chat_id']}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                switch_chat(chat["chat_id"])
                st.rerun()

        st.divider()
        st.markdown("### Documents")
        files = load_files(chat_id)

        if files:
            for item in files:
                with st.container(border=True):
                    st.write(item.get("file", "Untitled file"))
                    owner = item.get("source_uploaded_by") or item.get("uploaded_by", "")
                    st.caption(f"{owner} | {item.get('role', '')}")
        else:
            st.caption("No documents in this chat.")

        if st.session_state.role in {"viewer", "guest"}:
            st.divider()
            st.markdown("### Available Files")
            available_files = load_available_files()

            if available_files:
                for item in available_files:
                    key = f"use_file_{item.get('file_key')}_{chat_id}"
                    with st.container(border=True):
                        st.write(item.get("file", "Untitled file"))
                        st.caption(
                            f"Uploaded by {item.get('uploaded_by', '')} "
                            f"({item.get('role', '')})"
                        )
                        if st.button("Use in this chat", key=key, use_container_width=True):
                            process_available_file(item, chat_id)
            else:
                st.caption("No uploaded files are available yet.")

        if st.session_state.role in ADMIN_ROLES:
            st.divider()
            st.markdown("### Audit")

            with st.expander("Uploaded Files", expanded=False):
                audit_files = load_audit("/audit/files", "files")
                if audit_files:
                    for item in audit_files[:25]:
                        st.write(item.get("file", "Untitled file"))
                        st.caption(
                            f"{item.get('uploaded_by', '')} | "
                            f"{item.get('role', '')} | "
                            f"{item.get('chat_id', '')}"
                        )
                else:
                    st.caption("No file records.")

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

    return files


def upload_panel(chat_id):
    if st.session_state.role not in UPLOAD_ROLES:
        return

    with st.expander("Ingestion", expanded=True):
        notice = st.session_state.upload_notice
        if notice:
            if notice.get("already_processed"):
                st.success(f"{notice['file']} is already ready for retrieval in this chat.")
            else:
                st.success(
                    f"{notice['file']} indexed successfully. "
                    f"{notice['chunks']} chunks are available for retrieval in this chat."
                )
            if st.button("Clear ingestion message"):
                st.session_state.upload_notice = None
                st.rerun()

        uploaded_file = st.file_uploader(
            "File",
            type=SUPPORTED_UPLOAD_TYPES,
            key=st.session_state.uploaded_file_key,
        )

        disabled = uploaded_file is None
        if st.button("Process Document", type="primary", disabled=disabled):
            file_type = uploaded_file.name.rsplit(".", 1)[-1].lower()

            with st.spinner("Extracting text, chunking, and indexing..."):
                try:
                    res = request(
                        "POST",
                        f"/upload?file_type={file_type}&chat_id={chat_id}",
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
                }
                st.session_state.uploaded_file_key += 1
                st.rerun()

            st.error(f"Processing failed: {error_detail(res)}")

        st.divider()
        url_to_ingest = st.text_input("Web URL")
        if st.button("Process URL", disabled=not url_to_ingest.strip()):
            with st.spinner("Fetching and indexing URL content..."):
                try:
                    res = request(
                        "POST",
                        "/ingest-url",
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


def render_history():
    for message in st.session_state.history:
        role = message.get("role", "assistant")
        content = message.get("content", "")

        with st.chat_message(role):
            st.write(content)

            sources = message.get("sources") or []
            if sources:
                with st.expander("Retrieved Sources", expanded=False):
                    for index, source in enumerate(sources, start=1):
                        st.markdown(f"**Source {index}**")
                        st.write(source)

            telemetry = message.get("telemetry") or {}
            if telemetry:
                with st.expander("Answer Telemetry", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Latency", f"{telemetry.get('latency_ms', 0)} ms")
                    col2.metric("Chunks", telemetry.get("retrieved_chunks", 0))
                    col3.metric("Tokens", telemetry.get("total_tokens", 0))

                    col4, col5, col6 = st.columns(3)
                    col4.metric("Precision@K", telemetry.get("retrieval_precision_at_k", 0))
                    col5.metric("Recall Proxy", telemetry.get("retrieval_recall_proxy", 0))
                    col6.metric("Relevance", telemetry.get("response_relevance", 0))


def query_panel(chat_id, files):
    query = st.chat_input("Ask a question about the indexed documents")
    if not query:
        return

    if not files:
        st.session_state.history.append({
            "role": "assistant",
            "content": "No documents are indexed in this chat yet.",
            "sources": [],
        })
        st.rerun()

    st.session_state.history.append({"role": "user", "content": query})

    with st.spinner("Retrieving context and generating answer..."):
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
        })
    else:
        st.session_state.history.append({
            "role": "assistant",
            "content": f"Query failed: {error_detail(res)}",
            "sources": [],
        })

    st.rerun()


def admin_panel():
    if st.session_state.role not in ADMIN_ROLES:
        return

    with st.expander("Admin", expanded=False):
        user_tab, telemetry_tab = st.tabs(["Users", "Telemetry"])

        with user_tab:
            if st.button("Refresh Users"):
                res = request("GET", "/users")
                if res.status_code == 200:
                    st.session_state.users = res.json().get("users", {})
                else:
                    st.error(error_detail(res))

            for username, data in st.session_state.users.items():
                col1, col2 = st.columns([4, 1])
                col1.write(f"{username} ({data.get('role', '')})")
                if col2.button("Delete", key=f"delete_user_{username}"):
                    res = request("DELETE", f"/delete-user/{username}", timeout=30)
                    if res.status_code == 200:
                        st.rerun()
                    st.error(error_detail(res))

            st.divider()
            with st.form("create_user_form"):
                new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                new_role = st.selectbox("Role", ["manager", "analyst", "viewer", "guest"])
                submitted = st.form_submit_button("Create User")

            if submitted:
                res = request(
                    "POST",
                    "/create-user",
                    json={
                        "username": new_username.strip(),
                        "password": new_password,
                        "role": new_role,
                    },
                )
                if res.status_code == 200:
                    st.success("User created.")
                else:
                    st.error(error_detail(res))

        with telemetry_tab:
            col_a, col_b = st.columns([1, 1])
            if col_a.button("Load Telemetry", type="primary"):
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

            if col_b.button("Clear Telemetry"):
                st.session_state.telemetry = None
                st.rerun()

            telemetry = st.session_state.telemetry
            if telemetry:
                if telemetry.get("error"):
                    st.warning(telemetry["error"])
                else:
                    metrics = telemetry.get("metrics", {})
                    health = telemetry.get("health", {})

                    st.markdown("#### System Health")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Status", health.get("status", "unknown"))
                    col2.metric("Service", health.get("service", "rag-app"))
                    col3.metric("Errors", metrics.get("errors", 0))

                    st.markdown("#### Usage Tracking")
                    col4, col5, col6, col7 = st.columns(4)
                    col4.metric("Queries", metrics.get("queries", 0))
                    col5.metric("Uploads", metrics.get("uploads", 0))
                    col6.metric("Tokens", metrics.get("total_tokens", 0))
                    col7.metric("Est. Cost", f"${metrics.get('estimated_cost_usd', 0):.6f}")

                    st.markdown("#### Model Performance")
                    col8, col9, col10 = st.columns(3)
                    col8.metric("Avg Latency", f"{metrics.get('avg_latency_ms', 0)} ms")
                    col9.metric("Last Latency", f"{metrics.get('last_latency_ms', 0)} ms")
                    col10.metric("Model Calls", sum(metrics.get("model_calls", {}).values()))

                    st.markdown("#### Retrieval & Evaluation")
                    retrieval = metrics.get("retrieval", {})
                    col11, col12, col13 = st.columns(3)
                    col11.metric("Avg Precision@K", retrieval.get("avg_precision_at_k", 0))
                    col12.metric("Avg Recall Proxy", retrieval.get("avg_recall_proxy", 0))
                    col13.metric("Avg Relevance", retrieval.get("avg_response_relevance", 0))

                    with st.expander("Raw Telemetry"):
                        st.json(metrics)

            st.markdown("#### Endpoint Flow")
            st.dataframe(
                ENDPOINT_DOCS,
                hide_index=True,
                use_container_width=True,
            )


def chat_page():
    chat_id = ensure_chat()
    chats = load_chats(show_errors=True)
    chat = active_chat(chats, chat_id)
    files = sidebar(chats, chat_id)
    load_history(chat_id)

    st.markdown(f"<h1 class='rag-title'>{chat.get('title', 'RAG Chat')}</h1>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='rag-muted'>Chat ID: {chat_id}</div>",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Documents", len(files))
    col2.metric("Messages", len(st.session_state.history))
    col3.metric("Answers", count_assistant_turns(st.session_state.history))

    chat_controls(chat)
    upload_panel(chat_id)
    admin_panel()

    st.divider()
    st.subheader("Conversation")

    if not files:
        st.info("No documents are indexed for this chat.")

    render_history()
    query_panel(chat_id, files)


if st.session_state.page == "login":
    login_page()
elif st.session_state.page == "signup":
    signup_page()
elif st.session_state.page == "chat":
    chat_page()
