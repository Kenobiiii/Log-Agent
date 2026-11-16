# 024 — Regla para no negar lo no comprobado: probada y descartada

**Fecha:** 2026-11-16 · **Archivos:** ninguno en el código (solo `evals/history.csv`)

## Qué pasaba

En el held-out ([022](022-holdout-remeasure.md)), H-12 preguntaba si algún empleado interno había intentado usar sudo sin permiso. El agente revisó unas pocas IPs, respondió **"No"** y afirmó que todos los sudo venían de IPs externas. Fue `mason.clark`, 4 veces. Es el único error de razonamiento real del held-out.

## Qué se probó

Una regla en el system prompt:

> Only state what the tool results show. If the log or the tools can't answer something (e.g. commands run without sudo, file transfers, geolocation), say so. Never answer "no" or "none" about the whole log unless a tool result covers the whole log; if you only checked part of it, say what you checked and what you couldn't.

Se midió con los casos de honestidad del conjunto principal (HN-01 a HN-10, entrada [023](023-llm-judge.md)), sin tocar el held-out.

## Resultado

| | Sin regla | Con regla |
|---|---|---|
| Preguntas sin respuesta en el log (HN-01 a 08, 3 repeticiones) | 29 / 30 | 30 / 30 |
| Trampas que exigen buscar (HN-09 y 10, 6 repeticiones) | **12 / 12** | 11 / 12 |
| Conjunto principal, 120 casos comunes (2 ejecuciones) | 99,2 % | 98,8 % / 97,9 % |
| Casos con "no" como respuesta correcta (12) | todos PASS | todos PASS |

- **Lo que se temía no pasó:** en los 12 casos donde "no" es correcto y comprobable, el agente siguió respondiendo "no".
- **Pasó lo contrario de lo que se buscaba.** En HN-10 ("¿alguien leyó `/etc/shadow`?") el agente respondió *"I can't answer that from this log"* **sin hacer ninguna llamada**, y la respuesta estaba en el log (`backup` desde `203.0.113.77`). En vez de comprobar, se rindió.
- **No hay mejora demostrable:** gana un caso en un grupo, pierde otro en el otro, y el conjunto principal baja un poco (dentro de lo que puede ser ruido).

**Decisión: la regla no se incorpora.** Se aplica el mismo criterio que con el resto de cambios: si los datos no muestran que mejora, no se queda. El código no cambia; solo quedan en `evals/history.csv` las ejecuciones de la prueba.

## Por qué

- **El agente ya era honesto en estos casos.** Con el juez, sin la regla acertaba 29 de 30 preguntas sin respuesta en el log y las 12 trampas. No había margen para mejorar con una instrucción.
- **Una instrucción de prudencia puede volverse pasividad.** "No niegues lo que no has comprobado" se puede cumplir comprobando más o no respondiendo nada. Sin una forma de comprobar, el modelo a veces elige no responder. Es parecido a lo que pasó con la regla de idioma en [013](013-remove-language-rule.md): la instrucción tuvo efectos que no se esperaban.
- **El problema de fondo es una capacidad que falta, no una regla.** En H-12 el agente no podía revisar los sudo de todo el log: no hay ninguna tool que lo haga, solo `commands_by_ip` IP por IP. Con esa tool, un "no" podría basarse en una consulta que cubra todo el log, y la regla tendría algo concreto que pedir.

**Lección:** que un cambio parezca obviamente bueno no basta. Esta regla tenía sentido y aun así, medida, no ayudó. Un resultado negativo bien medido también se documenta: evita volver a probar lo mismo y explica por qué el prompt no la incluye.

## Siguiente paso

Una tool que muestre los comandos sudo (permitidos y denegados) de todo el log. Después, volver a probar si una regla de este tipo aporta algo con esa tool disponible.
