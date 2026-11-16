# 007 — `top_failed_ips` agrupa las IPs por subred

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`

## Qué pasaba

En la baseline, el caso **TF-06** dio FAIL. La pregunta es cuántas IPs `194.26.29.x` hay en el top 30. El agente llamó bien a `top_failed_ips(n=30)` y recibió la lista completa, pero contó **24** en lugar de **25**.

Los LLM cuentan mal los elementos de una lista larga. Ya había pasado en la primera prueba del agente, cuando dijo "7 IPs" de esa subred y eran 25.

## Qué se cambió

`top_failed_ips` devuelve un campo nuevo, `subnets_in_top`, que agrupa por subred `/24` las IPs devueltas (solo las subredes con 2 o más IPs):

```json
"subnets_in_top": [{"subnet": "194.26.29.0/24", "ips": 25, "failures": 430}]
```

La descripción de la tool lo explica y añade: *"use those counts instead of counting IPs yourself"*.

## Por qué

- **Los recuentos los hace Python, no el modelo.** Es la misma idea con la que se diseñaron las tools: el LLM interpreta y Python calcula.
- **Se descartó la propuesta del diagnóstico** de añadir al prompt una regla del tipo "verifica tus sumas". Pedirle al modelo que cuente con más cuidado no lo hace fiable. Darle el número ya calculado, sí.
- **Además aporta información de seguridad.** Una subred con 25 IPs que atacan a la vez es un ataque distribuido, y ahora el agente lo ve directamente.

## Resultado

**TF-06, 5 ejecuciones por versión:**

| Versión | PASS | Llamadas |
|---|---|---|
| Sin `subnets_in_top` | 4 / 5 (1 FAIL) | 1–2 |
| Con `subnets_in_top` | 5 / 5 | 1 siempre |

**Los 15 casos de la tool contra la baseline** salieron **peor**: 80 % → 70 %, con 5 regresiones. Antes de aceptar el cambio se investigó si las causaba el campo nuevo:

- **TF-01, 02, 07 y 14** pasaron de PASS a WARN por hacer más llamadas. En una prueba A/B (3 ejecuciones por caso y versión), la versión antigua tenía el mismo problema: TF-07 da WARN 3 de 3 en las dos versiones. Es el exceso de investigación del system prompt, que varía mucho de una ejecución a otra.
- **TF-03** pasó a FAIL. Con 6 ejecuciones por versión, **la antigua falla más** (3 / 6) que la nueva (0 / 6). No era el cambio.

**Conclusión:** el cambio arregla TF-06 y las regresiones eran ruido. **Lección:** una ejecución de cada caso no basta para decidir. Cuando aparece una regresión, hay que repetir los casos afectados con las dos versiones antes de culpar al cambio.

## Hallazgos pendientes (no arreglados aquí)

1. **El agente cambia de idioma de vez en cuando.** Ante preguntas en inglés respondió en neerlandés y en vietnamita, con las dos versiones. Tiene que ver con la regla del system prompt "reply in the same language".
2. **El check de "no" de TF-03 es frágil.** Busca `"no "` con espacio, así que "**No.** All 10…" da FAIL aunque sea correcto.
