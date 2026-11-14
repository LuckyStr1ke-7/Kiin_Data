#!/usr/bin/env python3
"""Dashboard de K'IIN DATA para Datostada MX 2026.

Escribe un .twbx que Tableau abre, el PDF de respaldo y la nota de fuentes.
Una interacción: el parámetro Grupo de monitoreo recorta todas las vistas.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def formula_attr(text: str) -> str:
    """Escape a Tableau formula so it can sit inside a double-quoted attribute."""
    return escape(text, {'"': "&quot;"})

import pandas as pd
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
    Flowable,
    CondPageBreak,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "documents"
PROCESSED = ROOT / "data" / "processed"
SRC = PROCESSED / "municipios_yucatan_2018_2023.csv"
RESUMEN = PROCESSED / "resumen_grupos.csv"
PARAMS = PROCESSED / "excedencias_por_parametro.csv"
OFFICIAL = Path("/Users/a/Desktop/datostada-mx-2026/equipos/kiin-data/03-dashboard")

MUN = "federated.municipios"
RES = "federated.resumen"
EXC = "federated.excedencias"
PAR = "Parameters"
GROUPS = ("Con evidencia", "Monitoreado sin excedencia", "Sin monitoreo")
COLORS = {
    "Con evidencia": "#C47B2B",
    "Monitoreado sin excedencia": "#1F6F6A",
    "Sin monitoreo": "#8AA0A8",
}
FLAGS = (
    ("ex_COLI_FEC", "Coliformes fecales", "1.1", "NMP/100 mL"),
    ("ex_N_NO3", "Nitratos (N)", "11", "mg/L"),
    ("ex_AS_TOT", "Arsénico", "0.025", "mg/L"),
    ("ex_CD_TOT", "Cadmio", "0.005", "mg/L"),
    ("ex_CR_TOT", "Cromo total", "0.05", "mg/L"),
    ("ex_PB_TOT", "Plomo", "0.01", "mg/L"),
    ("ex_HG_TOT", "Mercurio", "0.006", "mg/L"),
    ("ex_FLUORUROS_TOT", "Fluoruros", "1.5", "mg/L"),
)

NAVY = Color(0.106, 0.227, 0.294)
TEAL = Color(0.122, 0.435, 0.416)
SAND = Color(0.769, 0.482, 0.169)
INK = Color(0.110, 0.141, 0.157)
MUTED = Color(0.361, 0.420, 0.451)
LINE = Color(0.835, 0.871, 0.890)
PALE = Color(0.945, 0.957, 0.965)
W_PX, H_PX = 1440, 3600


def q(source: str, field: str) -> str:
    return f"[{source}].{field}"


def inst(column: str, derivation: str, kind: str) -> str:
    prefix = {"None": "none", "Avg": "avg", "Sum": "sum", "Median": "median"}[derivation]
    suffix = {"nominal": "nk", "ordinal": "ok", "quantitative": "qk"}[kind]
    return f"[{prefix}:{column}:{suffix}]"


def ref(source: str, column: str, derivation: str, kind: str) -> str:
    return q(source, inst(column, derivation, kind))


def gx(px: float) -> int:
    return int(round(px / W_PX * 100000))


def gy(px: float) -> int:
    return int(round(px / H_PX * 100000))


def kind_of(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series) or pd.api.types.is_bool_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "real"
    return "string"


def remote_type(kind: str) -> int:
    return {"integer": 20, "real": 5, "string": 129}[kind]


def datasource_xml(name: str, caption: str, filename: str, frame: pd.DataFrame, extra_columns: str = "") -> str:
    table = f"[{filename.replace('.csv', '#csv')}]"
    columns, metadata, fields = [], [], []
    for ordinal, column in enumerate(frame.columns):
        kind = kind_of(frame[column])
        if kind == "string" or column in {"cve_municipio", "estable", "vulnerabilidad_alta"}:
            role, semantic, aggregation = "dimension", "nominal", "Count"
        else:
            role, semantic, aggregation = "measure", "quantitative", "Avg"
        columns.append(f'<column datatype="{kind}" name="{escape(column)}" ordinal="{ordinal}" />')
        metadata.append(
            "<metadata-record class='column'>"
            f"<remote-name>{escape(column)}</remote-name>"
            f"<remote-type>{remote_type(kind)}</remote-type>"
            f"<local-name>[{escape(column)}]</local-name>"
            f"<parent-name>{table}</parent-name>"
            f"<remote-alias>{escape(column)}</remote-alias>"
            f"<ordinal>{ordinal}</ordinal>"
            f"<local-type>{kind}</local-type>"
            f"<aggregation>{aggregation}</aggregation>"
            "<contains-null>true</contains-null>"
            f"<object-id>{table}</object-id>"
            "</metadata-record>"
        )
        fields.append(
            f'<column datatype="{kind}" name="[{escape(column)}]" role="{role}" type="{semantic}" />'
        )
    formula = '[Parameters].[Grupo de monitoreo] = "(Todos)" OR [grupo] = [Parameters].[Grupo de monitoreo]'
    fields.append(
        '<column caption="En el grupo elegido" datatype="boolean" name="[En grupo]" role="dimension" type="nominal">'
        f'<calculation class="tableau" formula="{formula_attr(formula)}" />'
        "</column>"
    )
    fields.append(extra_columns)
    return f"""
    <datasource caption="{escape(caption)}" inline="true" name="{name}" version="18.1">
      <connection class="federated">
        <named-connections>
          <named-connection caption="{escape(caption)}" name="textscan.{name}">
            <connection class="textscan" directory="Data" filename="{escape(filename)}" password="" server="" />
          </named-connection>
        </named-connections>
        <relation connection="textscan.{name}" name="{escape(filename)}" table="{table}" type="table">
          <columns character-set="UTF-8" header="yes" locale="en_US" separator=",">{''.join(columns)}</columns>
        </relation>
        <metadata-records>
          {''.join(metadata)}
        </metadata-records>
      </connection>
      <aliases enabled="yes" />
      {''.join(fields)}
      <layout dim-ordering="alphabetic" measure-ordering="alphabetic" show-structure="true" />
      <semantic-values>
        <semantic-value key="[Country].[Name]" value="&quot;Mexico&quot;" />
      </semantic-values>
    </datasource>
    """


def parameter_xml() -> str:
    members = '<member alias="Todos los grupos" value="&quot;(Todos)&quot;" />'
    members += "".join(f'<member value="&quot;{escape(grupo)}&quot;" />' for grupo in GROUPS)
    return f"""
    <datasource caption="Parameters" inline="true" name="{PAR}" version="18.1">
      <aliases enabled="yes" />
      <column caption="Grupo de monitoreo" datatype="string" name="[Grupo de monitoreo]" param-domain-type="list" role="measure" type="nominal" value="&quot;(Todos)&quot;">
        <calculation class="tableau" formula="&quot;(Todos)&quot;" />
        <members>{members}</members>
      </column>
    </datasource>
    """


def dep_field(column: str, datatype: str, role: str, semantic: str, derivation: str, fmt: str | None = None) -> str:
    formatted = f'<default-format format-string="{fmt}" />' if fmt else ""
    return (
        f'<column datatype="{datatype}" name="[{escape(column)}]" role="{role}" type="{semantic}">{formatted}</column>'
        f'<column-instance column="[{escape(column)}]" derivation="{derivation}" name="{inst(column, derivation, semantic)}" pivot="key" type="{semantic}" />'
    )


def dependencies(source: str, fields: list[tuple[str, str, str, str]]) -> str:
    """fields: column, datatype, semantic, derivation."""
    calc = '[Parameters].[Grupo de monitoreo] = "(Todos)" OR [grupo] = [Parameters].[Grupo de monitoreo]'
    blocks = [
        '<column caption="En el grupo elegido" datatype="boolean" name="[En grupo]" role="dimension" type="nominal">'
        f'<calculation class="tableau" formula="{formula_attr(calc)}" />'
        "</column>",
        f'<column-instance column="[En grupo]" derivation="None" name="{inst("En grupo", "None", "nominal")}" pivot="key" type="nominal" />',
        dep_field("grupo", "string", "dimension", "nominal", "None"),
    ]
    for column, datatype, semantic, derivation in fields:
        if column == "grupo":
            continue
        role = "dimension" if semantic != "quantitative" else "measure"
        fmt = "n#,##0.00" if column in {"imr_mediana", "lbw_mediana"} else None
        blocks.append(dep_field(column, datatype, role, semantic, derivation, fmt))
    param = (
        f'<datasource-dependencies datasource="{PAR}">'
        '<column caption="Grupo de monitoreo" datatype="string" name="[Grupo de monitoreo]" param-domain-type="list" '
        'role="measure" type="nominal" value="&quot;(Todos)&quot;">'
        '<calculation class="tableau" formula="&quot;(Todos)&quot;" />'
        "</column></datasource-dependencies>"
    )
    return (
        f'<datasource-dependencies datasource="{source}">{"".join(blocks)}</datasource-dependencies>'
        + param
    )


def choice_filter(source: str) -> str:
    field = ref(source, "En grupo", "None", "nominal")
    return (
        f'<filter class="categorical" column="{field}">'
        f'<groupfilter function="member" level="{inst("En grupo", "None", "nominal")}" member="true" />'
        "</filter>"
    )


def palette() -> str:
    maps = []
    for grupo, color in COLORS.items():
        maps.append(
            f'<map to="{color}"><bucket>&quot;{escape(grupo)}&quot;</bucket></map>'
        )
    field = "[none:grupo:nk]"
    return (
        '<style-rule element="mark">'
        f'<encoding attr="color" field="{field}" type="palette">{"".join(maps)}</encoding>'
        "</style-rule>"
    )


def group_sort(source: str) -> str:
    buckets = "".join(f"<bucket>&quot;{escape(grupo)}&quot;</bucket>" for grupo in GROUPS)
    return (
        f'<manual-sort column="{ref(source, "grupo", "None", "nominal")}" direction="ASC">'
        f"<dictionary>{buckets}</dictionary></manual-sort>"
    )


def sheet(name, title, source, caption, rows, cols, fields, encodings, extra_filters="", extra_slices=(), mark="Bar", header="8", sorts="") -> str:
    return f"""
    <worksheet name="{escape(name)}">
      <layout-options>
        <title>
          <formatted-text>
            <run fontcolor="#1B3A4B" fontname="Tableau Medium" fontsize="11">{escape(title)}</run>
          </formatted-text>
        </title>
      </layout-options>
      <table>
        <view>
          <datasources>
            <datasource caption="{escape(caption)}" name="{source}" />
            <datasource caption="Parameters" name="{PAR}" />
          </datasources>
          {dependencies(source, fields)}
          {choice_filter(source)}
          {extra_filters}
          <slices>
            <column>{ref(source, "En grupo", "None", "nominal")}</column>
            {''.join(f'<column>{item}</column>' for item in extra_slices)}
          </slices>
          <aggregation value="true" />
          {group_sort(source)}
          {sorts}
        </view>
        <style>
          <style-rule element="header"><format attr="font-size" value="{header}" /></style-rule>
          <style-rule element="axis"><format attr="font-size" value="9" /></style-rule>
          <style-rule element="label"><format attr="font-size" value="8" /></style-rule>
          <style-rule element="title"><format attr="font-size" value="11" /></style-rule>
          {palette()}
        </style>
        <panes>
          <pane selection-relaxation-option="selection-relaxation-allow">
            <view><breakdown value="auto" /></view>
            <mark class="{mark}" />
            <encodings>{encodings}</encodings>
            <style>{palette()}</style>
          </pane>
        </panes>
        <rows>{rows}</rows>
        <cols>{cols}</cols>
      </table>
    </worksheet>
    """


def member_filter(source: str, column: str, member: str, kind: str = "nominal") -> str:
    field = ref(source, column, "None", kind)
    level = inst(column, "None", kind)
    return (
        f'<filter class="categorical" column="{field}">'
        f'<groupfilter function="member" level="{level}" member="{member}" />'
        "</filter>"
    )


def build_twb() -> str:
    main_rows = f'({ref(MUN, "grupo", "None", "nominal")} / {ref(MUN, "municipio", "None", "nominal")})'
    main_cols = ref(MUN, "imr", "Avg", "quantitative")
    main = sheet(
        "Vista principal",
        "106 municipios. La barra es la mortalidad infantil por 1,000. El gris es el hueco: sin muestra en 2018-2023.",
        MUN,
        "Municipios",
        main_rows,
        main_cols,
        [
            ("municipio", "string", "nominal", "None"),
            ("imr", "real", "quantitative", "Avg"),
            ("bajo_peso_pct", "real", "quantitative", "Avg"),
            ("n_muestras", "integer", "quantitative", "Sum"),
            ("nacimientos_inegi", "integer", "quantitative", "Sum"),
            ("parametro_principal", "string", "nominal", "None"),
        ],
        encodings=(
            f'<color column="{ref(MUN, "grupo", "None", "nominal")}" />'
            f'<tooltip column="{ref(MUN, "n_muestras", "Sum", "quantitative")}" />'
            f'<tooltip column="{ref(MUN, "bajo_peso_pct", "Avg", "quantitative")}" />'
            f'<tooltip column="{ref(MUN, "nacimientos_inegi", "Sum", "quantitative")}" />'
            f'<tooltip column="{ref(MUN, "parametro_principal", "None", "nominal")}" />'
        ),
        header="7",
        sorts=(
            f'<computed-sort column="{ref(MUN, "municipio", "None", "nominal")}" direction="DESC" '
            f'using="{ref(MUN, "imr", "Avg", "quantitative")}" />'
        ),
    )
    med_imr = sheet(
        "Mediana de mortalidad",
        "Mediana por 1,000, municipios con al menos 100 nacimientos. Todos: 10.18 (n=36), 10.88 (n=27) y 10.85 (n=42). A un decimal: 10.2, 10.9 y 10.8. No se separan.",
        RES,
        "Grupos",
        ref(RES, "grupo", "None", "nominal"),
        ref(RES, "imr_mediana", "Avg", "quantitative"),
        [
            ("imr_mediana", "real", "quantitative", "Avg"),
            ("estables", "integer", "quantitative", "Avg"),
        ],
        encodings=(
            f'<color column="{ref(RES, "grupo", "None", "nominal")}" />'
            f'<text column="{ref(RES, "imr_mediana", "Avg", "quantitative")}" />'
            f'<tooltip column="{ref(RES, "estables", "Avg", "quantitative")}" />'
        ),
    )
    med_lbw = sheet(
        "Mediana de bajo peso",
        "Mediana de bajo peso, %. Todos: 7.72 (n=36), 8.9 (n=27) y 7.73 (n=42). A un decimal: 7.7, 8.9 y 7.7. No se separan.",
        RES,
        "Grupos",
        ref(RES, "grupo", "None", "nominal"),
        ref(RES, "lbw_mediana", "Avg", "quantitative"),
        [("lbw_mediana", "real", "quantitative", "Avg"), ("estables", "integer", "quantitative", "Avg")],
        encodings=(
            f'<color column="{ref(RES, "grupo", "None", "nominal")}" />'
            f'<text column="{ref(RES, "lbw_mediana", "Avg", "quantitative")}" />'
            f'<tooltip column="{ref(RES, "estables", "Avg", "quantitative")}" />'
        ),
    )
    exc = sheet(
        "Excedencias por parámetro",
        "Municipios con al menos una muestra sobre la NOM-127. Con todos los grupos: coliformes 29, nitratos 12, arsénico 7, cadmio 0, cromo 4, plomo 0, mercurio 0, fluoruros 6.",
        EXC,
        "Excedencias",
        ref(EXC, "parametro", "None", "nominal"),
        ref(EXC, "municipios", "Sum", "quantitative"),
        [("parametro", "string", "nominal", "None"), ("municipios", "integer", "quantitative", "Sum")],
        encodings=f'<text column="{ref(EXC, "municipios", "Sum", "quantitative")}" />',
        mark="Bar",
    )
    accion = sheet(
        "Sin monitoreo en el cuartil alto",
        "Acción: 20 municipios del cuartil alto (13.8 muertes por 1,000 o 9.2% de bajo peso) sin muestra. La barra es la mortalidad y la etiqueta es el % de bajo peso. Con otro grupo, esta lista se vacía.",
        MUN,
        "Municipios",
        ref(MUN, "municipio", "None", "nominal"),
        ref(MUN, "imr", "Avg", "quantitative"),
        [
            ("municipio", "string", "nominal", "None"),
            ("imr", "real", "quantitative", "Avg"),
            ("bajo_peso_pct", "real", "quantitative", "Avg"),
            ("nacimientos_inegi", "integer", "quantitative", "Sum"),
            ("n_muestras", "integer", "quantitative", "Sum"),
            ("gm_2020", "string", "nominal", "None"),
            ("vulnerabilidad_alta", "integer", "nominal", "None"),
        ],
        encodings=(
            f'<color column="{ref(MUN, "grupo", "None", "nominal")}" />'
            f'<text column="{ref(MUN, "bajo_peso_pct", "Avg", "quantitative")}" />'
            f'<tooltip column="{ref(MUN, "gm_2020", "None", "nominal")}" />'
            f'<tooltip column="{ref(MUN, "nacimientos_inegi", "Sum", "quantitative")}" />'
            f'<tooltip column="{ref(MUN, "n_muestras", "Sum", "quantitative")}" />'
        ),
        extra_filters=(
            member_filter(MUN, "vulnerabilidad_alta", "1")
            + member_filter(MUN, "grupo", "&quot;Sin monitoreo&quot;")
        ),
        extra_slices=(
            ref(MUN, "vulnerabilidad_alta", "None", "nominal"),
            ref(MUN, "grupo", "None", "nominal"),
        ),
        sorts=(
            f'<computed-sort column="{ref(MUN, "municipio", "None", "nominal")}" direction="DESC" '
            f'using="{ref(MUN, "imr", "Avg", "quantitative")}" />'
        ),
    )
    sheets = ["Vista principal", "Mediana de mortalidad", "Mediana de bajo peso", "Excedencias por parámetro", "Sin monitoreo en el cuartil alto"]
    viewpoints = "".join(
        f'<viewpoint name="{escape(name)}"><zoom type="entire-view" /></viewpoint>' for name in sheets
    )
    windows = "".join(
        f"""
        <window class="worksheet" name="{escape(name)}">
          <cards>
            <edge name="left"><strip size="160"><card type="pages" /><card type="filters" /><card type="marks" /></strip></edge>
            <edge name="top">
              <strip size="31"><card type="columns" /></strip>
              <strip size="31"><card type="rows" /></strip>
              <strip size="31"><card type="title" /></strip>
            </edge>
          </cards>
        </window>"""
        for name in sheets
    )
    header = """<run bold="true" fontcolor="#1B3A4B" fontname="Tableau Bold" fontsize="15">El hueco de monitoreo del agua subterránea no es un gradiente de salud materno-infantil</run>
              <run>&#10;</run>
              <run fontcolor="#1C2428" fontsize="10">En los municipios con al menos 100 nacimientos, la mediana de mortalidad infantil es 10.2 (con evidencia), 10.9 (monitoreado sin excedencia) y 10.8 (sin monitoreo) por 1,000. El bajo peso mediano es 7.7%, 8.9% y 7.7%. Los tres grupos no se separan.</run>
              <run>&#10;</run>
              <run fontcolor="#1C2428" fontsize="10">El hallazgo es la cobertura: 20 municipios del cuartil alto no tienen muestra en 2018-2023 y 12 de ese cuartil sí tienen una excedencia. Otros 14 de ese cuartil están monitoreados y no rebasan la NOM. Unidades: muertes por 1,000 nacimientos; porcentaje de nacidos vivos con menos de 2,500 g; límites NOM-127-SSA1-2021 en mg/L o NMP/100 mL.</run>
              <run>&#10;</run>
              <run fontcolor="#1F6F6A" fontsize="10">Interacción única: Grupo de monitoreo, arriba a la derecha. Recorta las cinco vistas. «Todos los grupos» deja el estado completo.</run>"""
    footer = """<run bold="true" fontcolor="#1B3A4B" fontsize="9">Fuentes y periodos. </run>
              <run fontcolor="#1C2428" fontsize="9">RENAMECA subterráneo (CONAGUA), data/Subterraneo.xlsb, 2018-2023: 121 sitios (113 pozos y 8 cenotes) y 366 muestras. CONAPO, grado de marginación municipal 2020. Defunciones de menores de 1 año: microdatos DGIS que publican la estadística vital de INEGI, residencia habitual, 2018-2022. Nacimientos registrados INEGI, residencia de la madre, 2018-2022. El archivo de nacimientos 2023 no abrió: 2023 no entra ni en muertes ni en nacimientos, y no se rellena con otra fuente. Bajo peso: SINAC 2018-2023, menos de 2,500 g, residencia de la madre.</run>
              <run>&#10;</run>
              <run bold="true" fontcolor="#1B3A4B" fontsize="9">Grupos. </run>
              <run fontcolor="#1C2428" fontsize="9">Con evidencia (36): al menos una muestra de la ventana sobre la NOM-127 en coliformes fecales (1.1 NMP/100 mL), nitratos como N (11 mg/L), arsénico (0.025), cadmio (0.005), cromo (0.05), plomo (0.01), mercurio (0.006) o fluoruros (1.5 mg/L). Monitoreado sin excedencia (27): hay muestra y ninguna de esas excedencias. Sin monitoreo (43): ninguna muestra en la ventana. Dureza y sólidos disueltos se reportan aparte y no definen el grupo. Coliformes por encima de 1,000 NMP/100 mL son un subconjunto severo de 5 municipios (Cuzamá, Espita, Homún, Kopomá y Mérida), no la definición del grupo.</run>
              <run>&#10;</run>
              <run bold="true" fontcolor="#1B3A4B" fontsize="9">Límites. </run>
              <run fontcolor="#1C2428" fontsize="9">El muestreo se concentra en Mérida (82 de 366 muestras, 22.4%). Varios parámetros tienen muchos blancos o valores bajo detección. La NOM-127 es de agua para uso y consumo humano y aquí se aplica a pozos y cenotes. La unidad es el municipio: no describe la exposición de cada hogar. El municipio de Quintana Roo tiene 75 nacimientos y queda fuera de la mediana y del cuartil. Sin 2020 y 2021 el orden cambia: 10.58 con evidencia, 9.45 monitoreado sin excedencia y 10.26 sin monitoreo, por 1,000. Descripción, no causalidad. Verificación: data/processed/municipios_yucatan_2018_2023.csv, también dentro de este libro.</run>"""
    return f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook original-version="18.1" source-build="2023.2.0 (20232.23.0611.1704)" source-platform="mac" version="18.1" xmlns:user="http://www.tableausoftware.com/xml/user">
  <preferences />
  <datasources>
    {parameter_xml()}
    {{mun}}
    {{res}}
    {{exc}}
  </datasources>
  <worksheets>
    {main}
    {med_imr}
    {med_lbw}
    {exc}
    {accion}
  </worksheets>
  <dashboards>
    <dashboard name="Cobertura y salud">
      <style>
        <style-rule element="dash-container"><format attr="background-color" value="#ffffff" /></style-rule>
      </style>
      <size maxheight="{H_PX}" maxwidth="{W_PX}" minheight="{H_PX}" minwidth="{W_PX}" sizing-mode="fixed" />
      <zones>
        <zone h="100000" id="2" type="layout-basic" w="100000" x="0" y="0">
          <zone h="100000" id="3" param="vert" type="layout-flow" w="100000" x="0" y="0">
            <zone h="8000" id="4" param="horz" type="layout-flow" w="100000">
              <zone forceUpdate="true" h="8000" id="10" type="text" w="74000">
                <formatted-text>{header}</formatted-text>
              </zone>
              <zone h="8000" id="30" param="vert" type="layout-flow" w="26000">
                <zone h="2800" id="20" mode="dropdown" param="[{PAR}].[Grupo de monitoreo]" type="paramctrl" w="26000" />
                <zone h="5200" id="21" name="Vista principal" pane-specification-id="0" param="{ref(MUN, 'grupo', 'None', 'nominal')}" show-title="false" type="color" w="26000" />
              </zone>
            </zone>
            <zone h="58000" id="5" param="horz" type="layout-flow" w="100000">
              <zone h="58000" id="11" name="Vista principal" show-title="true" w="64000" />
              <zone h="58000" id="6" param="vert" type="layout-flow" w="36000">
                <zone h="16000" id="12" name="Mediana de mortalidad" show-title="true" w="36000" />
                <zone h="16000" id="13" name="Mediana de bajo peso" show-title="true" w="36000" />
                <zone h="26000" id="14" name="Excedencias por parámetro" show-title="true" w="36000" />
              </zone>
            </zone>
            <zone h="20000" id="15" name="Sin monitoreo en el cuartil alto" show-title="true" w="100000" />
            <zone forceUpdate="true" h="14000" id="16" type="text" w="100000">
              <formatted-text>{footer}</formatted-text>
            </zone>
          </zone>
        </zone>
      </zones>
    </dashboard>
  </dashboards>
  <windows source-height="30">
    <window class="dashboard" maximized="true" name="Cobertura y salud">
      <viewpoints>{viewpoints}</viewpoints>
      <active id="-1" />
    </window>
    {windows}
  </windows>
</workbook>
"""


