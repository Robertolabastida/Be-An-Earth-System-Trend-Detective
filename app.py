
import streamlit as st

st.set_page_config(
    page_title="EarthTrend AI",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 EarthTrend AI")
st.subheader("NASA Space Apps Challenge 2026")

st.write("Explorador inteligente de tendencias del sistema terrestre.")

region = st.selectbox(
    "Selecciona una región:",
    ["Baja California", "Amazoníha", "Sahel"]
)

st.info(f"Región seleccionada: {region}")

st.caption("Prototipo inicial. Datos NASA aún no conectados.")
