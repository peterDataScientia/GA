"""GA Studio · Phase 1: reliable PDF preview and direct download.

Deploy this file as the Streamlit Community Cloud main file (app.py).
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from pdf_source import (
    DEFAULT_PDF,
    DEFAULT_REPO,
    PdfDocument,
    PdfSourceError,
    canonical_repo,
    load_bundled_pdf,
    load_github_pdf,
    safe_pdf_path,
)

st.set_page_config(page_title="GA Studio | PDF Viewer", page_icon="📄", layout="wide")


def secret_token() -> str | None:
    # No API key field in the web interface; only server-side configuration.
    try:
        secret = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:  # Streamlit raises its own exception when no secrets file exists.
        secret = ""
    return str(secret or os.environ.get("GITHUB_TOKEN", "")).strip() or None


@st.cache_data(ttl=30, show_spinner=False)
def remote_pdf(repo: str, path: str, _token: str | None) -> PdfDocument:
    return load_github_pdf(repo, path, token=_token)


st.title("GA Studio")
st.caption("Graphical abstracts and scientific figures · PDF preview and download")

with st.sidebar:
    st.header("PDF source")
    repository = st.text_input(
        "GitHub repository",
        value=DEFAULT_REPO,
        help="Use owner/repository or https://github.com/owner/repository.",
    )
    pdf_path = st.text_input("PDF file", value=DEFAULT_PDF)
    source = st.radio(
        "Load from",
        options=["Automatic", "GitHub latest", "Repository copy"],
        help="Automatic tries GitHub first and uses the bundled GA PDF if GitHub is unavailable.",
    )
    refresh = st.button("↻ Refresh PDF", use_container_width=True)
    if refresh:
        remote_pdf.clear()
    st.divider()
    st.caption("No AI assistant or code editor in this first version.")
    st.caption("Private GitHub repositories require a read-only GITHUB_TOKEN in Streamlit Secrets for live updates.")

try:
    clean_repo = canonical_repo(repository)
    clean_path = safe_pdf_path(pdf_path)
except PdfSourceError as exc:
    st.error(str(exc))
    st.stop()

pdf = None
warning = None
if source != "Repository copy":
    with st.spinner("Checking GitHub PDF…"):
        try:
            pdf = remote_pdf(clean_repo, clean_path, secret_token())
        except PdfSourceError as exc:
            if source == "GitHub latest":
                st.error(str(exc))
                st.stop()
            warning = str(exc)
if pdf is None:
    try:
        pdf = load_bundled_pdf(clean_repo, clean_path)
    except PdfSourceError as exc:
        st.error(f"Unable to load PDF: {exc}")
        if warning:
            st.caption(f"GitHub: {warning}")
        st.stop()

assert pdf is not None
st.subheader("PDF preview")
meta, button_area = st.columns([3, 1], vertical_alignment="center")
with meta:
    st.caption(
        f"{pdf.source} · {clean_repo} · {clean_path}"
        + (f" · blob {pdf.blob_sha[:8]}" if pdf.blob_sha else "")
    )
with button_area:
    st.download_button(
        "⬇ Download PDF",
        data=pdf.content,
        file_name=Path(clean_path).name,
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
if warning:
    st.info("Showing the PDF bundled with this app. For live updates from your private repository, add GITHUB_TOKEN in Streamlit Secrets.")

st.pdf(pdf.content, height=850)
st.caption("The download button saves the same PDF shown in the viewer. Click Refresh PDF to check GitHub for a newer compiled version.")
