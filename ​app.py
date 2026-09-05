
import math
import re
import time
from datetime import datetime, timedelta
import requests
import streamlit as st

# ==========================================
# 1. CONFIGURACIÓN GENERAL Y APIS
# ==========================================
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "")
FOOTBALL_DATA_API_KEY = st.secrets.get("FOOTBALL_DATA_API_KEY", "")
BANKROLL_TOTAL = 100000

LIGAS = {
    "soccer_epl": {
        "nombre": "Premier League (Inglaterra)",
        "football_data_code": "PL",
    },
    "soccer_spain_la_liga": {
        "nombre": "La Liga (España)",
        "football_data_code": "PD",
    },
    "soccer_italy_serie_a": {
        "nombre": "Serie A (Italia)",
        "football_data_code": "SA",
    },
    "soccer_germany_bundesliga": {
        "nombre": "Bundesliga (Alemania)",
        "football_data_code": "BL1",
    },
    "soccer_france_ligue_one": {
        "nombre": "Ligue 1 (Francia)",
        "football_data_code": "FL1",
    },
    "soccer_argentina_primera_division": {
        "nombre": "Liga Profesional (Argentina)",
        "football_data_code": "CLI",
    },
    "soccer_saudi_pro_league": {
        "nombre": "Saudi Pro League (Arabia Saudita)",
        "football_data_code": "SAU",
    },
    "soccer_japan_j_league": {
        "nombre": "J1 League (Japón)",
        "football_data_code": "JPN",
    },
}

# ==========================================
# 2. FUNCIONES DE CONEXIÓN Y DATOS
# ==========================================
def obtener_cuotas(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk",
        "markets": "totals,h2h",
        "oddsFormat": "decimal",
    }
    try:
        response = requests.get(url, params=params, timeout=12)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []

def obtener_estadisticas_football_data(competition_code):
    if not FOOTBALL_DATA_API_KEY:
        return {}
    url = f"https://api.football-data.org/v4/competitions/{competition_code}/standings"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            standings = data.get("standings", [])
            for st_block in standings:
                if st_block.get("type") == "TOTAL":
                    tabla = {}
                    for row in st_block.get("table", []):
                        team_name = row.get("team", {}).get("name", "")
                        played = row.get("playedGames", 1)
                        goals_for = row.get("goalsFor", 0)
                        goals_against = row.get("goalsAgainst", 0)
                        tabla[team_name] = {
                            "gf_avg": goals_for / max(played, 1),
                            "ga_avg": goals_against / max(played, 1),
                        }
                    return tabla
    except Exception:
        pass
    return {}

# ==========================================
# 3. MOTOR DE CÁLCULO POISSON Y VALOR +EV
# ==========================================
def poisson_prob(lmbda, k):
    try:
        return (math.exp(-lmbda) * (lmbda**k)) / math.factorial(k)
    except Exception:
        return 0.0

def calcular_probabilidades_partido(xg_home, xg_away):
    max_goles = 7
    prob_mas_1_5 = 0.0
    prob_mas_2_5 = 0.0
    prob_mas_3_5 = 0.0

    for gh in range(max_goles + 1):
        p_h = poisson_prob(xg_home, gh)
        for ga in range(max_goles + 1):
            p_a = poisson_prob(xg_away, ga)
            p_total = p_h * p_a
            total_goles = gh + ga
            
            if total_goles > 1.5:
                prob_mas_1_5 += p_total
            if total_goles > 2.5:
                prob_mas_2_5 += p_total
            if total_goles > 3.5:
                prob_mas_3_5 += p_total

    return {
        1.5: prob_mas_1_5,
        2.5: prob_mas_2_5,
        3.5: prob_mas_3_5,
    }

# ==========================================
# 4. INTERFAZ DE USUARIO EN STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Escáner +EV Goles Organizado",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ Escáner de Apuestas ValueBet (+EV)")
st.markdown("Modelo estadístico de Poisson enfocado en la Línea de Goles (Organizado por fecha y país)")

# Sidebar para controles de usuario
st.sidebar.header("⚙️ Configuración del Escáner")
filtro_ev = st.sidebar.slider("Filtro mínimo de EV (%)", min_value=0.0, max_value=20.0, value=0.0, step=0.5) / 100.0