def long_exceedances(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, name, limit, unit in FLAGS:
        for grupo in GROUPS:
            rows.append({
                "grupo": grupo,
                "parametro": name,
                "limite": limit,
                "unidad": unit,
                "municipios": int(frame.loc[frame.grupo == grupo, column].sum()),
            })
    out = pd.DataFrame(rows)
    totals = out.groupby("parametro").municipios.sum().to_dict()
    expected = {
        "Coliformes fecales": 29, "Nitratos (N)": 12, "Arsénico": 7, "Cadmio": 0,
        "Cromo total": 4, "Plomo": 0, "Mercurio": 0, "Fluoruros": 6,
    }
    if totals != expected:
        raise SystemExit(f"Las excedencias no coinciden: {totals}")
    return out


def check_facts(frame: pd.DataFrame, resumen: pd.DataFrame) -> None:
    if len(frame) != 106:
        raise SystemExit("El CSV municipal no tiene 106 filas.")
    stable = frame[frame.nacimientos_inegi >= 100]
    shown = {}
    for grupo in GROUPS:
        part = stable[stable.grupo == grupo]
        shown[grupo] = f"{round(float(part.imr.median()), 2):.1f}"
    if shown != {"Con evidencia": "10.2", "Monitoreado sin excedencia": "10.9", "Sin monitoreo": "10.8"}:
        raise SystemExit(f"Medianas inesperadas: {shown}")
    published = {row.grupo: f"{row.imr_mediana:.2f}" for row in resumen.itertuples()}
    if published != {"Con evidencia": "10.18", "Monitoreado sin excedencia": "10.88", "Sin monitoreo": "10.85"}:
        raise SystemExit(f"resumen_grupos no coincide: {published}")
    high = frame[frame.vulnerabilidad_alta == 1]
    if int((high.grupo == "Sin monitoreo").sum()) != 20 or int((high.grupo == "Con evidencia").sum()) != 12:
        raise SystemExit("El cuartil alto no tiene 20 sin muestra y 12 con excedencia.")
    if int(frame.n_muestras.sum()) != 366 or round(100 * float(frame.loc[frame.municipio == "Mérida", "n_muestras"].iloc[0]) / 366, 1) != 22.4:
        raise SystemExit("La concentración en Mérida no es 22.4%.")


class MedianChart(Flowable):
    def __init__(self, resumen: pd.DataFrame, width: float, height: float = 112):
        super().__init__()
        self.resumen = resumen
        self.width = width
        self.height = height

    def draw(self):
        canvas = self.canv
        panel_w = self.width / 2 - 8
        series = [
            ("Mortalidad infantil por 1,000", "imr_mediana", TEAL, 16),
            ("Bajo peso al nacer, %", "lbw_mediana", SAND, 12),
        ]
        labels = ["Con evidencia", "Sin excedencia", "Sin monitoreo"]
        for panel, (title, column, color, peak) in enumerate(series):
            left = panel * (panel_w + 16)
            canvas.setFillColor(NAVY)
            canvas.setFont("Arial-Bold", 8)
            canvas.drawString(left, self.height - 10, title)
            bottom, top = 16, self.height - 24
            bar_h = (top - bottom) / 3 - 6
            axis_left = left + 78
            axis_w = panel_w - 118
            canvas.setStrokeColor(LINE)
            canvas.line(axis_left, bottom - 2, axis_left + axis_w, bottom - 2)
            for index, grupo in enumerate(GROUPS):
                value = float(self.resumen.loc[self.resumen.grupo == grupo, column].iloc[0])
                y = top - (index + 1) * (bar_h + 6)
                canvas.setFillColor(MUTED)
                canvas.setFont("Arial", 7)
                canvas.drawString(left, y + 3, labels[index])
                canvas.setFillColor(color)
                canvas.roundRect(axis_left, y, max(axis_w * (value / peak), 1), bar_h - 2, 2, fill=1, stroke=0)
                canvas.setFillColor(INK)
                canvas.setFont("Arial", 7.5)
                shown = {
                    "imr_mediana": {"Con evidencia": "10.2", "Monitoreado sin excedencia": "10.9", "Sin monitoreo": "10.8"},
                    "lbw_mediana": {"Con evidencia": "7.7", "Monitoreado sin excedencia": "8.9", "Sin monitoreo": "7.7"},
                }[column][grupo]
                canvas.drawString(axis_left + axis_w * (value / peak) + 4, y + 3, shown)
            canvas.setFillColor(MUTED)
            canvas.setFont("Arial", 6.5)
            canvas.drawString(axis_left, 1, "El eje parte de cero.")


def build_pdf(path: Path, frame: pd.DataFrame, resumen: pd.DataFrame, params: pd.DataFrame) -> None:
    pdfmetrics.registerFont(TTFont("Arial", "/System/Library/Fonts/Supplemental/Arial.ttf"))
    pdfmetrics.registerFont(TTFont("Arial-Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
    pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold")
    styles = {
        "kicker": ParagraphStyle("kicker", fontName="Arial", fontSize=8, textColor=TEAL, spaceAfter=1),
        "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=13, leading=16, textColor=NAVY, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=10, leading=13, textColor=NAVY, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("body", fontName="Arial", fontSize=8, leading=10.4, textColor=INK, spaceAfter=3),
        "small": ParagraphStyle("small", fontName="Arial", fontSize=7.2, leading=9.3, textColor=INK, spaceAfter=2),
        "white": ParagraphStyle("white", fontName="Arial", fontSize=7.2, leading=9.3, textColor=white),
    }
    doc = SimpleDocTemplate(
        str(path), pagesize=letter, leftMargin=13 * mm, rightMargin=13 * mm,
        topMargin=10 * mm, bottomMargin=11 * mm,
        title="Dashboard K'IIN DATA — cobertura del agua subterránea", author="K'IIN DATA",
    )
    width = letter[0] - 26 * mm

    def P(text, style="body"):
        return Paragraph(text, styles[style])

    high = frame[frame.vulnerabilidad_alta == 1]
    gap = high[high.grupo == "Sin monitoreo"].sort_values(["imr", "municipio"], ascending=[False, True])
    coincidence = high[high.grupo == "Con evidencia"].sort_values(["imr", "municipio"], ascending=[False, True])
    twelve = "; ".join(
        f"{row.municipio} ({row.imr:.1f} por 1,000, {row.parametro_principal})"
        for row in coincidence.itertuples()
    )
    severe = ", ".join(frame.loc[frame.coli_severo == 1, "municipio"].tolist())
    story = [
        P("DESIGN  ·  DASHBOARD  ·  DATOSTADA MX 2026  ·  RESPALDO DEL LIBRO TABLEAU", "kicker"),
        P("El hueco de monitoreo no es un gradiente de salud materno-infantil", "h1"),
        P("Equipo K'IIN DATA  ·  Yucatán Vivo  ·  14 de noviembre de 2026  ·  Municipio", "small"),
        Spacer(1, 3),
        P(
            "Pregunta, sin cambio y sin causalidad: ¿dónde coinciden en Yucatán la contaminación del agua subterránea "
            "(NOM-127-SSA1-2021: coliformes fecales, nitratos, metales y fluoruros), la marginación de CONAPO 2020 "
            "y la vulnerabilidad materno-infantil (mortalidad infantil y bajo peso al nacer)?",
            "body",
        ),
        P(
            "Entre los municipios con al menos 100 nacimientos de INEGI, la mediana de mortalidad infantil es "
            "<b>10.2</b> por 1,000 con evidencia, <b>10.9</b> en el monitoreado sin excedencia y <b>10.8</b> sin monitoreo. "
            "La de bajo peso al nacer es <b>7.7%</b>, <b>8.9%</b> y <b>7.7%</b>. Los tres grupos no se separan. "
            "El hallazgo es el mapa de excedencias y de huecos de monitoreo, no una asociación.",
        ),
    ]
    cards = Table([[
        Paragraph("<b>Con evidencia</b><br/>36 municipios<br/>10.2 por 1,000 · 7.7%", styles["white"]),
        Paragraph("<b>Monitoreado sin excedencia</b><br/>27 municipios<br/>10.9 por 1,000 · 8.9%", styles["white"]),
        Paragraph("<b>Sin monitoreo</b><br/>43 municipios<br/>10.8 por 1,000 · 7.7%", styles["white"]),
    ]], colWidths=[width / 3.0] * 3)
    cards.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), SAND),
        ("BACKGROUND", (1, 0), (1, 0), TEAL),
        ("BACKGROUND", (2, 0), (2, 0), Color(0.45, 0.50, 0.53)),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [
        cards, Spacer(1, 4), MedianChart(resumen, width), Spacer(1, 2),
        P(
            "La coincidencia que sí se puede señalar es de cobertura. El cuartil alto usa el percentil 75: "
            "13.8 muertes por 1,000 o 9.2% de bajo peso, solo en municipios con al menos 100 nacimientos. "
            f"De ese cuartil, <b>20 no tienen muestra</b>, <b>12 tienen una excedencia</b> y "
            f"{int((high.grupo == 'Monitoreado sin excedencia').sum())} están monitoreados sin rebasar la NOM. "
            f"Los 12 con excedencia son: {twelve}."
        ),
        P("Qué hace el libro Tableau", "h2"),
        P(
            "Un solo tablero, «Cobertura y salud». La vista principal son los 106 municipios en barras horizontales, "
            "ordenados por mortalidad dentro de cada grupo y coloreados por grupo: ámbar con evidencia, verde monitoreado "
            "sin excedencia y gris sin monitoreo. La longitud de la barra es la mortalidad infantil. Al lado, las dos medianas "
            "(el resultado nulo, con el eje desde cero en este respaldo) y los municipios con excedencia por parámetro. "
            "Abajo, la lista de acción: el cuartil alto sin muestra. La única interacción es el parámetro <b>Grupo de monitoreo</b>. "
            "Con «Todos los grupos» se ve el estado completo; al elegir un grupo se recortan las cinco vistas. "
            "No hay mapa: las medianas no sostienen un gradiente geográfico."
        ),
        P(
            "Sirve a quien decide el siguiente muestreo. No dice que el agua explique las muertes infantiles. "
            "Dice dónde falta una muestra en municipios que ya están en el cuartil alto, y dónde la muestra que existe ya rebasó un límite de la NOM-127."
        ),
        CondPageBreak(120 * mm),
        P("Dónde falta la muestra: cuartil alto sin monitoreo", "h2"),
        P("Entran por mortalidad infantil, por bajo peso, o por las dos. Es una lista de cobertura, no un ranking de causa. Nacimientos INEGI 2018-2022.", "small"),
    ]
    gap_rows = [["Municipio", "Marginación", "Muertes / 1,000", "Bajo peso %", "Nacimientos"]]
    for row in gap.itertuples():
        gap_rows.append([row.municipio, row.gm_2020, f"{row.imr:.1f}", f"{row.bajo_peso_pct:.1f}", f"{int(row.nacimientos_inegi):,}"])
    gap_table = Table(gap_rows, colWidths=[width * x for x in (0.28, 0.16, 0.20, 0.18, 0.18)])
    gap_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Arial"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, PALE]),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.2, LINE),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
    ]))
    story.append(gap_table)
    story.append(P("Excedencias de la NOM-127 en la ventana 2018-2023", "h2"))
    story.append(P(
        f"Un municipio cuenta si al menos una muestra de la ventana supera el límite. Cadmio, plomo y mercurio quedan en cero. "
        f"Coliformes por encima de 1,000 NMP/100 mL, aparte del límite de la norma: {severe}.",
        "small",
    ))
    param_rows = [["Parámetro", "Límite", "Unidad", "Municipios", "% muestras con resultado"]]
    for row in params.itertuples():
        limit = f"{row.limite:.3f}".rstrip("0").rstrip(".")
        param_rows.append([row.nombre, limit, row.unidad, str(int(row.municipios_con_excedencia)), f"{row.pct_muestras_con_resultado:.1f}"])
    param_table = Table(param_rows, colWidths=[width * x for x in (0.28, 0.14, 0.18, 0.16, 0.24)])
    param_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Arial-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Arial"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, PALE]),
        ("GRID", (0, 0), (-1, -1), 0.2, LINE),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
    ]))
    story.append(param_table)
    story.append(P("Fuentes, unidades, periodos y límites", "h2"))
    story.append(P(
        "Agua: RENAMECA subterráneo, data/Subterraneo.xlsb, ventana 2018-2023, 121 sitios (113 pozos y 8 cenotes) y 366 muestras. "
        "Marginación: CONAPO 2020. Mortalidad infantil: defunciones de menores de un año en los microdatos de la DGIS, "
        "estadística vital de INEGI, residencia habitual, entre nacimientos registrados de INEGI, residencia de la madre, por 1,000, años 2018-2022. "
        "El microdato de nacimientos 2023 no abrió, así que 2023 no entra ni en las muertes ni en los nacimientos y no se rellena con el CSV de muertes fetales. "
        "Bajo peso: porcentaje de nacidos vivos con menos de 2,500 g en SINAC 2018-2023, municipio de residencia de la madre. "
        "Unidades: muertes por 1,000 nacimientos; porcentaje de bajo peso; límites de la NOM-127-SSA1-2021 en mg/L o NMP/100 mL.",
        "small",
    ))
    story.append(P(
        "Límites. Mérida concentra 82 de 366 muestras (22.4%). Hay parámetros con muchos blancos o valores bajo detección. "
        "La NOM-127 es de agua para uso y consumo humano y aquí se aplica a pozos y cenotes. La comparación es ecológica. "
        "El municipio de Quintana Roo tiene 75 nacimientos y queda fuera de la mediana y del cuartil. "
        "Al quitar 2020 y 2021 el orden cambia: 10.58 con evidencia, 9.45 monitoreado sin excedencia y 10.26 sin monitoreo, por 1,000. "
        "Dureza y sólidos disueltos se reportan aparte y no definen el grupo. No hay una asociación geográfica que las medianas sostengan. Es una descripción, no una causa.",
        "small",
    ))
    story.append(P(
        "Verificación. Dentro del .twbx: Data/municipios_yucatan_2018_2023.csv (la tabla municipal, sin modificar), "
        "Data/resumen_grupos.csv (las medianas publicadas) y Data/excedencias_por_grupo.csv (la suma de las banderas de excedencia, por grupo y parámetro). "
        "La misma tabla municipal está en data/processed/municipios_yucatan_2018_2023.csv. "
        "Tableau Desktop no está instalado en la computadora donde se armó el paquete: el libro es XML de Tableau 18.1 con conexiones de texto. "
        "Un asistente de IA en Cursor preparó el XML y este PDF a partir de esos CSV ya calculados para el evidence board. No se usaron microdatos de data/raw.",
        "small",
    ))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFillColor(TEAL)
        canvas.rect(0, letter[1] - 7 * mm, letter[0], 7 * mm, fill=1, stroke=0)
        canvas.setFillColor(MUTED)
        canvas.setFont("Arial", 7)
        canvas.drawString(13 * mm, 6 * mm, "K'IIN DATA  ·  Datostada MX 2026  ·  Dashboard, respaldo en PDF")
        canvas.drawRightString(letter[0] - 13 * mm, 6 * mm, f"{document.page} / 2")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def write_fuentes() -> None:
    (OUT / "Dashboard_fuentes.txt").write_text(
        "\n".join([
            "K'IIN DATA — Datostada MX 2026 — Dashboard",
            "Nota de verificación. No sustituye el libro Tableau ni el PDF.",
            "",
            "Archivos del entregable",
            "- documents/Dashboard_KIIN_Data.twbx",
            "- documents/Dashboard_KIIN_Data.pdf",
            "",
            "Dentro del .twbx",
            "- Dashboard_KIIN_Data.twb",
            "- Data/municipios_yucatan_2018_2023.csv",
            "  Copia exacta de data/processed/municipios_yucatan_2018_2023.csv (106 municipios).",
            "- Data/resumen_grupos.csv",
            "  Medianas publicadas: 10.18, 10.88 y 10.85 por 1,000; bajo peso 7.72%, 8.9% y 7.73%.",
            "  A un decimal, el hallazgo: 10.2, 10.9 y 10.8; 7.7%, 8.9% y 7.7%.",
            "- Data/excedencias_por_grupo.csv",
            "  Suma de las banderas de la tabla municipal, por grupo y parámetro.",
            "  Con los tres grupos: coliformes 29, nitratos 12, arsénico 7, cadmio 0, cromo 4, plomo 0, mercurio 0, fluoruros 6.",
            "",
            "Ruta para quien verifica fuera del libro",
            "- /Users/a/Desktop/Kiin_Data/data/processed/municipios_yucatan_2018_2023.csv",
            "- data/processed/resumen_grupos.csv",
            "- data/processed/resumen_grupos_sin_pandemia.csv",
            "- data/processed/excedencias_por_parametro.csv",
            "- data/processed/fuentes.csv",
            "",
            "Si Tableau pide la ruta de un texto, señalar el CSV del mismo nombre dentro de Data/ en el paquete,",
            "o la ruta de data/processed en la carpeta de trabajo.",
            "No se incluye data/raw.",
            "",
            "Interacción del libro: un parámetro, Grupo de monitoreo, aplicado a las cinco vistas.",
            "Tableau Desktop no estaba instalado. El .twbx se escribió como XML de Tableau 18.1.",
            "Herramienta: asistente de IA en Cursor, sobre los CSV ya calculados. El hallazgo no se recalculó.",
            "",
        ]),
        encoding="utf-8",
    )


