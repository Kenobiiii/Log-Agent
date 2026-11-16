# 020 — Nueva tool `external_logins`: logins desde fuera, con o sin fallos previos

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`, `agent.py`, `tests/test_tools.py`, `evals/run_evals.py`, `evals/holdout_cases.py`, `README.md`

## Qué pasaba

En el held-out ([017](017-holdout-suite.md)), **la clave SSH robada de jenkins pasaba desapercibida en las 4 preguntas sobre compromisos** (H-04, 05, 08 y 23). El atacante entró desde `198.51.100.77` sin un solo intento fallido, y las tools solo encontraban compromisos a través de fallos:

- `success_after_failures` necesita al menos un fallo antes del éxito;
- `top_failed_ips` ordena por número de fallos;
- `user_activity` sí lo mostraba, pero solo si se preguntaba por `jenkins` en concreto.

No había ninguna forma de preguntar "¿quién ha entrado desde fuera?".

## Qué se cambió

**1. Tool nueva `external_logins()`.** Lista todos los logins exitosos desde IPs externas, agrupados por IP y usuario: número de logins, métodos, primer y último login, fallos desde esa IP antes del primer login y **cuántas veces ha entrado ese usuario desde IPs internas**. Ese último campo es la señal de una clave robada: una cuenta que siempre entra desde dentro y de repente aparece desde fuera.

**2. System prompt.** El procedimiento para peticiones amplias ("¿nos han comprometido?") usa `external_logins` en lugar de `success_after_failures`, que encuentra lo mismo y además los compromisos sin fallos. También se quitó `successful_logins_by_ip` del paso de impacto: `external_logins` ya da esos datos, y en [011](011-review-optimal-calls.md) se vio que era una llamada redundante.

**3. Evals:**

- 15 casos nuevos (EL-01 a EL-15, 120 en total), incluidos varios cuya respuesta correcta es "no". En el log de ejemplo todos los logins externos tuvieron fallos previos, así que a "¿hubo algún login externo sin fallos?" el agente debe responder que no.
- CMD-03, SAF-10 y SAF-11 aceptan `external_logins` como camino válido.
- **Held-out:** H-04, 05, 08, 23 y 25 aceptan `external_logins` entre las tools esperadas. **Solo cambia el camino aceptado; las respuestas esperadas no se han tocado.** La tool no existía cuando se escribieron, y sin este cambio el caso daría WARN por no usar una tool que no estaba en la lista.
- UA-04 acepta "there is no" como forma de decir que la cuenta no existe. Es la cuarta vez que un check de texto rechaza una respuesta correcta ([003](003-fix-ub-09-invalid-ip.md), [008](008-fix-no-check.md)).

**4. Tests:** 3 nuevos, entre ellos uno con el patrón exacto de una clave robada (una cuenta que entra siempre desde dentro y luego desde fuera, sin fallos) que comprueba que `success_after_failures` no lo ve y `external_logins` sí. También se hicieron independientes del año dos tests que fallarían en 2027, porque syslog no incluye el año y el parser usa el actual; se comprobó simulando que estamos en 2027.

## Por qué

- **Buscar compromisos a través de fallos deja un hueco.** Un atacante con credenciales válidas (una clave robada, una contraseña filtrada) no falla. Hace falta una forma de verlo que no dependa de los fallos.
- **El contexto del usuario es lo que delata el ataque.** Un login externo puede ser legítimo (un empleado de viaje). Lo sospechoso es una cuenta de servicio que siempre entra desde el servidor de CI y de repente lo hace desde internet. Por eso la tool incluye los logins internos del mismo usuario.
- **Revisar los casos del held-out solo en el camino aceptado.** Cambiar lo que se espera de las respuestas después de ver los resultados sería hacer trampa. Aceptar una tool que no existía cuando se escribió el caso es mantenimiento.

## Resultado

**Tests:** 95 de 95.

**`external_logins` contra la verdad del held-out**, sin ejecutar el agente: devuelve exactamente los 5 pares IP/usuario de la verdad, incluida la clave robada de `jenkins` (0 fallos previos y 21 logins desde dentro). `success_after_failures` no la encuentra ni con el umbral mínimo.

**Conjunto principal**, dos ejecuciones completas con 120 casos: **98,3 % y 97,1 %**, con 0 y 1 FAIL. Regresiones revisadas:

| Caso | Causa | Decisión |
|---|---|---|
| SAF-10 | Ahora se resuelve en 1 llamada con `external_logins`; el caso exigía `success_after_failures` | Caso actualizado |
| SAF-11 | El agente llama a `success_after_failures` **y** a `external_logins`, que se solapan: 4–5 llamadas en lugar de 3 | **Coste real** de tener dos tools que se solapan. Pequeño; queda anotado |
| UB-15 | Una llamada de más, sin usar la tool nueva. Ya pasaba antes | Ruido |
| UA-04 | Check de texto frágil | Check arreglado |
| SAF-08 | Dice "10 fallos" (contra la cuenta `backup`) y el caso espera 16 (todos los fallos de esa IP). La pregunta admite las dos lecturas; no usó la tool nueva | Ambigüedad del caso que ya existía; pendiente |
