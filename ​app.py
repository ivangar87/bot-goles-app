import math
import re
import time
from datetime import datetime, timedelta, timezone
import requests
import streamlit as st

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Scanner +EV Goles",
    page_icon="⚽",
    layout="wide"
)

ODDS_API_KEY = "682df828846bde044edf25e77c30f98e"
FOOTBALL_DATA_API_KEY = "fbba36f8cc0f4baf9481b1f6aa5a489c"

LIGAS = {
    "soccer_epl": {"nombre": "Premier League (Inglaterra)", "code": "PL"},
    "soccer_spain_la_liga": {"nombre": "LaLiga (España)", "code": "PD"},
    "soccer_italy_serie_a": {"nombre": "Serie A (Italia)", "code": "SA"},
    "soccer_germany_bundesliga": {"nombre": "Bundesliga (Alemania)", "code": "BL1"},
    "soccer_france_ligue_one": {"nombre": "Ligue 1 (Francia)", "code": "FL1"},
    "soccer_uefa_champs_league": {"nombre": "UEFA Champions League", "code": "CL"},
    "soccer_netherlands_eredivisie": {"nombre": "Eredivisie (Países Bajos)", "code": "DED"},
    "soccer_efl_champ": {"nombre": "Championship (Inglaterra)", "code": "ELC"},
    "soccer_portugal_primeira_liga": {"nombre": "Primeira Liga (Portugal)", "code": "PPD"},
    "soccer_belgium_first_div": {"nombre": "Pro League (Bélgica)", "code": "BJL"},
    "soccer_brazil_campeonato": {"nombre": "Brasileirão (Brasil)", "code": "BSA"},
    "soccer_argentina_primera_division": {"nombre": "Liga Profesional (Argentina)", "code": "CLI"},
}

PROMEDIOS_LIGAS = {
    "soccer_epl": {"home": 1.55, "away": 1.25},
    "soccer_spain_la_liga": {"home": 1.45, "away": 1.10},
    "soccer_italy_serie_a": {"home": 1.40, "away": 1.15},
    "soccer_germany_bundesliga": {"home": 1.60, "away": 1.30},
    "soccer_france_ligue_one": {"home": 1.40, "away": 1.10},
    "soccer_uefa_champs_league": {"home": 1.55, "away": 1.25},
    "soccer_netherlands_eredivisie": {"home": 1.65, "away": 1.35},
    "soccer_efl_champ": {"home": 1.40, "away": 1.15},
    "soccer_portugal_primeira_liga": {"home": 1.45, "away": 1.10},
    "soccer_belgium_first_div": {"home": 1.55, "away": 1.25},
    "soccer_brazil_campeonato": {"home": 1.35, "away": 1.00},
    "soccer_argentina_primera_division": {"home": 1.25, "away": 0.90},
}

CACHE_ESTADISTICAS = {}

# ==========================================
# 2. LÓGICA DE PROCESAMIENTO
# ==========================================
def limpiar_texto(texto):
    texto = texto.lower()
    reemplazos = ["fc", "cf", "cd", "ud", "rcd", "afc", "sc", "club", "atletico", "real"]
    palabras = re.sub(r"[^a-z0-9 ]", "", texto).split()
    palabras_filtradas = [p for p in palabras if p not in reemplazos]
    return " ".join(palabras_filtradas) if palabras_filtradas else texto