def package(frame: pd.DataFrame, resumen: pd.DataFrame, long_exc: pd.DataFrame) -> None:
    staging = OUT / "_twbx_build"
    if staging.exists():
        shutil.rmtree(staging)
    data = staging / "Data"
    data.mkdir(parents=True)
    shutil.copy2(SRC, data / "municipios_yucatan_2018_2023.csv")
    shutil.copy2(RESUMEN, data / "resumen_grupos.csv")
    long_exc.to_csv(data / "excedencias_por_grupo.csv", index=False, encoding="utf-8")
    twb_text = build_twb().format(
        mun=datasource_xml(MUN, "Municipios", "municipios_yucatan_2018_2023.csv", frame),
        res=datasource_xml(RES, "Grupos", "resumen_grupos.csv", resumen),
        exc=datasource_xml(EXC, "Excedencias", "excedencias_por_grupo.csv", long_exc),
    )
    twb_path = staging / "Dashboard_KIIN_Data.twb"
    twb_path.write_text(twb_text, encoding="utf-8")
    twbx = OUT / "Dashboard_KIIN_Data.twbx"
    with zipfile.ZipFile(twbx, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(twb_path, "Dashboard_KIIN_Data.twb")
        for path in data.iterdir():
            archive.write(path, f"Data/{path.name}")
    loose = OUT / "Dashboard_KIIN_Data.twb"
    if loose.exists():
        loose.unlink()
    shutil.rmtree(staging)
    other = OUT / "_twbx_data"
    if other.exists():
        shutil.rmtree(other)


def verify() -> None:
    twbx = OUT / "Dashboard_KIIN_Data.twbx"
    with zipfile.ZipFile(twbx) as package:
        names = set(package.namelist())
        needed = {
            "Dashboard_KIIN_Data.twb",
            "Data/municipios_yucatan_2018_2023.csv",
            "Data/resumen_grupos.csv",
            "Data/excedencias_por_grupo.csv",
        }
        if not needed <= names:
            raise SystemExit(f"Faltan archivos en el twbx: {needed - names}")
        xml = package.read("Dashboard_KIIN_Data.twb").decode("utf-8")
        if package.read("Data/municipios_yucatan_2018_2023.csv") != SRC.read_bytes():
            raise SystemExit("El CSV municipal empaquetado no es el original.")
    from xml.etree import ElementTree as ET
    ET.fromstring(xml)
    for token in (
        "Con evidencia", "Monitoreado sin excedencia", "Sin monitoreo",
        "Grupo de monitoreo", "En grupo", "paramctrl", "Vista principal",
        "Excedencias por parámetro", "Sin monitoreo en el cuartil alto",
        "10.2", "10.9", "10.8", "22.4",
    ):
        if token not in xml:
            raise SystemExit(f"Falta en el twb: {token}")
    if xml.count("<filter ") < 5:
        raise SystemExit("El libro no trae un filtro por vista.")
    pdf = (OUT / "Dashboard_KIIN_Data.pdf").read_bytes()
    pages = pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")
    if pages != 2:
        raise SystemExit(f"El PDF tiene {pages} páginas, no 2.")
    print(f"twbx {twbx} ({twbx.stat().st_size} bytes)")
    print(f"pdf páginas {pages}")


def copy_official() -> None:
    if not OFFICIAL.is_dir():
        print("sin carpeta oficial")
        return
    try:
        _copy_official_files()
    except PermissionError as exc:
        print(f"copia oficial pendiente: {exc}")


def _copy_official_files() -> None:
    for name in (
        "Dashboard_KIIN_Data.twbx",
        "Dashboard_KIIN_Data.pdf",
        "Dashboard_fuentes.txt",
    ):
        shutil.copy2(OUT / name, OFFICIAL / name)
    for name in (
        "municipios_yucatan_2018_2023.csv",
        "resumen_grupos.csv",
        "resumen_grupos_sin_pandemia.csv",
        "excedencias_por_parametro.csv",
        "fuentes.csv",
    ):
        shutil.copy2(PROCESSED / name, OFFICIAL / name)
    loose = OFFICIAL / "Dashboard_KIIN_Data.twb"
    if loose.exists():
        loose.unlink()
    print(f"copia {OFFICIAL}")


def main() -> None:
    frame = pd.read_csv(SRC)
    resumen = pd.read_csv(RESUMEN)
    params = pd.read_csv(PARAMS)
    check_facts(frame, resumen)
    long_exc = long_exceedances(frame)
    package(frame, resumen, long_exc)
    build_pdf(OUT / "Dashboard_KIIN_Data.pdf", frame, resumen, params)
    write_fuentes()
    verify()
    copy_official()


if __name__ == "__main__":
    main()
