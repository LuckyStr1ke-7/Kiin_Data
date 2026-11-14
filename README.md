# K'IIN DATA

Datostada MX 2026 · Reto Yucatán Vivo · Universidad Politécnica de Yucatán.

La pregunta, cerrada en el data brief, es si en los municipios de Yucatán coinciden la contaminación del agua subterránea, la marginación y la vulnerabilidad materno-infantil. La respuesta que sostienen los datos no es una causa. Es un mapa de cobertura.

## La idea para contar

El agua que se bebe en gran parte de Yucatán sale del acuífero. Los pozos y los cenotes de la red de monitoreo dejan ver coliformes fecales, nitratos y metales, pero no miran todos los municipios por igual. La tentación del relato es decir que donde el agua rebasa la norma nacen más niños con bajo peso o mueren más menores de un año. Las medianas no dan esa pendiente.

Lo que sí se ve es un hueco. Hay municipios con mortalidad infantil o bajo peso en el cuartil alto del estado y sin una sola muestra subterránea entre 2018 y 2023. Chikindzonot, Tekom, Chichimilá, Kaua y Tixmehuac están en esa lista, con marginación alta. El monitoreo, en cambio, se concentra: Mérida reúne 22.4% de las muestras de la ventana. La historia útil para una autoridad de salud o de agua no es “el agua explica la mortalidad”. Es “estos pueblos ya muestran vulnerabilidad y nadie les ha medido el acuífero”.

Ese es el hilo del pitch de cinco minutos: pregunta, tres grupos, medianas que no se separan, lista de huecos, y el dashboard como herramienta para recorrer esa lista.

## Qué se compara

Una fila por cada uno de los 106 municipios. Tres grupos, solo con muestras de 2018 a 2023:

| Grupo | Municipios | Qué significa |
| --- | ---: | --- |
| Con evidencia | 36 | Al menos una muestra por encima de un límite general de la NOM-127-SSA1-2021 |
| Monitoreado sin excedencia | 27 | Hubo muestras y ninguna rebasó esos límites |
| Sin monitoreo | 43 | No hubo muestra subterránea en la ventana |

La norma se aplica con los límites generales, no con el cumplimiento gradual, porque la mayoría de los municipios tiene menos de 50,000 habitantes. Coliformes fecales cuentan desde 1.1 NMP/100 mL. Un valor censurado (`<1.1`, no detectable) no es excedencia. Nitratos como N: 11 mg/L. Arsénico 0.025, cadmio 0.005, cromo total 0.05, plomo 0.01, mercurio 0.006 y fluoruros 1.50 mg/L. Dureza y sólidos disueltos se reportan aparte y no definen el grupo. El corte de coliformes por encima de 1,000 NMP/100 mL es un subconjunto severo, no la definición del grupo.

La mortalidad infantil es defunciones de menores de un año por 1,000 nacimientos registrados, municipio de residencia habitual, 2018–2022. El microdato de nacimientos de INEGI para 2023 no abrió, así que ese año no entra ni en las defunciones ni en los nacimientos. El bajo peso es el porcentaje de nacidos vivos con menos de 2,500 g en SINAC, 2018–2023, municipio de residencia de la madre. La marginación es el índice y el grado municipal de CONAPO 2020.

La comparación usa la mediana de los municipios con al menos 100 nacimientos de INEGI. La vulnerabilidad alta es el cuartil superior de esa mortalidad (13.8 por 1,000) o de ese bajo peso (9.2%).

## Hallazgo

Entre los municipios estables, la mediana de mortalidad infantil es 10.2 por 1,000 con evidencia, 10.9 con monitoreo sin excedencia y 10.8 sin monitoreo. La de bajo peso es 7.7%, 8.9% y 7.7%. Los tres grupos no se separan. El grupo con evidencia no tiene la peor mediana.

La coincidencia que sí se puede señalar es de cobertura: 20 municipios del cuartil alto no tienen monitoreo subterráneo en la ventana, y 12 de ese mismo cuartil sí tienen una excedencia. Al quitar 2020 y 2021 cambia el orden de las medianas de mortalidad infantil, así que el empate no es una constante inmune a la pandemia. El detalle está en `data/processed/resumen_grupos.csv` y `data/processed/resumen_grupos_sin_pandemia.csv`.

## Cómo se reconstruyó el Evidence Board

El tablero anterior, `documents/Evidence Board K'IIN Data.pdf`, se conserva como antecedente y no es el entregable. Comparaba muertes fetales de 2012 con razones de 2025, estaba en inglés y sus propias tasas no se separaban (1.74% contra 1.77%). El archivo de muertes fetales de 2025 no entra en esta reconstrucción: está fuera del periodo y no es el resultado del brief.

El entregable es `documents/Evidence_Board_KIIN_Data.pdf`, tres páginas en español. El script `scripts/evidence_board.py` hace la lectura, la limpieza de nombres municipales, las banderas de excedencia, la unión y la sensibilidad. Los microdatos nacionales se descargan a `data/raw/`, que no se versiona. La verificación queda en:

- `data/processed/municipios_yucatan_2018_2023.csv`, 106 filas
- `data/processed/excedencias_por_parametro.csv`
- `data/processed/fuentes.csv`, con la URL y la fecha de cada fuente

Agua: `data/Subterraneo.xlsb`, hojas SITIOS y RESULTADOS, recorte a Yucatán. Son 121 sitios (113 pozos y 8 cenotes) y 366 muestras en 2018–2023. No se usa `TODOS LOS MONITOREOS.xlsb`. Defunciones: microdatos abiertos de la DGIS, que publican la estadística vital de INEGI. Nacimientos del denominador: INEGI. Bajo peso: SINAC. Marginación: índice municipal CONAPO 2020.

## Dashboard

`documents/Dashboard_KIIN_Data.twbx` es el libro empaquetado, con los CSV adentro. La vista principal son los 106 municipios, coloreados por grupo, según la mortalidad infantil. Al lado están las medianas de los tres grupos, el bajo peso y la lista de huecos. El filtro es el grupo de monitoreo. `documents/Dashboard_KIIN_Data.pdf` es el respaldo, y `documents/Dashboard_fuentes.txt` anota rutas y unidades.

Tableau Desktop no está en la máquina donde se armó el XML del libro. Antes de la presentación hay que abrirlo en Tableau y confirmar que el filtro responde.

## Pitch

El diseño del relato de cinco minutos está en `documents/Pitch_KIIN_Data.md`. Las láminas de apoyo están en `documents/Pitch_KIIN_Data.pdf`.

## Límites que el relato no puede saltar

La unidad es el municipio: una excedencia en un pozo no describe el agua de cada hogar, y una tasa municipal no describe un riesgo individual. La NOM-127 es de agua para uso y consumo humano; aquí se aplica a pozos y cenotes de la red de monitoreo, no a tomas domiciliarias. El muestreo es irregular. Varios parámetros tienen muchos vacíos, así que “sin excedencia” puede ser ausencia de medición de ese parámetro. Los municipios con pocos nacimientos tienen tasas inestables. Marginación, servicios y la pandemia se cruzan con la salud, y este corte no los separa. La relación que se describe es una asociación espacial, no una causa. RENAMECA no mide plaguicidas.

## Uso de IA

Cursor ayudó a localizar fuentes abiertas, escribir `scripts/evidence_board.py` y `scripts/build_dashboard.py`, redactar el Evidence Board, el respaldo del dashboard y este README, y diseñar el pitch. Las cifras salen de esos scripts y se revisan contra los CSV.
