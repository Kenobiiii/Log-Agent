# 008 — Fix: el check de "no" rechazaba respuestas correctas

**Fecha:** 2026-11-16 · **Archivos:** `evals/run_evals.py`

## Qué pasaba

Durante la investigación de [007](007-subnet-breakdown.md), el caso **TF-03** ("¿alguna de las 10 IPs con más fallos es interna?") dio FAIL con respuestas correctas como:

> **No.** All 10 top-failure IPs are external (`internal: false`).

El check buscaba `"no "`, con espacio detrás. "No." lleva punto, "**No** —" lleva los asteriscos de la negrita y "All 10 are external" ni siquiera dice "no".

## Qué se cambió

- El grupo `NO` acepta también "no" seguido de puntuación o de Markdown: `no.`, `no,`, `no!`, `no:`, `no*`, `no—`, `no –`.
- TF-03 acepta además `external` / `extern`, porque "todas son externas" es una respuesta correcta a esa pregunta.

## Por qué

- **Hay que arreglar la herramienta de medida antes de medir.** El siguiente paso es cambiar el system prompt. Si el check da FAIL al azar según cómo formatee el modelo su respuesta, esos fallos se confundirían con el efecto del prompt.
- **Se comprobó que el check sigue rechazando respuestas incorrectas**, como "Yes, 10.99.0.15 is internal". Aflojar un check sin comprobar esto lo convierte en un check que siempre pasa.
- **Es el segundo fallo de este tipo** (ver [003](003-fix-ub-09-invalid-ip.md)). Los checks por texto son baratos, pero frágiles con el lenguaje natural. Si siguen apareciendo, convendría que la puntuación de las respuestas de sí/no la hiciera un LLM.

## Resultado

Se probaron cuatro respuestas: las tres correctas pasan y la incorrecta falla. Con las 6 respuestas de la versión antigua de TF-03 guardadas en [007](007-subnet-breakdown.md), las dos en inglés que fallaban ("**No.** All 10…") ahora pasarían. La que está en vietnamita sigue fallando, y es correcto que falle: es el problema de idioma, que se aborda en el system prompt.
