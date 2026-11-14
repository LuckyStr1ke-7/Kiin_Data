#!/usr/bin/env python3
"""Reconstruye el Evidence Board de K'IIN DATA para la pregunta del data brief.

Lee el monitoreo subterráneo de RENAMECA, descarga marginación CONAPO 2020,
defunciones y nacimientos de INEGI 2018-2023 y nacimientos SINAC 2018-2023,
y escribe la tabla municipal, los CSV de verificación y un PDF de 3 páginas.
Los microdatos nacionales quedan en data/raw/ y no se versionan.
"""

from __future__ import annotations

import io
import pickle
import re
import sys
import zipfile
from datetime import date
from urllib.parse import urljoin
from pathlib import Path

import pandas as pd
import requests
from reportlab.lib.colors import Color, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    CondPageBreak,
    PageBreak,
    Flowable,
)
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
XLSB = ROOT / "data" / "Subterraneo.xlsb"
PDF_PATH = ROOT / "documents" / "Evidence_Board_KIIN_Data.pdf"
TODAY = date.today().isoformat()

YEARS = list(range(2018, 2024))
PANDEMIC = {2020, 2021}
STABLE_BIRTHS = 100
ENTITY = 31

# Límites generales de la NOM-127-SSA1-2021. El de coliformes es un mínimo
# medido: la norma pide ausencia (<1.1 NMP/100 mL).
LIMITS = {
    "COLI_FEC": 1.1,
    "N_NO3": 11.0,
    "AS_TOT": 0.025,
    "CD_TOT": 0.005,
    "CR_TOT": 0.05,
    "PB_TOT": 0.01,
    "HG_TOT": 0.006,
    "FLUORUROS_TOT": 1.5,
}
PARAM_LABEL = {
    "COLI_FEC": "Coliformes fecales",
    "N_NO3": "Nitratos (N)",
    "AS_TOT": "Arsénico",
    "CD_TOT": "Cadmio",
    "CR_TOT": "Cromo total",
    "PB_TOT": "Plomo",
    "HG_TOT": "Mercurio",
    "FLUORUROS_TOT": "Fluoruros",
}
PARAM_UNIT = {
    "COLI_FEC": "NMP/100 mL",
    "N_NO3": "mg/L",
    "AS_TOT": "mg/L",
    "CD_TOT": "mg/L",
    "CR_TOT": "mg/L",
    "PB_TOT": "mg/L",
    "HG_TOT": "mg/L",
    "FLUORUROS_TOT": "mg/L",
}
SDT_LIMIT = 1000.0
DUR_LIMIT = 500.0
COLI_SEVERE = 1000.0

NOMBRES = [
    "Abalá", "Acanceh", "Akil", "Baca", "Bokobá", "Buctzotz", "Cacalchén",
    "Calotmul", "Cansahcab", "Cantamayec", "Celestún", "Cenotillo", "Conkal",
    "Cuncunul", "Cuzamá", "Chacsinkín", "Chankom", "Chapab", "Chemax",
    "Chicxulub Pueblo", "Chichimilá", "Chikindzonot", "Chocholá", "Chumayel",
    "Dzán", "Dzemul", "Dzidzantún", "Dzilam de Bravo", "Dzilam González",
    "Dzitás", "Dzoncauich", "Espita", "Halachó", "Hocabá", "Hoctún", "Homún",
    "Huhí", "Hunucmá", "Ixil", "Izamal", "Kanasín", "Kantunil", "Kaua",
    "Kinchil", "Kopomá", "Mama", "Maní", "Maxcanú", "Mayapán", "Mérida",
    "Mocochá", "Motul", "Muná", "Muxupip", "Opichén", "Oxkutzcab", "Panabá",
    "Peto", "Progreso", "Quintana Roo", "Río Lagartos", "Sacalum", "Samahil",
    "Sanahcat", "San Felipe", "Santa Elena", "Seyé", "Sinanché", "Sotuta",
    "Sucilá", "Sudzal", "Suma", "Tahdziú", "Tahmek", "Teabo", "Tecoh",
    "Tekal de Venegas", "Tekantó", "Tekax", "Tekit", "Tekom", "Telchac Pueblo",
    "Telchac Puerto", "Temax", "Temozón", "Tepakán", "Tetiz", "Teya", "Ticul",
    "Timucuy", "Tinum", "Tixcacalcupul", "Tixkokob", "Tixmehuac", "Tixpéhual",
    "Tizimín", "Tunkás", "Tzucacab", "Uayma", "Ucú", "Umán", "Valladolid",
    "Xocchel", "Yaxcabá", "Yaxkukul", "Yobaín",
]
CATALOG_ASCII = {
    1: "ABALA", 2: "ACANCEH", 3: "AKIL", 4: "BACA", 5: "BOKOBA",
    6: "BUCTZOTZ", 7: "CACALCHEN", 8: "CALOTMUL", 9: "CANSAHCAB", 10: "CANTAMAYEC",
    11: "CELESTUN", 12: "CENOTILLO", 13: "CONKAL", 14: "CUNCUNUL", 15: "CUZAMA",
    16: "CHACSINKIN", 17: "CHANKOM", 18: "CHAPAB", 19: "CHEMAX", 20: "CHICXULUB PUEBLO",
    21: "CHICHIMILA", 22: "CHIKINDZONOT", 23: "CHOCHOLA", 24: "CHUMAYEL", 25: "DZAN",
    26: "DZEMUL", 27: "DZIDZANTUN", 28: "DZILAM DE BRAVO", 29: "DZILAM GONZALEZ", 30: "DZITAS",
    31: "DZONCAUICH", 32: "ESPITA", 33: "HALACHO", 34: "HOCABA", 35: "HOCTUN",
    36: "HOMUN", 37: "HUHI", 38: "HUNUCMA", 39: "IXIL", 40: "IZAMAL",
    41: "KANASIN", 42: "KANTUNIL", 43: "KAUA", 44: "KINCHIL", 45: "KOPOMA",
    46: "MAMA", 47: "MANI", 48: "MAXCANU", 49: "MAYAPAN", 50: "MERIDA",
    51: "MOCOCHA", 52: "MOTUL", 53: "MUNA", 54: "MUXUPIP", 55: "OPICHEN",
    56: "OXKUTZCAB", 57: "PANABA", 58: "PETO", 59: "PROGRESO", 60: "QUINTANA ROO",
    61: "RIO LAGARTOS", 62: "SACALUM", 63: "SAMAHIL", 64: "SANAHCAT", 65: "SAN FELIPE",
    66: "SANTA ELENA", 67: "SEYE", 68: "SINANCHE", 69: "SOTUTA", 70: "SUCILA",
    71: "SUDZAL", 72: "SUMA", 73: "TAHDZIU", 74: "TAHMEK", 75: "TEABO",
    76: "TECOH", 77: "TEKAL DE VENEGAS", 78: "TEKANTO", 79: "TEKAX", 80: "TEKIT",
    81: "TEKOM", 82: "TELCHAC PUEBLO", 83: "TELCHAC PUERTO", 84: "TEMAX", 85: "TEMOZON",
    86: "TEPAKAN", 87: "TETIZ", 88: "TEYA", 89: "TICUL", 90: "TIMUCUY",
    91: "TINUM", 92: "TIXCACALCUPUL", 93: "TIXKOKOB", 94: "TIXMEHUAC", 95: "TIXPEHUAL",
    96: "TIZIMIN", 97: "TUNKAS", 98: "TZUCACAB", 99: "UAYMA", 100: "UCU",
    101: "UMAN", 102: "VALLADOLID", 103: "XOCCHEL", 104: "YAXCABA", 105: "YAXKUKUL",
    106: "YOBAIN",
}

NAVY = Color(0.106, 0.227, 0.294)
TEAL = Color(0.122, 0.435, 0.416)
SAND = Color(0.769, 0.482, 0.169)
INK = Color(0.110, 0.141, 0.157)
MUTED = Color(0.361, 0.420, 0.451)
LINE = Color(0.835, 0.871, 0.890)
PALE = Color(0.945, 0.957, 0.965)
GROUP_COLOR = {
    "Con evidencia": SAND,
    "Monitoreado sin excedencia": TEAL,
    "Sin monitoreo": Color(0.541, 0.627, 0.659),
}


