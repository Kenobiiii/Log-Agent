# 006 — Renombrar `users_tried` a `users_tried_before_success`

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`

## Qué pasaba

En la baseline, el caso **SAF-12** dio FAIL. Pregunta cuántos usuarios distintos probó cada IP **antes de entrar**.

- `success_after_failures` devolvió el dato correcto: `"users_tried": 6` para `203.0.113.77`.
- El agente llamó después a `users_by_ip`, que devuelve `"distinct_users": 7`, y usó **ese** número.
- Ese 7 incluye `svc-update`, la cuenta que el atacante usó **después** de entrar.

Para la otra IP sí usó el campo correcto. El modelo no tenía claro qué significaba cada campo: `users_tried` y `distinct_users` parecen lo mismo.

## Qué se cambió

- En `success_after_failures`, el campo `users_tried` pasa a llamarse **`users_tried_before_success`**.
- La descripción de la tool añade: *"Failures and usernames are counted only up to the first successful login of each IP."*

## Por qué

- **El diagnóstico proponía una regla en el system prompt:** "no sustituyas users_tried por distinct_users". Se descartó porque solo cubre el caso descrito: cada nueva confusión exigiría otra regla. Un nombre que se explica solo funciona en cualquier pregunta.
- **Los nombres de los campos son parte del prompt.** El modelo no ve el código, solo el JSON. Si un campo no dice lo que significa, el modelo lo adivina.
- **No se tocó `distinct_users` de `users_by_ip`.** Ese campo es correcto: cuenta todos los usuarios vistos desde la IP. El problema era que el otro campo no dejaba claro su límite temporal.

## Resultado

La primera ejecución de los 15 casos de la tool dio +6,6 puntos (SAF-12 pasó de FAIL a WARN). El informe avisó de que, con solo 2 casos cambiados, podía ser azar. Por eso se repitió SAF-12 cinco veces con cada versión:

| Versión | FAIL | Respuesta correcta |
|---|---|---|
| `users_tried` (antes) | 3 / 5 | 2 / 5 |
| `users_tried_before_success` (después) | 0 / 5 | 5 / 5 |

**La mejora es real.** En la versión antigua, además del 6, a veces faltaba también el 42: el modelo usaba los 60 usuarios totales de `users_by_ip` para la otra IP.

**Lo que no cambia:** SAF-12 sigue haciendo entre 1 y 10 llamadas según la ejecución. Ese exceso viene del system prompt, que obliga a investigar a fondo, y se arreglará aparte.
