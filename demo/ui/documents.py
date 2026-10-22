"""File-browser style UI for document folders and PDF uploads."""
import requests
import streamlit as st
import json

BASE_URL = "http://localhost:8000"
FOLDER_COLUMNS = 3

def _show_request_error(message: str, exc: requests.RequestException) -> None:
    detail = ""
    if exc.response is not None:
        try:
            detail = exc.response.json().get("detail", "")
        except ValueError:
            detail = exc.response.text
    st.error(f"{message}: {detail or exc}")

def _get_folders():
    response = requests.get(f"{BASE_URL}/folders", timeout=10)
    response.raise_for_status()
    return response.json().get("folders", [])

def _get_documents(folder_id: str):
    response = requests.get(
        f"{BASE_URL}/folders/{folder_id}/documents",
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("documents", [])

@st.dialog("Create a folder")
def _create_folder_dialog():
    with st.form("create_folder_form", clear_on_submit=True):
        name = st.text_input("Folder name", max_chars=80, placeholder="e.g. Research papers")
        submitted = st.form_submit_button("Create folder", type="primary")

    if submitted:
        try:
            response = requests.post(
                f"{BASE_URL}/folders",
                json={"name": name},
                timeout=10,
            )
            response.raise_for_status()
            st.session_state.pop("selected_folder_id", None)
            st.toast(f"Created folder: {name.strip()}")
            st.rerun()
        except requests.RequestException as exc:
            _show_request_error("Could not create folder", exc)

@st.dialog("Rename folder")
def _rename_folder_dialog(folder_id: str, current_name: str):
    with st.form(f"rename_folder_form_{folder_id}"):
        name = st.text_input(
            "Folder name",
            value=current_name,
            max_chars=80,
        )
        submitted = st.form_submit_button("Save name", type="primary")

    if submitted:
        try:
            response = requests.patch(
                f"{BASE_URL}/folders/{folder_id}",
                json={"name": name},
                timeout=10,
            )
            response.raise_for_status()
            st.toast("Folder renamed")
            st.rerun()
        except requests.RequestException as exc:
            _show_request_error("Could not rename folder", exc)

@st.dialog("Delete folder")
def _delete_folder_dialog(folder_id: str):
    with st.form(f"delete_folder_form_{folder_id}"):
        st.text("All documents in the folder will be deleted. Are you sure?")
        submitted = st.form_submit_button("Confirm", type="primary")

    if submitted:
        try:
            response = requests.delete(
                f"{BASE_URL}/folders/{folder_id}",
                json={"name": folder_id},
                timeout=10,
            )
            response.raise_for_status()
            st.toast("Folder deleted")
            st.rerun()
        except requests.RequestException as exc:
            _show_request_error("Could not delete folder", exc)

@st.dialog("Delete selected documents")
def _delete_documents_dialog(folder_id: str, documents):
    st.write(f"Delete {len(documents)} selected document(s)? This cannot be undone.")
    if st.button("Confirm delete", type="primary", key=f"confirm_delete_documents_{folder_id}"):
        deleted = []
        for document in documents:
            document_id = document["document_id"]
            try:
                response = requests.delete(
                    f"{BASE_URL}/documents/{document_id}",
                    timeout=30,
                )
                response.raise_for_status()
                deleted.append(document)
            except requests.RequestException as exc:
                _show_request_error(f"Could not delete {document['filename']}", exc)

        if deleted:
            st.toast(f"Deleted {len(deleted)} document(s)")
        st.rerun()

def _render_folder_cards(folders):
    create_folder = st.button(
        "New folder",
        icon=":material/add:",
        width="stretch",
    )
    if create_folder:
        _create_folder_dialog()

    if not folders:
        st.info("No folders yet. Use **New folder** to create your first one.")
        return

    st.markdown(
        """
        <style>
        div[data-testid="stButton"] button[kind="secondary"] {
            min-height: 5rem;
            justify-content: flex-start;
            border-radius: 0.75rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for start in range(0, len(folders), FOLDER_COLUMNS):
        columns = st.columns(FOLDER_COLUMNS)
        for column, folder in zip(columns, folders[start : start + FOLDER_COLUMNS]):
            with column:
                if st.button(
                    folder["name"],
                    key=f"open_folder_{folder['id']}",
                    icon=":material/folder:",
                    type="secondary",
                    width="stretch",
                ):
                    st.session_state["selected_folder_id"] = folder["id"]
                    st.rerun()

def _render_folder_contents(folder):
    folder_id = folder["id"]
    navigation, title, rename, delete = st.columns([1, 5, 1, 1])
    with navigation:
        if st.button("Back", icon=":material/arrow_back:", key="back_to_folders"):
            st.session_state.pop("selected_folder_id", None)
            st.rerun()
    with title:
        st.subheader(f":material/folder: {folder['name']}")
    with rename:
        if st.button(
            "Rename",
            icon=":material/edit:",
            key=f"rename_{folder_id}",
            help="Rename this folder",
        ):
            _rename_folder_dialog(folder_id, folder["name"])
    with delete:
        if st.button(
            "Delete",
            icon=":material/delete:",
            key=f"delete_{folder_id}",
            help="Delete this folder",
        ):
            _delete_folder_dialog(folder_id)

    st.divider()
    st.subheader("Add documents")
    with st.form(f"upload_documents_form_{folder_id}", clear_on_submit=True):
        uploads = st.file_uploader(
            "Drop PDFs here or browse files",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        upload_submitted = st.form_submit_button(
            "Upload and ingest",
            type="primary",
            icon=":material/upload_file:",
        )

    if upload_submitted:
        if not uploads:
            st.warning("Choose at least one PDF to upload.")
        else:
            with st.spinner(f"Ingesting {len(uploads)} document(s)..."):
                for upload in uploads:
                    try:
                        metadata = {"folder_id": folder_id}
                        response = requests.post(
                            f"{BASE_URL}/documents",
                            data={"metadata": json.dumps(metadata)},
                            files={
                                "file": (
                                    upload.name,
                                    upload.getvalue(),
                                    upload.type or "application/pdf",
                                )
                            },
                            timeout=(10, 300),
                        )
                        response.raise_for_status()
                        result = response.json()
                        st.success(
                            f"{result['filename']} added ({result['chunks_added']} chunks)."
                        )
                    except requests.RequestException as exc:
                        _show_request_error(f"Could not ingest {upload.name}", exc)

    st.divider()
    st.subheader("Files")
    try:
        documents = _get_documents(folder_id)
    except requests.RequestException as exc:
        _show_request_error("Could not load documents", exc)
        return

    if not documents:
        st.info("This folder is empty. Add PDFs above to get started.")
        return

    selected_documents = []
    for document in documents:
        selector, details = st.columns([0.08, 1])
        with selector:
            selected = st.checkbox(
                f"Select {document['filename']}",
                key=f"select_document_{folder_id}_{document['document_id']}",
                label_visibility="collapsed",
            )
        with details:
            st.markdown(f"**{document['filename']}** · {document['chunks']} chunks")
            st.caption(f"Document ID: `{document['document_id']}`")
        if selected:
            selected_documents.append(document)

    if st.button(
        f"Delete selected ({len(selected_documents)})",
        key=f"delete_selected_documents_{folder_id}",
        icon=":material/delete:",
        type="secondary",
        disabled=not selected_documents,
    ):
        _delete_documents_dialog(folder_id, selected_documents)

def render_documents():
    st.title("Documents")

    try:
        folders = _get_folders()
    except requests.RequestException as exc:
        _show_request_error("Could not load folders", exc)
        return

    selected_id = st.session_state.get("selected_folder_id")
    folder_by_id = {folder["id"]: folder for folder in folders}

    if selected_id in folder_by_id:
        _render_folder_contents(folder_by_id[selected_id])
    else:
        st.caption("Your folders")
        _render_folder_cards(folders)
