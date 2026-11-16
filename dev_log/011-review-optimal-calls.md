# 011 — Revisión de `optimal_calls` en los casos con WARN

**Fecha:** 2026-11-16 · **Archivos:** `evals/run_evals.py`

## Qué pasaba

Con el prompt nuevo ([009](009-system-prompt-rewrite.md)) quedaban 9 casos con WARN por llamadas de más. El diagnóstico atribuía varios al propio caso (`eval_case`). Si un caso exige menos llamadas de las razonables, castiga al agente por hacer bien su trabajo.

## Qué se cambió

Se revisó cada caso preguntando: ¿qué haría un analista razonable con esta pregunta?

| Caso | Cambio | Motivo |
|---|---|---|
| UB-12 | Ya no exige `users_by_ip`; óptimo 2 → 1 | El agente lo resolvió en **1** llamada con `users_tried_before_success` ([006](006-rename-users-tried.md)). Su camino era mejor que el esperado |
| CMD-03 | Óptimo 3 → 5 | Es una petición amplia ("full incident response") y el agente sigue el procedimiento que le marca el prompt para esos casos |
| SAF-02 | Óptimo 1 → 3 | Distinguir intrusiones reales de errores de tecleo justifica confirmar las 2 IPs externas |
| SAF-13 | Óptimo 1 → 2 | "Explain how you know" justifica `users_by_ip` para mostrar la prueba: 2 intentos por usuario |

**Se mantienen**, porque las llamadas de más son fallos del agente:

- **SAF-08:** `success_after_failures` ya da la IP y el número de fallos. El agente añade `commands_by_ip`, que no se pedía.
- **CMD-04, CMD-10 y CMD-15:** llama a `commands_by_ip` también con IPs internas, o repite con `successful_logins_by_ip` datos que ya tiene.
- **SAF-07:** se mantiene, y revela un problema nuevo (ver abajo).

## Por qué

- **Un eval demasiado estricto enseña al agente a hacer peor su trabajo.** Si UB-12 sigue exigiendo `users_by_ip`, un cambio que hiciera al agente usarla "para cumplir" puntuaría mejor, aunque el resultado empeorara.
- **Pero tampoco hay que aflojar por aflojar.** Cada cambio se justifica por lo que pide la pregunta. Donde el agente hace llamadas que nadie pidió, el WARN se queda: es un fallo real.
- **Se recalcularon las respuestas guardadas** para ver el efecto antes de dar el cambio por bueno.

## Resultado

Mismas respuestas, puntuadas con los casos nuevos:

| Ejecución (prompt nuevo) | Antes | Después |
|---|---|---|
| Ejecución 1 | 73,3 % | 74,4 % |
| Ejecución 2 | 70,6 % | 71,7 % |

El efecto es pequeño, y eso es buena señal: **casi todo lo que queda por arreglar son fallos reales del agente**, sobre todo el idioma ([010](010-language-check.md)).

**Hallazgo nuevo, una tool que falta:** en SAF-07 ("investiga si la cuenta de mlopez fue comprometida") el agente llamó a `users_by_ip("mlopez")` y a `users_by_ip("0.0.0.0")`, es decir, **pasó un nombre de usuario como IP**. Ninguna tool busca por usuario, así que el modelo improvisa. Una tool `logins_by_user(user)` resolvería ese tipo de pregunta.
