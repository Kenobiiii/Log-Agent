# 010 — Los evals comprueban el idioma de la respuesta

**Fecha:** 2026-11-16 · **Archivos:** `evals/run_evals.py`

## Qué pasaba

En [009](009-system-prompt-rewrite.md) se vio que el agente a veces responde en otro idioma, y que los evals no lo detectan: las IPs y las cifras se escriben igual en cualquier idioma, así que los checks pasaban. El recuento de 009 ("15 de 180 respuestas") se hizo buscando a mano algunas palabras de neerlandés y vietnamita y caracteres chinos o cirílicos. Era incompleto.

## Qué se cambió

`check_answer()` comprueba ahora que la respuesta esté en el idioma de la pregunta. Si no lo está, el caso da FAIL con `wrong language: answered in es, question is in en`.

La detección (`detect_language()`) no usa librerías externas:

1. Quita el código entre comillas invertidas (IPs, usernames, comandos), que no indica el idioma.
2. Escrituras no latinas (chino, cirílico, árabe, coreano…) → `non-latin`.
3. Caracteres típicos del vietnamita → `vi`.
4. Para el resto, cuenta palabras muy frecuentes de cada idioma ("the", "and", "el", "los", "het", "geen", "não"…) y elige el idioma con más apariciones. Si hay menos de 3, devuelve `unknown` y no se penaliza.

Los casos solo están en inglés o en español, así que el idioma esperado es español si se detecta español en la pregunta y, si no, inglés. Así las preguntas cortas como "Which usernames did 185.220.101.47 try?" también se comprueban.

## Por qué

- **Una respuesta en el idioma equivocado es una respuesta incorrecta para el usuario**, aunque los datos sean correctos. Por eso cuenta como FAIL y no como WARN.
- **Sin dependencias nuevas.** Para distinguir unos pocos idiomas basta con contar palabras frecuentes. Una librería de detección sería más precisa, pero esta precisión es suficiente para el caso.
- **Se validó con las 360 respuestas guardadas** de las cuatro últimas ejecuciones, antes de confiar en el check.

## Resultado

**El problema era mucho mayor de lo que se pensaba:**

| Ejecución | Respuestas en otro idioma | Detalle |
|---|---|---|
| Prompt antiguo, 1 | 36 / 90 | 27 en español, 7 en chino/ruso, 2 en otros |
| Prompt antiguo, 2 | 32 / 90 | 22 en español, 7 en chino/ruso, 3 en otros |
| Prompt nuevo, 1 | 21 / 90 | 20 en español, 1 en ruso |
| Prompt nuevo, 2 | 24 / 90 | 24 en español |

Se revisaron a mano las respuestas marcadas y una muestra de las aceptadas como inglés; la detección es correcta. Algunas respuestas mezclan idiomas, por ejemplo un título en inglés con una tabla en español; se clasifican por el idioma que predomina.

**Puntuación real**, recalculando las mismas respuestas con el check de idioma:

| | Antes del check | Con el check |
|---|---|---|
| Prompt antiguo (media) | 79,7 % | **52,0 %** |
| Prompt nuevo (media) | 94,7 % | **72,0 %** |

El prompt nuevo sigue mejorando unos 20 puntos, pero **el idioma es ahora el mayor problema del agente**: una de cada cuatro preguntas en inglés recibe respuesta en español.

**Lección:** un eval solo detecta lo que comprueba. Los checks miraban si estaban los datos, no si la respuesta servía al usuario. Antes de concluir que algo funciona, hay que preguntarse qué fallos podrían estar pasando sin que ningún check los vea.
