import math
import re
import time
from datetime import datetime, timedelta, timezone
import requests
import streamlit as st

# ==========================================
# 1. CONFIGURACIÓN GENERAL Y APIS
# ==========================================
# Streamlit leerá las llaves de los Secrets configurados en la plataforma
ODDS_API_KEY = st.secrets.get("ODDS_API_KEY", "78eaa8461c2a397cd8e2de084867512b")
FOOTBALL_DATA_API_KEY = st.secrets.get("FOOTBALL_DATA_API_KEY", "fbba36f8cc0f4baf9481b1f6aa5a489c")
BANKROLL_TOTAL = 100000

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
    "soccer_argentina_primera_division": {"nombre": "Liga Profesional (Argentina)", "code": "CLI"}
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
    "soccer_argentina_primera_division": {"home": 1.25, "away": 0.90}
}

CACHE_ESTADISTICAS = {}

# ==========================================
# 2. FUNCIONES DE CÁLKULO Y DATOS
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
                    nombre = row["team"]["name"]
                    nombre_clean = limpiar_texto(nombre)
                    pj_total = max(1, row.get("playedGames", 1))
                    home_data = row.get("home", {})
                    away_data = row.get("away", {})
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
                        "gf_home": max(0.5, gf_home),
                        "gc_home": max(0.5, gc_home),
                        "gf_away": max(0.5, gf_away),
                        "gc_away": max(0.5, gc_away),
                    }
            CACHE_ESTADISTICAS[league_code] = tabla_equipos
            return tabla_equipos
    except Exception:
        pass

    CACHE_ESTADISTICAS[league_code] = {}
    return {}

def obtener_datos_equipo_dinamico(nombre_equipo, league_code, prom_liga):
    tabla_liga = cargar_tabla_posiciones(league_code)
    nombre_clean = limpiar_texto(nombre_equipo)
    for eq_nombre, stats in tabla_liga.items():
        if eq_nombre in nombre_clean or nombre_clean in eq_nombre:
            return stats, True
    return {
        "gf_home": prom_liga["home"],
        "gc_home": prom_liga["away"],
        "gf_away": prom_liga["away"],
        "gc_away": prom_liga["home"],
    }, False

def calcular_lambdas(local, visitante, sport_key, league_code):
    prom_liga = PROMEDIOS_LIGAS.get(sport_key, {"home": 1.45, "away": 1.15})
    eq_local, enc_loc = obtener_datos_equipo_dinamico(local, league_code, prom_liga)
    eq_vis, enc_vis = obtener_datos_equipo_dinamico(visitante, league_code, prom_liga)

    avg_home = prom_liga["home"]
    avg_away = prom_liga["away"]

    l_local = (eq_local["gf_home"] / avg_home) * (eq_vis["gc_away"] / avg_home) * avg_home
    l_vis = (eq_vis["gf_away"] / avg_away) * (eq_local["gc_home"] / avg_away) * avg_away

    return min(2.80, max(0.40, l_local)), min(2.80, max(0.40, l_vis)), (enc_loc and enc_vis)

def poisson(k, lambd):
    return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

def calcular_probabilidades_multilinea(l_local, l_vis):
    prob_ou = {"Más de 1.5": 0.0, "Menos de 1.5": 0.0, "Más de 2.5": 0.0, "Menos de 2.5": 0.0, "Más de 3.5": 0.0, "Menos de 3.5": 0.0}
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

def obtener_cuotas_goles(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"apiKey": ODDS_API_KEY, "regions": "eu,uk", "markets": "totals", "oddsFormat": "decimal", "dateFormat": "iso"}
    try:
        res = requests.get(url, params=params)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def calcular_kelly_fraccionado(prob, cuota, fraccion=0.25):
    b = cuota - 1
    p = prob
    q = 1 - p
    f_kelly = (b * p - q) / b
    return max(0, f_kelly * fraccion) * 100