with st.spinner("Escaneando y organizando mercados en tiempo real..."):
    lista_oportunidades = []

    for sport_key, info in LIGAS.items():
        eventos = obtener_cuotas(sport_key)
        if not eventos:
            continue

        stats_fd = obtener_estadisticas_football_data(info["football_data_code"])

        for evento in eventos:
            home = evento.get("home_team", "")
            away = evento.get("away_team", "")
            commence_time = evento.get("commence_time", "")

            try:
                dt = datetime.strptime(commence_time, "%Y-%m-%dT%H:%M:%SZ")
                dt_local = dt - timedelta(hours=5)
                fecha_dia = dt_local.strftime("%d/%m/%Y")
                hora_str = dt_local.strftime("%I:%M %p")
                dt_orden = dt_local
            except:
                fecha_dia = "Por definir"
                hora_str = commence_time
                dt_orden = datetime.min

            h_stat = stats_fd.get(home, {"gf_avg": 1.4, "ga_avg": 1.1})
            a_stat = stats_fd.get(away, {"gf_avg": 1.2, "ga_avg": 1.3})

            xg_home = (h_stat["gf_avg"] + a_stat["ga_avg"]) / 2
            xg_away = (a_stat["gf_avg"] + h_stat["ga_avg"]) / 2
            xg_home = max(0.5, min(xg_home, 3.5))
            xg_away = max(0.5, min(xg_away, 3.5))

            probs = calcular_probabilidades_partido(xg_home, xg_away)

            bookmakers = evento.get("bookmakers", [])
            if not bookmakers:
                continue

            cuotas_mercado = {}
            for bookmaker in bookmakers:
                for market in bookmaker.get("markets", []):
                    if market.get("key") == "totals":
                        for outcome in market.get("outcomes", []):
                            if "Over" in outcome.get("name", ""):
                                punto = outcome.get("point")
                                precio = outcome.get("price")
                                if punto in [1.5, 2.5, 3.5]:
                                    if punto not in cuotas_mercado:
                                        cuotas_mercado[punto] = precio

            for linea in [1.5, 2.5, 3.5]:
                if linea in cuotas_mercado and linea in probs:
                    cuota = cuotas_mercado[linea]
                    prob_poisson = probs[linea]
                    
                    if prob_poisson > 0:
                        ev = (prob_poisson * cuota) - 1
                        
                        if ev >= filtro_ev:
                            lista_oportunidades.append({
                                "dt_orden": dt_orden,
                                "fecha_dia": fecha_dia,
                                "hora_str": hora_str,
                                "liga_nombre": info["nombre"],
                                "home": home,
                                "away": away,
                                "linea": linea,
                                "cuota": cuotas_mercado[linea],
                                "ev": ev,
                                "prob_poisson": prob_poisson,
                                "xg_home": xg_home,
                                "xg_away": xg_away
                            })

    # Ordenar cronológicamente por fecha/hora
    lista_oportunidades.sort(key=lambda x: x["dt_orden"])

    total_encontrados = len(lista_oportunidades)
    st.success(f"¡Se encontraron {total_encontrados} opciones en el mercado!")

    if total_encontrados == 0:
        st.warning("No se encontraron apuestas que superen el filtro de EV actual.")
    else:
        fechas_unicas = sorted(list(set(op["fecha_dia"] for op in lista_oportunidades)))
        
        for fecha in fechas_unicas:
            st.markdown(f"### 📅 Fecha: {fecha}")
            ops_fecha = [op for op in lista_oportunidades if op["fecha_dia"] == fecha]
            
            ligas_en_fecha = sorted(list(set(op["liga_nombre"] for op in ops_fecha)))
            
            for liga in ligas_en_fecha:
                st.markdown(f"#### 🏆 {liga}")
                ops_liga = [op for op in ops_fecha if op["liga_nombre"] == liga]
                
                for item in ops_liga:
                    color_borde = "#4CAF50" if item["ev"] > 0.05 else "#FF9800"
                    st.markdown(
                        f"""
                        <div style="background-color: #1a1a1a; padding: 14px; border-radius: 10px; margin-bottom: 12px; border-left: 5px solid {color_borde}; color: #ffffff;">
                            <strong>{item['home']} vs {item['away']}</strong><br>
                            <small style="color: #b0b0b0;">🕒 Hora: {item['hora_str']} | xG Est. ({item['xg_home']:.2f} - {item['xg_away']:.2f})</small><br>
                            👉 <strong>Más de {item['linea']} Goles</strong> a cuota <code>{item['cuota']:.2f}</code><br>
                            📈 <strong>Valor (+EV):</strong> <span style="color: #4CAF50; font-weight: bold;">{item['ev']*100:+.1f}%</span> | <strong>Prob. Poisson:</strong> <code>{item['prob_poisson']*100:.1f}%</code>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
