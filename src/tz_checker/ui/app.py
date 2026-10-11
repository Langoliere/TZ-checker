import os
import time

import httpx
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Проверка ТЗ", layout="wide")
st.title("Автоматическая проверка технических заданий")

uploaded = st.file_uploader("Загрузите ТЗ в формате DOCX", type=["docx"])
if uploaded and st.button("Проверить ТЗ", type="primary"):
    response = httpx.post(f"{API}/v1/documents", files={"file": (uploaded.name, uploaded.getvalue())}, timeout=30)
    if response.is_success:
        st.session_state.document_id = response.json()["id"]
    else:
        st.error(response.json().get("detail", "Ошибка загрузки"))

if document_id := st.session_state.get("document_id"):
    placeholder = st.empty()
    document = httpx.get(f"{API}/v1/documents/{document_id}").json()
    placeholder.info(f"Статус: {document['status']}")
    if document["status"] == "completed":
        findings = httpx.get(f"{API}/v1/documents/{document_id}/findings").json()
        cols = st.columns(5)
        cols[0].metric("Всего", len(findings))
        for col, severity_name in zip(cols[1:], ["critical", "major", "minor", "advisory"], strict=True):
            col.metric(severity_name, sum(f["severity"] == severity_name for f in findings))
        severity_filter = st.multiselect("Severity", ["critical", "major", "minor", "advisory"])
        source_filter = st.multiselect("Источник", ["rule", "rag", "llm"])
        query = st.text_input("Поиск")
        filtered = [f for f in findings if (not severity_filter or f["severity"] in severity_filter) and (not source_filter or f["source"] in source_filter) and query.lower() in f["issue"].lower()]
        st.dataframe(filtered, use_container_width=True)
        selected = st.selectbox("Замечание", filtered, format_func=lambda f: f["issue"])
        if selected:
            st.write(selected["evidence"])
            st.info(selected["recommendation"])
            action = st.radio("Решение эксперта", ["accepted", "rejected", "fixed"], horizontal=True)
            if st.button("Сохранить решение"):
                httpx.patch(f"{API}/v1/findings/{selected['id']}", json={"status": action}, timeout=10)
                st.success("Сохранено")
        st.download_button("Скачать Markdown", httpx.get(f"{API}/v1/documents/{document_id}/reports/markdown").content, "report.md")
    elif document["status"] == "failed":
        st.error(document.get("error") or "Ошибка обработки")
    else:
        time.sleep(2)
        st.rerun()

st.subheader("Последние документы")
try:
    st.dataframe(httpx.get(f"{API}/v1/documents", timeout=5).json(), use_container_width=True)
except httpx.HTTPError:
    st.warning("API недоступен")
