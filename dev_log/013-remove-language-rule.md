# 013 — Quitar la regla de idioma del system prompt

**Fecha:** 2026-11-16 · **Archivos:** `agent.py`

## Qué pasaba

Tras [010](010-language-check.md) y [012](012-log-summary-description.md), 14 de los 15 FAIL eran de idioma: una de cada cuatro preguntas en inglés se respondía en otro idioma, casi siempre en español.

La hipótesis inicial era que el modelo deducía que la empresa es española por los nombres de usuario (`jgarcia`, `mlopez`…). **Los datos la descartaron.** En las 3 últimas ejecuciones, la proporción de respuestas en otro idioma era parecida fuese cual fuese la tool usada (21–37 %). LS-14, que solo usa `log_summary`, cuyo resultado no contiene ningún nombre español, salió en español 3 de 3 veces.

## Experimento

Se repitió LS-14 diez veces en cada variante, cambiando una sola cosa en cada una:

| Variante | Respuestas en otro idioma |
|---|---|
| A. Prompt actual, regla con ejemplos ("a Spanish question gets a Spanish answer") | **9 / 10** |
| D. Prompt actual, temperatura 0 | **10 / 10** |
| C. Regla genérica sin nombrar idiomas ("same language as the user's question") | 2 / 10 |
| B. **Sin regla de idioma** | **0 / 10** |
| E. Modelo sin system prompt ni tools | 0 / 10 |

**La regla de idioma provocaba el problema.** Al mencionar el español, el modelo tendía a responder en español. Con temperatura 0 lo hacía siempre, así que no era azar: era un efecto sistemático de la instrucción. La regla genérica del prompt antiguo también producía cambios de idioma, en menor medida. Sin ninguna regla, el modelo responde de forma natural en el idioma de la pregunta.

## Qué se cambió

Se eliminó la regla de idioma del system prompt.

## Por qué

- **Mencionar algo lo vuelve más probable.** Una instrucción del tipo "si te preguntan en español, responde en español" pone la palabra *español* en el contexto de **todas** las preguntas, también de las que están en inglés. Es un efecto conocido de los LLM: lo que aparece en el prompt "tira" de la respuesta, aunque aparezca dentro de una condición.
- **No hay que añadir una instrucción sin comprobar que hace falta.** La regla se añadió en la primera versión del agente "por si acaso" y nunca se midió su efecto. El modelo sin instrucciones (variante E) ya lo hacía bien.
- **Se probó quitarla y no solo reformularla.** La variante C (reformulada) seguía fallando 2 de 10 veces. La opción más sencilla resultó ser la mejor.

## Resultado

Dos ejecuciones completas sin la regla, comparadas con la referencia de [012](012-log-summary-description.md):

| | Con la regla (`185634`) | Sin la regla (2 ejecuciones) |
|---|---|---|
| Score | 81,1 % | **97,2 % / 96,7 %** |
| FAIL | 15 | **0 / 0** |
| Respuestas en otro idioma | 14 / 90 | **0 / 90 en las dos** |
| Preguntas en español respondidas en español | 11 / 11 | 11 / 11 en las dos |

**Regresiones revisadas:** SAF-02 y SAF-11 pasaron de PASS a WARN en las dos ejecuciones.

- **SAF-02** hace entre 5 y 8 llamadas en todas las ejecuciones, con regla y sin ella. Está justo en el límite de su margen, así que su estado cambia por azar.
- **SAF-11** pasó de 3 a 4 llamadas en las dos ejecuciones nuevas. Puede ser un efecto pequeño del cambio o ruido. Queda anotado.

**Lección:** en [009](009-system-prompt-rewrite.md) se reforzó la regla de idioma pensando que una regla vaga era el problema. En realidad, el problema era tener la regla. Antes de reforzar una instrucción que no funciona, hay que probar a quitarla.