def cargar_tabla_posiciones(league_code):
    if league_code in CACHE_ESTADISTICAS:
        return CACHE_ESTADISTICAS[league_code]
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            tabla_equipos = {}
            standings = data.get("standings", [])
            if standings:
                table = standings[0].get("table", [])
                for row in table:
                    nombre_clean = limpiar_texto(row["team"]["name"])
                    pj_total = max(1, row.get("playedGames", 1))
                    home_data, away_data = row.get("home", {}), row.get("away", {})
                    pj_home = max(1, home_data.get("played", max(1, pj_total // 2)))
                    pj_away = max(1, away_data.get("played", max(1, pj_total // 2)))

                    gf_home_raw = home_data.get("goalsFor", 0)
                    gc_home_raw = home_data.get("goalsAgainst", 0)
                    gf_away_raw = away_data.get("goalsFor", 0)
                    gc_away_raw = away_data.get("goalsAgainst", 0)

                    gf_home = gf_home_raw / pj_home if gf_home_raw > 0 else 1.45
                    gc_home = gc_home_raw / pj_home if gc_home_raw > 0 else 1.15
                    gf_away = gf_away_raw / pj_away if gf_away_raw > 0 else 1.15
                    gc_away = gc_away_raw / pj_away if gc_away_raw > 0 else 1.45

                    tabla_equipos[nombre_clean] = {
                        "gf_home": max(0.5, gf_home), "gc_home": max(0.5, gc_home),
                        "gf_away": max(0.5, gf_away), "gc_away": max(0.5, gc_away),
                    }
            CACHE_ESTADISTICAS[league_code] = tabla_equipos
            return tabla_equipos
    except Exception:
        pass
    CACHE_ESTADISTICAS[league_code] = {}
    return {}

def obtener_datos_equipo(nombre_equipo, league_code, prom_liga):
    tabla_liga = cargar_tabla_posiciones(league_code)
    nombre_clean = limpiar_texto(nombre_equipo)
    for eq_nombre, stats in tabla_liga.items():
        if eq_nombre in nombre_clean or nombre_clean in eq_nombre:
            return stats
    return {
        "gf_home": prom_liga["home"], "gc_home": prom_liga["away"],
        "gf_away": prom_liga["away"], "gc_away": prom_liga["home"],
    }

def poisson(k, lambd):
    return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

def calcular_lambdas(local, visitante, sport_key, league_code):
    prom_liga = PROMEDIOS_LIGAS.get(sport_key, {"home": 1.45, "away": 1.15})
    eq_local = obtener_datos_equipo(local, league_code, prom_liga)
    eq_vis = obtener_datos_equipo(visitante, league_code, prom_liga)

    l_local = min(2.80, max(0.40, (eq_local["gf_home"] / prom_liga["home"]) * (eq_vis["gc_away"] / prom_liga["home"]) * prom_liga["home"]))
    l_vis = min(2.80, max(0.40, (eq_vis["gf_away"] / prom_liga["away"]) * (eq_local["gc_home"] / prom_liga["away"]) * prom_liga["away"]))
    return l_local, l_vis

def calcular_probabilidades_goles(l_local, l_vis):
    prob_ou = {"Más de 1.5": 0, "Menos de 1.5": 0, "Más de 2.5": 0, "Menos de 2.5": 0, "Más de 3.5": 0, "Menos de 3.5": 0}
    for i in range(8):
        for j in range(8):
            p = poisson(i, l_local) * poisson(j, l_vis)
            goles = i + j
            if goles > 1.5: prob_ou["Más de 1.5"] += p
            else: prob_ou["Menos de 1.5"] += p
            if goles > 2.5: prob_ou["Más de 2.5"] += p
            else: prob_ou["Menos de 2.5"] += p
            if goles > 3.5: prob_ou["Más de 3.5"] += p
            else: prob_ou["Menos de 3.5"] += p
    return prob_ou

def analizar_partido(partido, prob_ou, bankroll):
    if not partido.get("bookmakers"): return []
    
    # Usamos un diccionario para mantener únicamente la MEJOR cuota (máxima) por cada mercado
    mejores_opciones = {}
    lineas = [1.5, 2.5, 3.5]
    
    for casa in partido["bookmakers"]:
        casa_nombre = re.sub(r"\s*\([A-Z]{2}\)", "", casa["title"])
        for m in casa.get("markets", []):
            if m["key"] == "totals":
                for outcome in m["outcomes"]:
                    point, price = outcome.get("point"), outcome["price"]
                    if point in lineas:
                        tipo_str = "Más de" if outcome["name"] == "Over" else "Menos de"
                        mercado_key = f"{tipo_str} {point} Goles"
                        prob_est = prob_ou.get(f"{tipo_str} {point}", 0)
                        
                        if prob_est > 0:
                            ev = (prob_est * price) - 1
                            if 0.05 < ev < 0.35:
                                b, q = price - 1, 1 - prob_est
                                stake_pct = max(0, ((b * prob_est - q) / b) * 0.25) * 100
                                
                                opcion = {
                                    "mercado": mercado_key,
                                    "cuota": price,
                                    "ev": ev * 100,
                                    "stake_pct": stake_pct,
                                    "monto": bankroll * (stake_pct / 100),
                                    "casa": casa_nombre
                                }
                                
                                # Si no existe o la nueva cuota es más alta, la reemplazamos
                                if mercado_key not in mejores_opciones or price > mejores_opciones[mercado_key]["cuota"]:
                                    mejores_opciones[mercado_key] = opcion

    return list(mejores_opciones.values())

# ==========================================
# 3. INTERFAZ GRÁFICA EN STREAMLIT
# ==========================================
st.title("⚽ Scanner de Apuestas ValueBet (+EV)")
st.caption("Modelo estadístico de Poisson enfocado en la Línea de Goles (>5% EV)")

# Panel Lateral de Configuración
with st.sidebar:
    st.header("⚙️ Configuración")
    bankroll_input = st.number_input("Bankroll Total ($)", value=100000, step=1000)
    
    st.subheader("Ligas a analizar")
    ligas_seleccionadas = []
    for k, v in LIGAS.items():
        if st.checkbox(v["nombre"], value=True):
            ligas_seleccionadas.append(k)

boton_escanear = st.button("🚀 Escanear Mercado", type="primary", use_container_width=True)

if boton_escanear:
    todas_las_entradas = []
    tz_local = timezone(timedelta(hours=-5))

    with st.spinner("Analizando cuotas y calculando expectativas de valor..."):
        progreso = st.progress(0)
        total_ligas = len(ligas_seleccionadas)

        for index, sport_key in enumerate(ligas_seleccionadas):
            config = LIGAS[sport_key]
            url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
            params = {"apiKey": ODDS_API_KEY, "regions": "eu,uk", "markets": "totals", "oddsFormat": "decimal"}
            
            res = requests.get(url, params=params)
            if res.status_code == 200:
                partidos = res.json()
                for p in partidos:
                    local, visitante = p["home_team"], p["away_team"]
                    fecha_inicio = p.get("commence_time", "")
                    
                    l_loc, l_vis = calcular_lambdas(local, visitante, sport_key, config["code"])
                    prob_ou = calcular_probabilidades_goles(l_loc, l_vis)
                    entradas = analizar_partido(p, prob_ou, bankroll_input)
                    
                    try:
                        dt_utc = datetime.fromisoformat(fecha_inicio.replace("Z", "+00:00"))
                        dt_loc = dt_utc.astimezone(tz_local)
                    except Exception:
                        dt_loc = datetime.now(tz_local)

                    for e in entradas:
                        e["liga"] = config["nombre"]
                        e["partido"] = f"{local} vs {visitante}"
                        e["fecha"] = dt_loc.strftime("%d/%m/%Y %I:%M %p")
                        e["goles_est"] = l_loc + l_vis
                        todas_las_entradas.append(e)

            progreso.progress((index + 1) / total_ligas)

    # MOSTRAR RESULTADOS
    if todas_las_entradas:
        st.success(f"¡Escaneo completado! Se encontraron **{len(todas_las_entradas)}** oportunidades con valor positivo (+EV).")
        st.divider()

        # Métricas rápidas
        m1, m2 = st.columns(2)
        m1.metric("Oportunidades Encontradas", len(todas_las_entradas))
        m2.metric("Mejor EV Detectado", f"+{max(x['ev'] for x in todas_las_entradas):.1f}%")

        st.subheader("📋 Entradas Recomendadas")

        # Mostrar tarjetas visuales por cada entrada
        for item in todas_las_entradas:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 1.5, 1.5])
                
                with col1:
                    st.markdown(f"**{item['partido']}**")
                    st.caption(f"🏆 {item['liga']} | 🕒 {item['fecha']}")
                
                with col2:
                    st.markdown(f"👉 **{item['mercado']}** @ `{item['cuota']:.2f}`")
                    st.caption(f"🏠 Casa: **{item['casa']}**")
                
                with col3:
                    st.markdown(f"📈 Valor: **+{item['ev']:.1f}% EV**")
                    st.caption(f"⚽ Goles Est: {item['goles_est']:.2f}")

                with col4:
                    st.markdown(f"💰 Stake: **{item['stake_pct']:.2f}%**")
                    st.caption(f"Monto: **${item['monto']:,.0f}**")
    else:
        st.warning("No se encontraron oportunidades con suficiente valor (+EV > 5%) en este momento.")