def ascii_key(text) -> str:
    import unicodedata

    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    value = unicodedata.normalize("NFD", str(text))
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.upper().replace(".", " ")
    return " ".join(value.split())


ALIASES = {
    "OXKUZTCAB": "OXKUTZCAB",
}


def resolve_municipality(raw, by_key: dict[str, int]):
    key = ascii_key(raw)
    if key in by_key:
        return by_key[key], key
    aliased = ALIASES.get(key, key)
    if aliased in by_key:
        return by_key[aliased], aliased
    import difflib
    match = difflib.get_close_matches(key, by_key.keys(), n=1, cutoff=0.88)
    if match:
        print(f"  alias automático: {raw!r} -> {match[0]}")
        return by_key[match[0]], match[0]
    return None, key


def check_catalog() -> dict[str, int]:
    if len(NOMBRES) != 106:
        raise SystemExit(f"El catálogo de nombres tiene {len(NOMBRES)} entradas.")
    by_key = {}
    for code, name in enumerate(NOMBRES, start=1):
        key = ascii_key(name)
        if CATALOG_ASCII[code] != key:
            raise SystemExit(f"Nombre {code} {name!r} no coincide con {CATALOG_ASCII[code]!r}.")
        by_key[key] = code
    return by_key


def parse_measure(value):
    """Devuelve (numero, tipo) con tipo en missing, below, above, value."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, "missing"
    if isinstance(value, (int, float)):
        return float(value), "value"
    text = str(value).strip().replace(",", "")
    if text == "" or text.lower() in {"nan", "none", "nd", "nr", "na", "n/d", "n.d.", "s/d"}:
        return None, "missing"
    lower = text.lower()
    if lower in {"ausencia", "ausente", "no detectable", "no detectado"}:
        return None, "below"
    if text[0] in "<≤":
        return None, "below"
    if text[0] in ">≥":
        number = re.sub(r"[^0-9.]", "", text)
        return (float(number) if number else None), "above"
    try:
        return float(text), "value"
    except ValueError:
        return None, "missing"


def exceeds(param: str, number, kind: str) -> bool:
    if kind == "missing" or kind == "below":
        return False
    limit = LIMITS[param]
    if number is None:
        return False
    if param == "COLI_FEC":
        return number >= limit
    if kind == "above":
        return number >= limit
    return number > limit


def session() -> requests.Session:
    http = requests.Session()
    http.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
    )
    return http


def download(http: requests.Session, url: str, dest: Path, timeout: int = 180) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ya existe {dest.name}", flush=True)
        return
    last_error = None
    for attempt in range(1, 3):
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            print(f"  descarga {url}", flush=True)
            with http.get(url, timeout=(25, 90), stream=True) as response:
                response.raise_for_status()
                with tmp.open("wb") as handle:
                    for chunk in response.iter_content(1024 * 256):
                        if chunk:
                            handle.write(chunk)
            tmp.replace(dest)
            if dest.suffix.lower() == ".zip" and dest.read_bytes()[:2] != b"PK":
                dest.unlink()
                raise RuntimeError(f"{url} no devolvió un ZIP")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if tmp.exists():
                tmp.unlink()
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink()
            print(f"  reintento {attempt} ({type(exc).__name__})", flush=True)
    raise RuntimeError(last_error)


def first_working(http, urls, dest: Path):
    errors = []
    for url in urls:
        try:
            download(http, url, dest)
            return url
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url} -> {exc}")
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink()
    raise RuntimeError("Ninguna URL funcionó:\n" + "\n".join(errors))


def load_water(by_key: dict[str, int]):
    import pyxlsb

    cache = OUT / "water_cache.pkl"
    if cache.exists():
        print("Usando caché del monitoreo subterráneo.")
        with cache.open("rb") as handle:
            return pickle.load(handle)

    print("Leyendo monitoreo subterráneo...")
    sites = {}
    with pyxlsb.open_workbook(XLSB) as book:
        with book.get_sheet("SITIOS") as sheet:
            rows = sheet.rows()
            header = [cell.v for cell in next(rows)]
            index = {name: pos for pos, name in enumerate(header)}
            for row in rows:
                values = [cell.v for cell in row]
                if not values or values[index["ESTADO"]] is None:
                    continue
                if "YUC" not in str(values[index["ESTADO"]]).upper():
                    continue
                key = str(values[index["CLAVE SITIO"]]).strip()
                code, _mun_key = resolve_municipality(values[index["MUNICIPIO"]], by_key)
                sites[key] = {
                    "cve": code,
                    "mun_raw": values[index["MUNICIPIO"]],
                    "subtipo": ascii_key(values[index["SUBTIPO CUERPO AGUA"]]),
                }

    unmatched = sorted({item["mun_raw"] for item in sites.values() if item["cve"] is None})
    if unmatched:
        raise SystemExit(f"Municipios de agua sin clave INEGI: {unmatched}")

    wanted = list(LIMITS) + ["SDT", "DUR_TOT"]
    quality = {
        "n_sitios": len(sites),
        "n_pozos": sum(1 for item in sites.values() if item["subtipo"] == "POZO"),
        "n_cenotes": sum(1 for item in sites.values() if item["subtipo"] == "CENOTE"),
        "n_muestras_ventana": 0,
        "n_muestras_archivo_yuc": 0,
        "medidos": {name: 0 for name in wanted},
        "censurados": {name: 0 for name in wanted},
        "excedencias": {name: 0 for name in LIMITS},
        "coli_severo_muestras": 0,
        "sdt_excede_muestras": 0,
        "dur_excede_muestras": 0,
        "muestras_por_mun": {},
        "anios": set(),
    }
    mun_stats = {
        code: {
            "sitios": set(),
            "sitios_ventana": set(),
            "pozos": set(),
            "cenotes": set(),
            "n_muestras": 0,
            "anios": set(),
            "ex_muestras": {name: 0 for name in LIMITS},
            "coli_severo": 0,
            "sdt_excede": 0,
            "dur_excede": 0,
        }
        for code in range(1, 107)
    }
    for key, item in sites.items():
        stats = mun_stats[item["cve"]]
        stats["sitios"].add(key)
        if item["subtipo"] == "POZO":
            stats["pozos"].add(key)
        elif item["subtipo"] == "CENOTE":
            stats["cenotes"].add(key)

    with pyxlsb.open_workbook(XLSB) as book:
        with book.get_sheet("RESULTADOS") as sheet:
            rows = sheet.rows()
            header = [cell.v for cell in next(rows)]
            index = {name: pos for pos, name in enumerate(header)}
            missing_cols = [name for name in wanted + ["CLAVE SITIO", "Año"] if name not in index]
            if missing_cols:
                raise SystemExit(f"Faltan columnas en RESULTADOS: {missing_cols}")
            seen = 0
            for row in rows:
                seen += 1
                if seen % 20000 == 0:
                    print(f"  filas leídas {seen}")
                values = [cell.v for cell in row]
                key = str(values[index["CLAVE SITIO"]]).strip() if values[index["CLAVE SITIO"]] is not None else ""
                site = sites.get(key)
                if site is None:
                    continue
                quality["n_muestras_archivo_yuc"] += 1
                year_raw = values[index["Año"]]
                try:
                    year = int(year_raw)
                except (TypeError, ValueError):
                    continue
                quality["anios"].add(year)
                if year not in YEARS:
                    continue
                quality["n_muestras_ventana"] += 1
                code = site["cve"]
                stats = mun_stats[code]
                stats["n_muestras"] += 1
                stats["anios"].add(year)
                stats["sitios_ventana"].add(key)
                quality["muestras_por_mun"][code] = quality["muestras_por_mun"].get(code, 0) + 1
                for name in wanted:
                    number, kind = parse_measure(values[index[name]])
                    if kind != "missing":
                        quality["medidos"][name] += 1
                    if kind == "below":
                        quality["censurados"][name] += 1
                    if name in LIMITS and exceeds(name, number, kind):
                        quality["excedencias"][name] += 1
                        stats["ex_muestras"][name] += 1
                    if name == "COLI_FEC" and kind == "value" and number is not None and number > COLI_SEVERE:
                        quality["coli_severo_muestras"] += 1
                        stats["coli_severo"] += 1
                    if name == "SDT" and kind == "value" and number is not None and number > SDT_LIMIT:
                        quality["sdt_excede_muestras"] += 1
                        stats["sdt_excede"] += 1
                    if name == "DUR_TOT" and kind == "value" and number is not None and number > DUR_LIMIT:
                        quality["dur_excede_muestras"] += 1
                        stats["dur_excede"] += 1

    rows_out = []
    for code in range(1, 107):
        stats = mun_stats[code]
        exceeded = [name for name, count in stats["ex_muestras"].items() if count > 0]
        if stats["n_muestras"] == 0:
            grupo = "Sin monitoreo"
        elif exceeded:
            grupo = "Con evidencia"
        else:
            grupo = "Monitoreado sin excedencia"
        principal = ""
        if exceeded:
            principal = max(exceeded, key=lambda name: stats["ex_muestras"][name])
        record = {
            "cve_municipio": code,
            "municipio": NOMBRES[code - 1],
            "grupo": grupo,
            "n_sitios": len(stats["sitios"]),
            "n_sitios_ventana": len(stats["sitios_ventana"]),
            "n_pozos": len(stats["pozos"]),
            "n_cenotes": len(stats["cenotes"]),
            "n_muestras": stats["n_muestras"],
            "anio_min": min(stats["anios"]) if stats["anios"] else "",
            "anio_max": max(stats["anios"]) if stats["anios"] else "",
            "n_parametros_excedidos": len(exceeded),
            "parametro_principal": PARAM_LABEL.get(principal, ""),
            "coli_severo": int(stats["coli_severo"] > 0),
            "sdt_excede": int(stats["sdt_excede"] > 0),
            "dureza_excede": int(stats["dur_excede"] > 0),
        }
        for name in LIMITS:
            record[f"ex_{name}"] = int(stats["ex_muestras"][name] > 0)
            record[f"muestras_ex_{name}"] = stats["ex_muestras"][name]
        rows_out.append(record)

    frame = pd.DataFrame(rows_out)
    param_rows = []
    samples = quality["n_muestras_ventana"] or 1
    for name in LIMITS:
        param_rows.append(
            {
                "parametro": name,
                "nombre": PARAM_LABEL[name],
                "limite": LIMITS[name],
                "unidad": PARAM_UNIT[name],
                "muestras_con_resultado": quality["medidos"][name],
                "muestras_bajo_deteccion": quality["censurados"][name],
                "muestras_con_excedencia": quality["excedencias"][name],
                "municipios_con_excedencia": int(frame[f"ex_{name}"].sum()),
                "pct_muestras_con_resultado": round(100 * quality["medidos"][name] / samples, 1),
            }
        )
    quality["anios"] = sorted(quality["anios"])
    if quality["muestras_por_mun"]:
        top_code = max(quality["muestras_por_mun"], key=quality["muestras_por_mun"].get)
        quality["top_mun"] = NOMBRES[top_code - 1]
        quality["top_muestras"] = quality["muestras_por_mun"][top_code]
        quality["top_pct"] = round(100 * quality["top_muestras"] / samples, 1)
    else:
        quality["top_mun"] = ""
        quality["top_muestras"] = 0
        quality["top_pct"] = 0
    print(
        f"  sitios {quality['n_sitios']} | muestras {quality['n_muestras_archivo_yuc']} "
        f"| ventana {quality['n_muestras_ventana']} | grupos\n"
        f"  {frame['grupo'].value_counts().to_dict()}"
    )
    result = frame, pd.DataFrame(param_rows), quality
    OUT.mkdir(parents=True, exist_ok=True)
    with cache.open("wb") as handle:
        pickle.dump(result, handle)
    return result


def ckan_conapo_url(http) -> str:
    response = http.get(
        "https://www.datos.gob.mx/api/3/action/package_show?id=indices_marginacion",
        timeout=15,
    )
    response.raise_for_status()
    resources = response.json()["result"]["resources"]
    ranked = []
    for resource in resources:
        name = (resource.get("name") or "").lower()
        url = resource.get("url") or ""
        if "municip" in name and "2020" in name and "localidad" not in name and "urbana" not in name:
            score = 0
            if "csv" in (resource.get("format") or "").lower() or url.lower().endswith(".csv"):
                score += 2
            ranked.append((score, url))
    if not ranked:
        raise RuntimeError("El catálogo de datos.gob.mx no listó el índice municipal 2020.")
    ranked.sort(reverse=True)
    return ranked[0][1]


def github_conapo_candidates(http) -> list[str]:
    urls = []
    try:
        response = http.get(
            "https://api.github.com/search/repositories",
            params={"q": "indice marginacion municipal 2020", "per_page": 8},
            timeout=15,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
    except Exception as exc:  # noqa: BLE001
        print(f"  búsqueda en GitHub no disponible ({type(exc).__name__})")
        return urls
    for item in items:
        full = item["full_name"]
        branch = item.get("default_branch") or "main"
        try:
            listing = http.get(
                f"https://api.github.com/repos/{full}/git/trees/{branch}?recursive=1",
                timeout=15,
            )
            listing.raise_for_status()
            tree = listing.json().get("tree", [])
        except Exception:  # noqa: BLE001
            continue
        for node in tree:
            path = node.get("path", "")
            low = path.lower()
            if not low.endswith((".csv", ".xlsx", ".xls")):
                continue
            if "loc" in low or "localidad" in low or "colonia" in low or "ageb" in low:
                continue
            if "imm_2020" in low or ("2020" in low and "mun" in low and "margin" in low):
                urls.append(f"https://raw.githubusercontent.com/{full}/{branch}/{path}")
    return urls


def read_conapo_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, encoding="latin-1")
    else:
        frame = pd.read_excel(path, engine="calamine")
    columns = {ascii_key(col): col for col in frame.columns}

    def col(*options):
        for option in options:
            if option in columns:
                return columns[option]
        raise KeyError(options[0])

    entity = col("CVE_ENT", "CVE ENT", "ENT")
    mun = col("CVE_MUN", "CVE MUN", "MUN")
    grade = col("GM_2020", "GM 2020", "GRADO")
    index = col("IM_2020", "IM 2020", "INDICE")
    part = frame[pd.to_numeric(frame[entity], errors="coerce") == ENTITY].copy()
    raw_mun = part[mun].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    part["cve_municipio"] = raw_mun.str[-3:].astype(int)
    part = part[part["cve_municipio"].between(1, 106)]
    out = part[["cve_municipio", grade, index]].rename(columns={grade: "gm_2020", index: "im_2020"})
    out["im_2020"] = pd.to_numeric(out["im_2020"], errors="coerce")
    if out["cve_municipio"].nunique() < 100:
        raise RuntimeError(f"solo {out['cve_municipio'].nunique()} municipios")
    return out


def load_conapo(http, fuentes: list[dict]) -> pd.DataFrame:
    print("Marginación CONAPO 2020...")
    local = sorted(RAW.glob("conapo_*.xls*"))
    if local:
        out = read_conapo_frame(local[0])
        fuentes.append(
            {
                "fuente": "CONAPO",
                "descripcion": "Índice y grado de marginación municipal 2020",
                "url": "https://raw.githubusercontent.com/franJ0212/Analisis-Indice-Marginacion-Municipal-Mexico-2020/main/IMM_2020.xls",
                "fecha_descarga": TODAY,
                "estado": "ok",
            }
        )
        print(f"  municipios {out['cve_municipio'].nunique()} desde {local[0].name}")
        return out
    candidates = github_conapo_candidates(http)
    candidates += [
        "https://raw.githubusercontent.com/JuveCampos/Indices-de-Marginacion/master/IMM_2020.csv",
        "https://raw.githubusercontent.com/JuveCampos/Marginacion/main/datos/IMM_2020.csv",
    ]
    errors = []
    out = None
    url = None
    for candidate in candidates:
        suffix = ".xlsx" if ".xlsx" in candidate.lower() else ".csv" if ".csv" in candidate.lower() else ".xls"
        digest = abs(hash(candidate)) % 10**8
        path = RAW / f"conapo_{digest}{suffix}"
        try:
            download(http, candidate, path)
            if path.stat().st_size < 1000:
                raise RuntimeError(f"archivo demasiado chico ({path.stat().st_size} bytes)")
            if suffix == ".csv":
                out = read_conapo_frame(path)
            else:
                out = read_conapo_frame(path)
            url = candidate
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidate} -> {exc}")
            out = None
    if out is None:
        raise RuntimeError("No se pudo descargar CONAPO.\n" + "\n".join(errors[:12]))
    fuentes.append(
        {
            "fuente": "CONAPO",
            "descripcion": "Índice y grado de marginación municipal 2020",
            "url": url,
            "fecha_descarga": TODAY,
            "estado": "ok",
        }
    )
    print(f"  municipios {out['cve_municipio'].nunique()}")
    return out


def html_links(http, page_url: str, timeout: int = 20) -> list[str]:
    response = http.get(page_url, timeout=timeout)
    response.raise_for_status()
    links = re.findall(r'href=["\']([^"\']+)["\']', response.text, flags=re.I)
    return [urljoin(page_url, link) for link in links]


def pick_year_links(links, years, needles) -> dict[int, str]:
    chosen = {}
    for year in years:
        hits = []
        for link in links:
            low = link.lower()
            if str(year) not in low:
                continue
            if not any(token in low for token in (".zip", ".csv", ".7z")):
                continue
            if any(token in low for token in needles):
                hits.append(link)
        if hits:
            hits.sort(key=len)
            chosen[year] = hits[0]
    return chosen


def largest_table(path: Path) -> Path:
    if path.suffix.lower() in {".csv", ".txt", ".dbf"}:
        return path
    if path.suffix.lower() != ".zip":
        return path
    with zipfile.ZipFile(path) as archive:
        members = [
            info for info in archive.infolist()
            if not info.is_dir() and not info.filename.startswith("__MACOSX")
        ]
        tables = [
            info for info in members
            if info.filename.lower().endswith((".csv", ".txt", ".dbf"))
        ]
        if not tables:
            nested = [info for info in members if info.filename.lower().endswith(".zip")]
            if not nested:
                raise RuntimeError(f"{path.name} no trae CSV ni DBF. Trae: {archive.namelist()[:8]}")
            nested.sort(key=lambda info: -info.file_size)
            member = nested[0]
            target = path.parent / (path.stem + "_" + Path(member.filename).name)
            if not target.exists() or target.stat().st_size == 0:
                print(f"  extrae {member.filename}", flush=True)
                with archive.open(member) as source, target.open("wb") as handle:
                    handle.write(source.read())
            return largest_table(target)
        tables.sort(key=lambda info: (not info.filename.lower().endswith((".csv", ".txt")), -info.file_size))
        member = tables[0]
        target = path.parent / (path.stem + "_" + Path(member.filename).name)
        if not target.exists() or target.stat().st_size == 0:
            print(f"  extrae {member.filename}", flush=True)
            with archive.open(member) as source, target.open("wb") as handle:
                handle.write(source.read())
        return target


def read_table_chunks(path: Path):
    table = largest_table(path)
    if table.suffix.lower() == ".dbf":
        from dbfread import DBF

        database = DBF(str(table), encoding="latin-1", ignore_missing_memofile=True)
        columns = list(database.field_names)

        def generate():
            batch = []
            for record in database:
                batch.append(record)
                if len(batch) >= 200000:
                    yield pd.DataFrame.from_records(batch)
                    batch = []
            if batch:
                yield pd.DataFrame.from_records(batch)

        return generate(), columns
    last_error = None
    attempts = [
        {"encoding": "latin-1", "sep": ",", "engine": "c"},
        {"encoding": "utf-8", "sep": ",", "engine": "c"},
        {"encoding": "latin-1", "sep": None, "engine": "python"},
    ]
    for kwargs in attempts:
        try:
            iterator = pd.read_csv(table, chunksize=250000, low_memory=False, **kwargs)
            first = next(iterator)

            def chain(first=first, iterator=iterator):
                yield first
                yield from iterator

            return chain(), list(first.columns)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"No se pudo leer {table.name}: {last_error}")


def find_column(columns, options, label):
    folded = {ascii_key(col): col for col in columns}
    for option in options:
        key = ascii_key(option)
        if key in folded:
            return folded[key]
    candidates = []
    for option in options:
        key = ascii_key(option)
        for folded_name, original in folded.items():
            if key and key in folded_name:
                candidates.append((len(folded_name), original))
    if candidates:
        candidates.sort()
        return candidates[0][1]
    raise SystemExit(f"No está la columna de {label}. Columnas: {columns[:40]}")


def as_int(series):
    return pd.to_numeric(series, errors="coerce")


def is_infant(age) -> bool:
    """Primer dígito de la clave INEGI/DGIS: 1 horas, 2 días, 3 meses, 4 años."""
    try:
        code = int(float(age))
    except (TypeError, ValueError):
        return False
    unit = code // 1000
    quantity = code % 1000
    if unit == 1:
        return True
    if unit == 2:
        return True
    if unit == 3:
        return quantity <= 11
    return False


def accumulate_inegi(http, fuentes, kind: str):
    print(f"INEGI {kind}...")
    if kind == "defunciones":
        page = "https://www.inegi.org.mx/programas/mortalidad/"
        needles = ("defun", "mortal")
        folder = "defunciones"
    else:
        page = "https://www.inegi.org.mx/programas/natalidad/"
        needles = ("nacim", "natal")
        folder = "nacimientos"
    try:
        links = html_links(http, page)
    except Exception as exc:  # noqa: BLE001
        print(f"  página de programa no disponible ({exc})")
        links = []
    if kind == "defunciones":
        try:
            links.extend(html_links(
                http,
                "http://www.dgis.salud.gob.mx/contenidos/basesdedatos/da_defunciones_gobmx.html",
            ))
        except Exception as exc:  # noqa: BLE001
            print(f"  página de defunciones DGIS no disponible ({exc})")
    found = pick_year_links(links, YEARS, needles)
    counts = {year: {} for year in YEARS}
    missing = []
    for year in YEARS:
        patterns = []
        if year in found:
            patterns.append(found[year])
        if kind == "defunciones":
            patterns = [
                f"http://www.dgis.salud.gob.mx/descargas/datosabiertos/defunciones/registro/DEFUN_{year}.zip",
            ]
            if year in found:
                patterns.append(found[year])
        else:
            patterns.extend(
                [
                    f"https://www.inegi.org.mx/contenidos/programas/natalidad/datosabiertos/{year}/conjunto_de_datos_natalidad_{year}_csv.zip",
                    f"https://www.inegi.org.mx/contenidos/programas/natalidad/datosabiertos/conjunto_de_datos_natalidad_{year}_csv.zip",
                    f"https://www.inegi.org.mx/contenidos/programas/natalidad/microdatos/{year}/conjunto_de_datos_natalidad_{year}_csv.zip",
                ]
            )
        dest = RAW / f"inegi_{kind}_{year}.zip"
        try:
            url = first_working(http, list(dict.fromkeys(patterns)), dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  {year} no disponible", flush=True)
            counts[year] = None
            missing.append(year)
            fuentes.append(
                {
                    "fuente": f"INEGI {kind} {year}",
                    "descripcion": f"No abrió. {exc}",
                    "url": patterns[0] if patterns else "",
                    "fecha_descarga": TODAY,
                    "estado": "no disponible",
                }
            )
            continue
        chunks, columns = read_table_chunks(dest)
        entity_col = find_column(columns, ["ent_resid", "ent_res", "entidad_residencia", "cve_ent_resid"], "entidad de residencia")
        mun_col = find_column(columns, ["mun_resid", "mun_res", "municipio_residencia", "cve_mun_resid"], "municipio de residencia")
        age_col = None
        if kind == "defunciones":
            age_col = find_column(columns, ["edad"], "edad")
        total = 0
        age_counts = None
        for chunk in chunks:
            entity = as_int(chunk[entity_col])
            mun = as_int(chunk[mun_col])
            mask = (entity == ENTITY) & mun.between(1, 106)
            if kind == "defunciones":
                infant = chunk.loc[mask, age_col].map(is_infant)
                selected = mun[mask][infant.to_numpy()]
                if year == YEARS[0]:
                    observed = chunk.loc[mask, age_col].astype(str).value_counts()
                    age_counts = observed if age_counts is None else age_counts.add(observed, fill_value=0)
            else:
                selected = mun[mask]
            total += int(selected.shape[0])
            for code, count in selected.value_counts().items():
                bucket = counts[year]
                bucket[int(code)] = bucket.get(int(code), 0) + int(count)
        print(f"  {year}: {total} registros de Yucatán", flush=True)
        if age_counts is not None:
            print("  edades más frecuentes en Yucatán, primer año:")
            print(age_counts.sort_values(ascending=False).head(12).to_string())
        fuentes.append(
            {
                "fuente": f"INEGI {kind} {year}",
                "descripcion": (
                    "Defunciones registradas de menores de 1 año por municipio de residencia habitual. "
                    "Microdatos abiertos de la DGIS, que publican la estadística vital de INEGI."
                    if kind == "defunciones"
                    else "Nacimientos registrados de INEGI, residencia habitual de la madre"
                ),
                "url": url,
                "fecha_descarga": TODAY,
                "estado": "ok",
            }
        )
        low, high = (80, 2500) if kind == "defunciones" else (15000, 60000)
        if not low <= total <= high:
            if age_counts is not None:
                print(age_counts.sort_values(ascending=False).head(20).to_string())
            raise SystemExit(
                f"El total {total} de {kind} {year} queda fuera del rango esperado ({low}-{high}). "
                "Hay que revisar el filtro antes de publicar el hallazgo."
            )
    return counts, missing


SINAC_URL = {
    2018: "http://www.dgis.salud.gob.mx/descargas/datosabiertos/nacimientos/sinac_2018.zip?V=2025.10.04",
    2019: "http://www.dgis.salud.gob.mx/descargas/datosabiertos/nacimientos/sinac_2019.zip?V=1.1",
    2020: "http://www.dgis.salud.gob.mx/descargas/datosabiertos/nacimientos/sinac_2020.zip?V=1.1",
    2021: "http://www.dgis.salud.gob.mx/descargas/datosabiertos/nacimientos/sinac_2021.zip?V=1.1",
    2022: "http://www.dgis.salud.gob.mx/descargas/datosabiertos/nacimientos/sinac_2022.zip?V=2023.05.23",
    2023: "http://www.dgis.salud.gob.mx/descargas/datosabiertos/nacimientos/sinac_2023.zip?V=2024.05.14",
}


def load_sinac(http, fuentes):
    print("SINAC, peso al nacer...")
    page = "http://www.dgis.salud.gob.mx/contenidos/basesdedatos/da_nacimientos_gobmx.html"
    try:
        links = html_links(http, page, timeout=8)
    except Exception as exc:  # noqa: BLE001
        print(f"  página de SINAC no disponible ({exc})")
        links = []
    found = pick_year_links(links, YEARS, ("nacim", "sinac", "sinba"))
    births = {year: {} for year in YEARS}
    low = {year: {} for year in YEARS}
    missing = []
    unit_note = ""
    for year in YEARS:
        dest = RAW / f"sinac_{year}.zip"
        candidates = [SINAC_URL[year]]
        if year in found and found[year] not in candidates:
            candidates.insert(0, found[year])
        try:
            url = first_working(http, list(dict.fromkeys(candidates)), dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  {year} no disponible", flush=True)
            births[year] = None
            low[year] = None
            missing.append(year)
            fuentes.append(
                {
                    "fuente": f"SINAC {year}",
                    "descripcion": f"No abrió. {exc}",
                    "url": candidates[0],
                    "fecha_descarga": TODAY,
                    "estado": "no disponible",
                }
            )
            continue
        chunks, columns = read_table_chunks(dest)
        mun_col = find_column(
            columns,
            ["mpo_res", "municipioresidencia", "mun_res", "mun_resid", "municipio_residencia", "cvemunicipioresidencia"],
            "municipio de residencia SINAC",
        )
        entity_col = find_column(
            columns,
            ["ent_res", "entidadresidencia", "ent_resid", "entidad_residencia", "cveentidadresidencia"],
            "entidad de residencia SINAC",
        )
        weight_col = find_column(columns, ["pesoh", "peso", "peso_nacer", "pesonacer"], "peso")
        weights = []
        for chunk in chunks:
            entity = as_int(chunk[entity_col])
            mun = as_int(chunk[mun_col])
            weight = as_int(chunk[weight_col])
            mask = (entity == ENTITY) & mun.between(1, 106)
            part = pd.DataFrame({"mun": mun[mask].to_numpy(), "peso": weight[mask].to_numpy()})
            weights.append(part)
        part = pd.concat(weights, ignore_index=True)
        observed = part["peso"].dropna()
        observed = observed[(observed > 0) & (observed < 9000)]
        median = float(observed.median()) if len(observed) else 0
        factor = 1
        if 15 <= median <= 80:
            factor = 100
            unit_note = "El peso de SINAC venía en hectogramos y se pasó a gramos."
        grams = part["peso"] * factor
        valid = grams.between(500, 6500)
        part = part.loc[valid.to_numpy()].copy()
        part["grams"] = grams[valid].to_numpy()
        for code, count in part["mun"].value_counts().items():
            births[year][int(code)] = int(count)
        small = part.loc[part["grams"] < 2500, "mun"]
        for code, count in small.value_counts().items():
            low[year][int(code)] = int(count)
        total = int(len(part))
        small_n = int((part["grams"] < 2500).sum())
        print(f"  {year}: {total} nacidos con peso válido, {small_n} con bajo peso, mediana {median}")
        if not 10000 <= total <= 70000:
            raise SystemExit(f"SINAC {year} tiene {total} registros válidos en Yucatán, fuera de lo esperado.")
        fuentes.append(
            {
                "fuente": f"SINAC {year}",
                "descripcion": "Nacidos vivos con peso al nacer, municipio de residencia de la madre. " + unit_note,
                "url": url,
                "fecha_descarga": TODAY,
                "estado": "ok",
            }
        )
    return births, low, unit_note, missing


def sum_years(counts, years, code) -> int:
    total = 0
    for year in years:
        bucket = counts.get(year)
        if not bucket:
            continue
        total += int(bucket.get(code, 0))
    return total


def available_years(counts) -> list[int]:
    return [year for year in YEARS if counts.get(year)]


def rate(numerator, denominator, scale):
    if denominator <= 0:
        return None
    return numerator / denominator * scale


def build_table(water, conapo, deaths, births, sinac_births, sinac_low):
    frame = water.merge(conapo, on="cve_municipio", how="left")
    imr_years = [year for year in YEARS if deaths.get(year) and births.get(year)]
    imr_off = [year for year in imr_years if year not in PANDEMIC]
    lbw_years = [year for year in YEARS if sinac_births.get(year)]
    lbw_off = [year for year in lbw_years if year not in PANDEMIC]
    rows = []
    for code in range(1, 107):
        death_n = sum_years(deaths, imr_years, code)
        birth_n = sum_years(births, imr_years, code)
        death_np = sum_years(deaths, imr_off, code)
        birth_np = sum_years(births, imr_off, code)
        sinac_n = sum_years(sinac_births, lbw_years, code)
        sinac_low_n = sum_years(sinac_low, lbw_years, code)
        sinac_np = sum_years(sinac_births, lbw_off, code)
        sinac_low_np = sum_years(sinac_low, lbw_off, code)
        rows.append(
            {
                "cve_municipio": code,
                "defunciones_infantiles": death_n,
                "nacimientos_inegi": birth_n,
                "imr": rate(death_n, birth_n, 1000),
                "defunciones_infantiles_sin_pandemia": death_np,
                "nacimientos_inegi_sin_pandemia": birth_np,
                "imr_sin_pandemia": rate(death_np, birth_np, 1000),
                "nacimientos_sinac": sinac_n,
                "bajo_peso_n": sinac_low_n,
                "bajo_peso_pct": rate(sinac_low_n, sinac_n, 100),
                "bajo_peso_pct_sin_pandemia": rate(sinac_low_np, sinac_np, 100),
            }
        )
    health = pd.DataFrame(rows)
    frame = frame.merge(health, on="cve_municipio", how="left")
    stable = frame["nacimientos_inegi"] >= STABLE_BIRTHS
    frame["estable"] = stable.astype(int)
    imr_cut = frame.loc[stable, "imr"].quantile(0.75)
    lbw_cut = frame.loc[frame["nacimientos_sinac"] >= STABLE_BIRTHS, "bajo_peso_pct"].quantile(0.75)
    frame["vulnerabilidad_alta"] = (
        stable
        & (
            (frame["imr"] >= imr_cut)
            | (
                (frame["nacimientos_sinac"] >= STABLE_BIRTHS)
                & (frame["bajo_peso_pct"] >= lbw_cut)
            )
        )
    ).astype(int)
    summary = group_summary(frame)
    sensitivity = group_summary(frame, pandemic_off=True)
    spearman = {}
    monitored = frame["grupo"].isin(["Con evidencia", "Monitoreado sin excedencia"]) & stable
    subset = frame.loc[monitored, ["n_parametros_excedidos", "imr", "bajo_peso_pct"]].dropna()
    spearman["n"] = int(len(subset))
    if len(subset) >= 10:
        rho_imr, _ = spearmanr(subset["n_parametros_excedidos"], subset["imr"])
        rho_lbw, _ = spearmanr(subset["n_parametros_excedidos"], subset["bajo_peso_pct"])
        spearman["rho_imr"] = float(rho_imr)
        spearman["rho_lbw"] = float(rho_lbw)
    else:
        spearman["rho_imr"] = None
        spearman["rho_lbw"] = None
    cuts = {"imr_p75": float(imr_cut) if pd.notna(imr_cut) else None, "lbw_p75": float(lbw_cut) if pd.notna(lbw_cut) else None}
    coverage = {"imr": imr_years, "lbw": lbw_years}
    return frame, summary, sensitivity, spearman, cuts, coverage


def group_summary(frame, pandemic_off=False):
    imr_col = "imr_sin_pandemia" if pandemic_off else "imr"
    lbw_col = "bajo_peso_pct_sin_pandemia" if pandemic_off else "bajo_peso_pct"
    birth_col = "nacimientos_inegi_sin_pandemia" if pandemic_off else "nacimientos_inegi"
    rows = []
    for grupo in ["Con evidencia", "Monitoreado sin excedencia", "Sin monitoreo"]:
        part = frame[frame["grupo"] == grupo]
        stable = part[part[birth_col] >= STABLE_BIRTHS]
        high_margin = part["gm_2020"].astype(str).str.contains("Alto", case=False, na=False)
        rows.append(
            {
                "grupo": grupo,
                "municipios": int(len(part)),
                "estables": int(len(stable)),
                "imr_mediana": round(float(stable[imr_col].median()), 2) if len(stable) else None,
                "lbw_mediana": round(float(stable[lbw_col].median()), 2) if stable[lbw_col].notna().any() else None,
                "marginacion_alta": int(high_margin.sum()),
            }
        )
    return pd.DataFrame(rows)


def fmt(value, digits=1):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "s.d."
    return f"{value:.{digits}f}"


def finding_text(frame, summary, sensitivity, spearman, cuts, quality, coverage) -> list[str]:
    by_group = {row.grupo: row for row in summary.itertuples()}
    evidence = by_group["Con evidencia"]
    watched = by_group["Monitoreado sin excedencia"]
    blind = by_group["Sin monitoreo"]
    medians = [evidence.imr_mediana, watched.imr_mediana, blind.imr_mediana]
    finite = [value for value in medians if value is not None and not pd.isna(value)]
    spread = max(finite) - min(finite) if finite else None
    separated = spread is not None and spread >= 3
    coincidence = frame[(frame["grupo"] == "Con evidencia") & (frame["vulnerabilidad_alta"] == 1)]
    gap = frame[(frame["grupo"] == "Sin monitoreo") & (frame["vulnerabilidad_alta"] == 1)]
    imr_label = ", ".join(str(year) for year in coverage["imr"]) or "ningún año"
    lbw_label = ", ".join(str(year) for year in coverage["lbw"]) or "ningún año"
    sentences = [
        (
            f"En 2018-2023 hay {int(evidence.municipios)} municipios con al menos una muestra subterránea "
            f"por encima de un límite de la NOM-127-SSA1-2021, {int(watched.municipios)} con monitoreo y sin esa excedencia, "
            f"y {int(blind.municipios)} sin muestra en la ventana."
        )
    ]
    if coverage["imr"] != YEARS:
        missing_imr = [str(year) for year in YEARS if year not in coverage["imr"]]
        sentences.append(
            f"La mortalidad infantil usa {imr_label}. El microdato de nacimientos registrados de INEGI "
            f"no abrió para {', '.join(missing_imr)}, así que ese año no entra ni en las defunciones ni en los nacimientos. "
            "No se rellena con otra fuente."
        )
        if coverage["lbw"] != YEARS:
            missing = [str(year) for year in YEARS if year not in coverage["lbw"]]
            sentences.append(
                f"El bajo peso usa {lbw_label}. SINAC no abrió para {', '.join(missing)}; "
                "esos años quedan fuera del porcentaje y no se rellenan con otra fuente."
            )
    if not finite:
        sentences.append("Con los microdatos que abrieron no se puede calcular la mediana de mortalidad infantil.")
    elif not separated:
        sentences.append(
            (
                f"Entre los municipios con al menos {STABLE_BIRTHS} nacimientos, la mediana de mortalidad infantil "
                f"es {fmt(evidence.imr_mediana)} por 1,000 en el grupo con evidencia, "
                f"{fmt(watched.imr_mediana)} en el monitoreado sin excedencia y {fmt(blind.imr_mediana)} sin monitoreo. "
                f"La de bajo peso al nacer es {fmt(evidence.lbw_mediana)}%, {fmt(watched.lbw_mediana)}% y {fmt(blind.lbw_mediana)}%. "
                "Los tres grupos no se separan. El hallazgo es el mapa de excedencias y de huecos de monitoreo, no una asociación."
            )
        )
    else:
        sentences.append(
            (
                f"Entre los municipios con al menos {STABLE_BIRTHS} nacimientos, la mediana de mortalidad infantil "
                f"es {fmt(evidence.imr_mediana)} por 1,000 con evidencia, {fmt(watched.imr_mediana)} con monitoreo sin excedencia "
                f"y {fmt(blind.imr_mediana)} sin monitoreo. El bajo peso mediano es {fmt(evidence.lbw_mediana)}%, "
                f"{fmt(watched.lbw_mediana)}% y {fmt(blind.lbw_mediana)}%."
            )
        )
    if separated and spearman["rho_imr"] is not None:
        sentences.append(
            (
                f"En los {spearman['n']} municipios monitoreados con denominador estable, el coeficiente de Spearman "
                f"entre el número de parámetros excedidos y la mortalidad infantil es {spearman['rho_imr']:.2f}, "
                f"y con el bajo peso es {spearman['rho_lbw']:.2f}. Es una descripción de rangos, no una causa."
            )
        )
    sentences.append(
        (
            f"La coincidencia que sí se puede señalar es de cobertura: {len(gap)} municipios del cuartil alto de "
            f"mortalidad infantil o de bajo peso no tienen monitoreo subterráneo en la ventana, y {len(coincidence)} "
            f"del mismo cuartil sí tienen una excedencia. El cuartil usa el percentil 75 "
            f"({fmt(cuts['imr_p75'])} muertes por 1,000 o {fmt(cuts['lbw_p75'])}% de bajo peso)."
        )
    )
    sens = {row.grupo: row.imr_mediana for row in sensitivity.itertuples()}
    base = {row.grupo: row.imr_mediana for row in summary.itertuples()}
    order_base = sorted(base, key=lambda name: (base[name] is None, base[name] or 0))
    order_sens = sorted(sens, key=lambda name: (sens[name] is None, sens[name] or 0))
    if order_base == order_sens:
        sentences.append(
            "Al quitar 2020 y 2021, el orden de las medianas de mortalidad infantil entre los tres grupos se mantiene."
        )
    else:
        sentences.append(
            "Al quitar 2020 y 2021 cambia el orden de las medianas de mortalidad infantil. Esa sensibilidad queda en la tabla de verificación."
        )
    sentences.append(
        (
            f"El muestreo de la ventana se concentra en {quality['top_mun']} "
            f"({quality['top_pct']}% de las muestras). Dureza y sólidos disueltos se reportan aparte y no entran al conteo de contaminación."
        )
    )
    return sentences


def register_fonts():
    regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    pdfmetrics.registerFont(TTFont("Arial", regular))
    pdfmetrics.registerFont(TTFont("Arial-Bold", bold))


class BarChart(Flowable):
    def __init__(self, summary, width, height=118):
        super().__init__()
        self.summary = summary
        self.width = width
        self.height = height

    def draw(self):
        canvas = self.canv
        summary = self.summary
        panel_w = self.width / 2 - 8
        series = [
            ("Mortalidad infantil por 1,000", "imr_mediana", TEAL),
            ("Bajo peso al nacer, %", "lbw_mediana", SAND),
        ]
        labels = ["Con evidencia", "Sin excedencia", "Sin monitoreo"]
        keys = ["Con evidencia", "Monitoreado sin excedencia", "Sin monitoreo"]
        for panel, (title, column, color) in enumerate(series):
            left = panel * (panel_w + 16)
            canvas.setFillColor(INK)
            canvas.setFont("Arial-Bold", 8)
            canvas.drawString(left, self.height - 10, title)
            values = [float(summary.loc[summary.grupo == key, column].iloc[0] or 0) for key in keys]
            peak = max(values) or 1
            bottom = 16
            top = self.height - 28
            bar_h = (top - bottom) / 3 - 6
            for index, value in enumerate(values):
                y = top - (index + 1) * (bar_h + 6)
                canvas.setFillColor(MUTED)
                canvas.setFont("Arial", 7)
                canvas.drawString(left, y + 2, labels[index])
                bar_left = left + 78
                bar_width = (panel_w - 110) * (value / peak)
                canvas.setFillColor(color)
                canvas.roundRect(bar_left, y, max(bar_width, 1), bar_h - 2, 2, fill=1, stroke=0)
                canvas.setFillColor(INK)
                canvas.setFont("Arial", 7.5)
                canvas.drawString(bar_left + bar_width + 4, y + 2, fmt(value))


def p(text, style):
    return Paragraph(text, style)


def build_pdf(frame, params, summary, quality, sentences, path: Path, coverage):
    register_fonts()
    styles = {
        "kicker": ParagraphStyle("kicker", fontName="Arial", fontSize=8, textColor=TEAL, tracking=0.4, spaceAfter=1),
        "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=17, textColor=NAVY, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=10, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=2),
        "body": ParagraphStyle("body", fontName="Arial", fontSize=8, leading=10.4, textColor=INK, spaceAfter=3),
        "small": ParagraphStyle("small", fontName="Arial", fontSize=7.2, leading=9.2, textColor=INK),
        "question": ParagraphStyle("question", fontName="Arial", fontSize=8, leading=10.4, textColor=INK, backColor=PALE, borderPadding=4, spaceAfter=4),
    }
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=11 * mm,
        bottomMargin=12 * mm,
        title="Evidence Board K'IIN DATA",
        author="K'IIN DATA",
    )
    width = letter[0] - 28 * mm
    story = []
    story.append(p("EXPLORE  ·  EVIDENCE BOARD  ·  DATOSTADA MX 2026", styles["kicker"]))
    story.append(p("Agua subterránea, marginación y vulnerabilidad materno-infantil en Yucatán", styles["h1"]))
    story.append(p("Equipo K'IIN DATA  ·  Reto Yucatán Vivo  ·  14 de noviembre de 2026  ·  Municipio, 2018-2023", styles["small"]))
    story.append(Spacer(1, 4))
    story.append(p(
        "Pregunta del data brief, sin cambio: ¿Dónde coinciden en Yucatán la contaminación del agua subterránea "
        "(coliformes fecales, nitratos y metales), la marginación y la vulnerabilidad materno-infantil "
        "(mortalidad infantil y bajo peso al nacer), y existe una asociación espacial entre ellas a nivel municipal?",
        styles["question"],
    ))
    story.append(p("1. Datos usados", styles["h2"]))
    story.append(p(
        f"Agua: RENAMECA, archivo Subterraneo.xlsb, hojas SITIOS y RESULTADOS, filtrado a Yucatán. "
        f"Son {quality['n_sitios']} sitios subterráneos ({quality['n_pozos']} pozos y {quality['n_cenotes']} cenotes). "
        f"La ventana del cruce de agua es 2018-2023 y contiene {quality['n_muestras_ventana']} muestras. "
        f"Salud: defunciones de menores de un año en los microdatos abiertos de la DGIS, que publican la estadística vital de INEGI, "
        f"por municipio de residencia habitual. La tasa usa {', '.join(str(year) for year in coverage['imr']) or 'ningún año'}. "
        "El denominador es el de nacimientos registrados de INEGI, en esos mismos años. "
        f"Bajo peso: porcentaje de nacidos vivos con menos de 2,500 g en SINAC ({', '.join(str(year) for year in coverage['lbw']) or 'sin años'}), "
        "municipio de residencia de la madre. "
        "Marginación: índice y grado municipal CONAPO 2020. La tasa infantil es defunciones entre nacimientos, por 1,000.",
        styles["body"],
    ))
    story.append(p("2. Preparación y calidad", styles["h2"]))
    sparsest = params.sort_values("pct_muestras_con_resultado").iloc[0]
    story.append(p(
        "Los nombres municipales se normalizaron a la clave INEGI 1-106. Un valor con signo de menor que "
        "(por debajo del límite de detección) no cuenta como excedencia. Dureza total y sólidos disueltos se calculan aparte: "
        f"la NOM los limita en {DUR_LIMIT:.0f} y {SDT_LIMIT:.0f} mg/L y el brief no los usa como contaminación. "
        f"De las muestras de la ventana, {quality['top_pct']}% están en {quality['top_mun']}. "
        f"El parámetro con menos resultados es {sparsest['nombre']} ({sparsest['pct_muestras_con_resultado']}% de las muestras). "
        f"La serie del archivo también trae años {quality['anios'][0]}-{quality['anios'][-1]}; el cruce no los mezcla con la ventana.",
        styles["body"],
    ))
    story.append(PageBreak())
    story.append(p("3. Procedimiento", styles["h2"]))
    story.append(p(
        "Un municipio entra en «con evidencia» si alguna muestra de 2018-2023 rebasa la NOM-127-SSA1-2021 "
        "en coliformes fecales (1.1 NMP/100 mL o más), nitratos como N (11 mg/L), arsénico (0.025 mg/L), "
        "cadmio (0.005 mg/L), cromo total (0.05 mg/L), plomo (0.01 mg/L), mercurio (0.006 mg/L) o fluoruros (1.50 mg/L). "
        "Esos son los límites generales de las tablas 2, 4 y 6, no el cumplimiento gradual posterior. "
        "«Monitoreado sin excedencia» tuvo muestras y ninguna rebasó. «Sin monitoreo» no tuvo muestra en la ventana. "
        f"La comparación usa la mediana de los municipios con al menos {STABLE_BIRTHS} nacimientos de INEGI. "
        "La vulnerabilidad alta es el cuartil superior de esa mortalidad o de ese bajo peso. "
        "Spearman se calcula solo en municipios monitoreados y con ese denominador. "
        "La sensibilidad repite las medianas sin los registros de 2020 y 2021.",
        styles["body"],
    ))

    story.append(p("4. Resultados", styles["h2"]))
    story.append(p(
        "Medianas en municipios con al menos 100 nacimientos. Estables es ese subconjunto. Alta o muy alta es el grado de marginación 2020.",
        styles["small"],
    ))
    story.append(Spacer(1, 3))
    header = ["Grupo", "Municipios", "Estables", "Mortalidad infantil", "Bajo peso", "Alta o muy alta"]
    data = [header]
    for row in summary.itertuples():
        data.append([
            row.grupo,
            str(row.municipios),
            str(row.estables),
            f"{fmt(row.imr_mediana)} / 1,000",
            f"{fmt(row.lbw_mediana)}%",
            str(row.marginacion_alta),
        ])
    table = Table(data, colWidths=[width * x for x in (0.28, 0.12, 0.12, 0.18, 0.13, 0.17)])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Arial"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("BACKGROUND", (0, 1), (-1, 1), Color(0.98, 0.94, 0.88)),
        ("BACKGROUND", (0, 2), (-1, 2), Color(0.90, 0.95, 0.94)),
        ("BACKGROUND", (0, 3), (-1, 3), PALE),
        ("GRID", (0, 0), (-1, -1), 0.2, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(BarChart(summary, width))
    story.append(Spacer(1, 4))
    param_header = ["Parámetro", "Límite", "Municipios", "Muestras con excedencia", "Cobertura de la medición"]
    param_data = [param_header]
    for row in params.sort_values("municipios_con_excedencia", ascending=False).itertuples():
        rule = "≥" if row.parametro == "COLI_FEC" else ">"
        param_data.append([
            row.nombre,
            f"{rule} {row.limite:g} {row.unidad}",
            str(row.municipios_con_excedencia),
            str(row.muestras_con_excedencia),
            f"{row.pct_muestras_con_resultado}%",
        ])
    param_table = Table(param_data, colWidths=[width * x for x in (0.24, 0.22, 0.14, 0.22, 0.18)])
    param_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Arial"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.2, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, PALE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(param_table)
    story.append(Spacer(1, 3))
    story.append(p(
        f"El corte de coliformes por encima de 1,000 NMP/100 mL, usado en el tablero anterior, marca "
        f"{int(frame['coli_severo'].sum())} municipios. Aquí es un subconjunto severo y no define el grupo. "
        f"Sólidos disueltos por encima de 1,000 mg/L: {int(frame['sdt_excede'].sum())} municipios. "
        f"Dureza por encima de 500 mg/L: {int(frame['dureza_excede'].sum())} municipios.",
        styles["body"],
    ))

    story.append(PageBreak())
    story.append(p("5. Dónde hay vulnerabilidad alta y dónde falta monitoreo", styles["h2"]))
    story.append(p(
        "Vulnerabilidad alta: municipio con al menos 100 nacimientos cuya mortalidad infantil o cuyo bajo peso "
        "está en el cuartil superior estatal de los municipios estables. La lista completa está en el CSV.",
        styles["small"],
    ))

    def mini(title, subset):
        subset = subset.sort_values(["imr", "bajo_peso_pct"], ascending=False)
        head = ["Municipio", "IMR", "Bajo peso", "Marginación", "Parámetro"]
        data = [head]
        for row in subset.head(8).itertuples():
            data.append([
                row.municipio,
                fmt(row.imr),
                f"{fmt(row.bajo_peso_pct)}%",
                str(row.gm_2020),
                row.parametro_principal or "—",
            ])
        if len(subset) == 0:
            data.append(["Ninguno con esta definición", "", "", "", ""])
        extra = ""
        if len(subset) > 8:
            extra = f" Hay {len(subset) - 8} municipios más en el CSV."
        label = p(f"{title} ({len(subset)}).{extra}", styles["body"])
        mini_table = Table(data, colWidths=[width * x for x in (0.24, 0.14, 0.16, 0.22, 0.24)])
        mini_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Arial"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("GRID", (0, 0), (-1, -1), 0.2, LINE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, PALE]),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return KeepTogether([label, mini_table, Spacer(1, 4)])

    story.append(mini(
        "Cuartil alto de salud y excedencia de agua",
        frame[(frame.grupo == "Con evidencia") & (frame.vulnerabilidad_alta == 1)],
    ))
    story.append(mini(
        "Cuartil alto de salud sin monitoreo subterráneo",
        frame[(frame.grupo == "Sin monitoreo") & (frame.vulnerabilidad_alta == 1)],
    ))
    story.append(p("6. Hallazgo", styles["h2"]))
    for sentence in sentences:
        story.append(p(sentence, styles["body"]))
    story.append(p("7. Límites", styles["h2"]))
    story.append(p(
        "La unidad es el municipio: una excedencia en un pozo no describe el agua que bebe cada hogar, y una tasa municipal "
        "no describe un riesgo individual. La NOM-127 es de agua para uso y consumo humano; aquí se aplica a pozos y cenotes "
        "de la red de monitoreo, que no son una muestra de tomas domiciliarias. El muestreo es irregular y está concentrado. "
        "Varios parámetros tienen muchos vacíos, así que «sin excedencia» puede ser ausencia de medición de ese parámetro. "
        "Los municipios con pocos nacimientos tienen tasas inestables; por eso la mediana usa un piso de 100 nacimientos. "
        "Marginación, servicios y la pandemia se cruzan con la salud, y este corte no los separa. "
        "La relación que se describe es una asociación espacial, no una causa. RENAMECA no mide plaguicidas.",
        styles["body"],
    ))
    story.append(p(
        "Verificación: data/processed/municipios_yucatan_2018_2023.csv, "
        "data/processed/excedencias_por_parametro.csv y data/processed/fuentes.csv. "
        "El script es scripts/evidence_board.py. "
        "Uso de IA: el entorno de Cursor ayudó a localizar las fuentes abiertas, escribir el script y redactar este reporte. "
        "Las cifras salen del script y se revisan contra los CSV.",
        styles["small"],
    ))

    page_counter = {"n": 0}

    def footer(canvas, document):
        page_counter["n"] = document.page
        canvas.saveState()
        canvas.setFillColor(TEAL)
        canvas.rect(0, letter[1] - 8, letter[0], 8, fill=1, stroke=0)
        canvas.setFillColor(MUTED)
        canvas.setFont("Arial", 7)
        canvas.drawString(14 * mm, 6 * mm, "K'IIN DATA  ·  Evidence Board  ·  Yucatán Vivo")
        canvas.drawRightString(letter[0] - 14 * mm, 6 * mm, f"{document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF escrito en {path} ({path.stat().st_size} bytes, {page_counter['n']} páginas)")
    return page_counter["n"]


def stage(name, fuentes, compute):
    path = OUT / f"stage_{name}_v1.pkl"
    if path.exists():
        print(f"Usando caché de {name}.", flush=True)
        data, rows = pickle.loads(path.read_bytes())
        fuentes.extend(rows)
        return data
    before = len(fuentes)
    data = compute()
    path.write_bytes(pickle.dumps((data, fuentes[before:])))
    return data


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    by_key = check_catalog()
    water, params, quality = load_water(by_key)
    http = session()
    fuentes = [
        {
            "fuente": "CONAGUA RENAMECA",
            "descripcion": "Monitoreo subterráneo, hojas SITIOS y RESULTADOS, recorte Yucatán",
            "url": "archivo local data/Subterraneo.xlsb",
            "fecha_descarga": TODAY,
            "estado": "ok",
        }
    ]
    conapo = load_conapo(http, fuentes)
    deaths, _missing_deaths = stage(
        "defunciones", fuentes, lambda: accumulate_inegi(http, fuentes, "defunciones")
    )
    births, _missing_births = stage(
        "nacimientos", fuentes, lambda: accumulate_inegi(http, fuentes, "nacimientos")
    )
    sinac_births, sinac_low, _note, _missing_sinac = stage(
        "sinac", fuentes, lambda: load_sinac(http, fuentes)
    )
    frame, summary, sensitivity, spearman, cuts, coverage = build_table(
        water, conapo, deaths, births, sinac_births, sinac_low
    )
    sentences = finding_text(frame, summary, sensitivity, spearman, cuts, quality, coverage)
    print("\n".join(sentences))
    print(summary.to_string(index=False))
    print("Sensibilidad")
    print(sensitivity.to_string(index=False))

    municipal_path = OUT / "municipios_yucatan_2018_2023.csv"
    frame.sort_values("cve_municipio").to_csv(municipal_path, index=False, encoding="utf-8-sig")
    params.to_csv(OUT / "excedencias_por_parametro.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(fuentes).to_csv(OUT / "fuentes.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUT / "resumen_grupos.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(OUT / "resumen_grupos_sin_pandemia.csv", index=False, encoding="utf-8-sig")
    build_pdf(frame, params, summary, quality, sentences, PDF_PATH, coverage)
    if len(frame) != 106:
        raise SystemExit(f"La tabla tiene {len(frame)} filas, no 106.")
    print(f"Tabla: {municipal_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
