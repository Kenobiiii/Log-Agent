# 012 — Descripción de `log_summary`: nombre del ranking y cuándo usarla

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`, `agent.py`, `README.md`

## Qué pasaba

Tras el prompt nuevo ([009](009-system-prompt-rewrite.md)), **LS-05** ("¿qué 5 usernames recibieron más intentos fallidos?") empezó a fallar de vez en cuando. Ese ranking es justo el que da `log_summary`, pero:

- El campo se llamaba `most_targeted_users`, y la descripción decía "most targeted users". El modelo no siempre lo relacionaba con "usernames with the most failed attempts". Cuando no lo hacía, concluía *"my tools don't offer a direct username ranking"* y sumaba a mano los datos de varias IPs, con resultados erróneos.
- La descripción de la tool terminaba con **"Call this first to get the big picture"**, lo contrario de lo que dice el prompt nuevo ("not as a routine first step"). El agente recibía dos instrucciones contradictorias.

## Qué se cambió

- El campo `most_targeted_users` pasa a llamarse **`top_usernames_by_failures`**.
- La descripción de `log_summary` dice qué contiene ("the top 5 usernames by failed attempts") y **cuándo** usarla ("for questions about totals or about which usernames/accounts are attacked the most"), en lugar de "call this first".
- El system prompt y el README usan el mismo nombre.

## Por qué

- **Es el mismo principio que en [006](006-rename-users-tried.md):** el modelo solo ve nombres y descripciones, así que tienen que decir exactamente qué contiene cada campo.
- **Las descripciones de las tools también son instrucciones.** Cuando se cambia el system prompt, hay que revisar que las descripciones no digan lo contrario. "Call this first" venía de la primera versión del agente y nadie lo había vuelto a mirar.

## Resultado

LS-05, 10 ejecuciones por versión (contando solo el contenido, sin el idioma):

| Versión | Correcto | Primera llamada a `log_summary` | Llamadas de media |
|---|---|---|---|
| Antes | 7 / 10 | 7 / 10 | 1,7 |
| Después | **10 / 10** | **10 / 10** | **1,0** |

**Ejecución completa con todos los pendientes cerrados** (`20261116-185634`): **81,1 %** (71 PASS, 4 WARN, 15 FAIL). Es la primera ejecución con los evals actuales, así que es la nueva referencia:

- **14 de los 15 FAIL son de idioma** ([010](010-language-check.md)). Es el problema más grande que queda.
- **El otro FAIL (CMD-13) confirma que falta una tool:** el agente responde *"tools are indexed by IP, not by username"*. Es la misma carencia que apareció en SAF-07 ([011](011-review-optimal-calls.md)).