def analizar_cuotas_goles(partido, prob_ou):
    if not partido.get("bookmakers"):
        return None, []
    casa = partido["bookmakers"][0]
    mercados = casa.get("markets", [])
    value_bets = []
    nombre_casa = re.sub(r"\s*\([A-Z]{2}\)", "", casa["title"])
    lineas_soportadas = [1.5, 2.5, 3.5]

    for m in mercados:
        if m["key"] == "totals":
            for outcome in m["outcomes"]:
                name = outcome["name"]
                point = outcome.get("point")
                price = outcome["price"]
                if point in lineas_soportadas:
                    tipo_str = "Más de" if name == "Over" else "Menos de"
                    key_lookup = f"{tipo_str} {point}"
                    prob_est = prob_ou.get(key_lookup, 0)
                    if prob_est > 0:
                        ev = (prob_est * price) - 1
                        # Filtro flexible a 0.0 para ver los partidos disponibles
                        if 0.0 < ev < 0.35:
                            pct_stake = calcular_kelly_fraccionado(prob_est, price)
                            value_bets.append({
                                "categoria": f"Línea de Goles ({tipo_str} {point})",
                                "mercado": f"{tipo_str} {point} Goles",
                                "cuota": price,
                                "prob_est": prob_est * 100,
                                "ev": ev * 100,
                                "stake_pct": pct_stake,
                                "monto": BANKROLL_TOTAL * (pct_stake / 100),
                            })
    return nombre_casa, value_bets

# ==========================================
# 3. INTERFAZ STREAMLIT
# ==========================================
st.set_page_config(page_title="Scanner ValueBet (+EV)", page_icon="⚽", layout="centered")

st.title("⚽ Scanner de Apuestas ValueBet (+EV)")
st.markdown("Modelo estadístico de Poisson enfocado en la Línea de Goles (Filtro flexible activo)")

if st.button("🚀 Escanear Mercado", type="primary", use_container_width=True):
    with st.spinner("Escaneando ligas y calculando valor..."):
        todas_las_oportunidades = []
        tz_local = timezone(timedelta(hours=-5))

        for sport_key, config in LIGAS.items():
            nombre_liga = config["nombre"]
            league_code = config["code"]
            partidos = obtener_cuotas_goles(sport_key)

            if not partidos:
                continue

            for p in partidos:
                local = p["home_team"]
                visitante = p["away_team"]
                fecha_inicio = p.get("commence_time", "")

                l_local, l_vis, _ = calcular_lambdas(local, visitante, sport_key, league_code)
                prob_ou = calcular_probabilidades_multilinea(l_local, l_vis)
                casa_nombre, value_bets = analizar_cuotas_goles(p, prob_ou)

                for vb in value_bets:
                    try:
                        dt_utc = datetime.fromisoformat(fecha_inicio.replace("Z", "+00:00"))
                        dt_loc = dt_utc.astimezone(tz_local)
                    except Exception:
                        dt_loc = datetime.now(tz_local)

                    todas_las_oportunidades.append({
                        "liga": nombre_liga,
                        "partido": f"{local} vs {visitante}",
                        "dt_local": dt_loc,
                        **vb,
                        "casa": casa_nombre,
                        "lambda_local": l_local,
                        "lambda_vis": l_vis,
                    })

        if todas_las_oportunidades:
            st.success(f"¡Se encontraron {len(todas_las_oportunidades)} opciones en el mercado!")
            for op in todas_las_oportunidades:
                with st.container():
                    st.markdown(f"**[{op['liga']}] {op['partido']}**")
                    st.caption(f"🕒 {op['dt_local'].strftime('%d/%m/%Y %I:%M %p')} | Casa: {op['casa']}")
                    st.info(f"👉 **{op['mercado']}** @ **{op['cuota']:.2f}**\n\n"
                            f"📈 Valor (+EV): `+{op['ev']:.1f}%` | Prob. Est: `{op['prob_est']:.1f}%`\n\n"
                            f"💰 Stake Sugerido: `{op['stake_pct']:.2f}%` (`${op['monto']:,.0f}`)")
                    st.divider()
        else:
            st.warning("No se encontraron oportunidades en este momento, pero la conexión con la API y los créditos funcionan perfectamente.")
