# 009 — Reescritura del system prompt

**Fecha:** 2026-11-16 · **Archivos:** `agent.py`

## Qué pasaba

Con el prompt antiguo, el agente **investigaba de más**. Preguntas que se resuelven con 1 llamada acababan con 6, 9 o 13: unos 35 WARN de 90 casos. Además, a veces **respondía en otro idioma**.

Revisando el prompt, regla por regla:

| Regla antigua | Problema |
|---|---|
| "Start with log_summary if you don't have an overview yet" | Cada pregunta empieza con una conversación nueva, así que nunca hay "overview": lo llamaba **siempre** |
| "use success_after_failures… and investigate them with users_by_ip and successful_logins_by_ip" | Un procedimiento de investigación completa, aplicado a **cualquier** pregunta |
| "For **every** external IP that logged in, use commands_by_ip" | "every" lo convertía en obligatorio, incluso para "¿cuál es la IP con más fallos?" |
| *(no existía)* | Ninguna regla pedía responder solo lo que se pregunta ni prohibía repetir llamadas |
| "Reply in the same language the user writes in" | Demasiado vaga: respondió en chino, ruso, neerlandés y vietnamita a preguntas en inglés |

## Qué se cambió

El prompt nuevo separa **dos modos de trabajo**:

- **Preguntas concretas** (por defecto): responder exactamente lo que se pregunta con las mínimas llamadas, y ofrecer los siguientes pasos en una línea en vez de hacerlos.
- **Peticiones amplias** ("analiza el log", "¿nos han comprometido?", revisar un incidente): el procedimiento completo de antes, en pasos numerados.

Además:

- `log_summary` solo cuando hacen falta cifras globales, no como primer paso por rutina.
- No repetir una llamada con los mismos argumentos.
- Usar los recuentos que ya calculan las tools (`subnets_in_top`, `users_tried_before_success`) en lugar de contar a mano.
- Una regla de idioma explícita, con ejemplos: pregunta en inglés, respuesta en inglés; en español, en español; nunca en otro idioma.

## Por qué

- **Las instrucciones incondicionales se cumplen siempre.** "Start with…" y "For every…" eran buenas para un análisis completo, pero el modelo las aplicaba también a las preguntas simples. La solución no es quitarlas, sino decir **cuándo** aplican.
- **Ofrecer el siguiente paso en vez de darlo.** El usuario decide si quiere profundizar: se ahorran llamadas y respuestas largas que nadie pidió.
- **Las reglas vagas se interpretan de forma variable.** "The same language the user writes in" no bastaba; con ejemplos concretos y una prohibición explícita el modelo lo cumple mucho mejor.

## Resultado

Dos ejecuciones completas (90 casos) con cada prompt. Mismo código, mismas tools y mismos checks; solo cambia el prompt:

| | Prompt antiguo | Prompt nuevo | Cambio |
|---|---|---|---|
| Score (media de 2) | 79,7 % | **94,7 %** | +15 |
| PASS | 53 / 56 | 82 / 81 | +27 |
| WARN | 37 / 32 | 7 / 8 | −27 |
| FAIL | 0 / 2 | 1 / 1 | = |
| Llamadas por caso | 3,6 | **1,7** | −53 % |
| Tokens por caso | ~5.800 | ~4.150 | −28 % |
| Segundos por caso | 4,9 | 3,3 | −33 % |
| Respuestas en otro idioma | 7 / 8 | **1 / 0** | −94 % |

**Hallazgo importante: los cambios de idioma estaban ocultos.** Con el prompt antiguo, **15 de 180 respuestas** estaban en otro idioma, pero solo 2 dieron FAIL. Las demás pasaban porque las IPs y las cifras se escriben igual en cualquier idioma. Se detectaron al buscarlos a mano en las respuestas, no gracias a los evals.

**Regresión investigada: LS-05.** Ahora falla de vez en cuando: 2 de 7 ejecuciones (1 en cada ejecución completa, 0 en 5 repeticiones). Pregunta por los 5 usernames más atacados, que es justo el campo `most_targeted_users` de `log_summary`. Con el prompt antiguo lo obtenía por casualidad, porque siempre llamaba primero a `log_summary`. Ahora a veces no relaciona la pregunta con ese campo y suma a mano los datos de varias IPs, con resultados erróneos.

## Pendiente

1. **LS-05:** la descripción de `log_summary` dice "most targeted users", y debería decir explícitamente que es un ranking de usernames por intentos fallidos.
2. **Los evals no comprueban el idioma de la respuesta.** Hace falta un check que lo verifique en todos los casos.
3. **El diagnóstico propone revisar `optimal_calls`** en casos como SAF-02 y SAF-13, cuya pregunta pide explicar o distinguir y justifica más llamadas.
