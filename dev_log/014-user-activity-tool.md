# 014 — Nueva tool `user_activity`: buscar por usuario

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`, `evals/run_evals.py`, `README.md`

## Qué pasaba

Todas las tools buscaban **por IP**, pero hay preguntas que empiezan **por un usuario**:

- **SAF-07** ("a mlopez le llegó una alerta de login extraño, investiga"): el agente llamó a `users_by_ip("mlopez")` y a `users_by_ip("0.0.0.0")`. Improvisaba pasando un nombre de usuario como si fuera una IP ([011](011-review-optimal-calls.md)).
- **CMD-13** ("¿qué hizo la cuenta svc-update?"): el agente se rindió con *"tools are indexed by IP, not by username"* ([012](012-log-summary-description.md)).

Cuando acertaba, era porque encontraba un camino indirecto (`success_after_failures` → IP → `commands_by_ip`), que solo funciona si el usuario aparece en esa lista.

## Qué se cambió

**1. Tool nueva `user_activity(user)`.** Devuelve todo lo relativo a un usuario:

- si existe (sshd registra "invalid user" para las cuentas que no existen) y, si se creó durante el log, cuándo;
- primera y última aparición;
- intentos fallidos, en total y por IP;
- las IPs desde las que entró: interna o externa, método, número de logins, primero y último;
- el número de logins desde IPs externas;
- el número de comandos sudo y cuántos se denegaron.

Los comandos en sí no se repiten aquí. La descripción de la tool indica que, para verlos, hay que llamar a `commands_by_ip` con las IPs desde las que entró.

**2. Errores que orientan al agente.** Si recibe un nombre de usuario donde espera una IP, la tool responde *"'mlopez' is not an IP address. To look up a username, use user_activity."* Si `user_activity` recibe una IP, sugiere `users_by_ip`.

**3. Evals:**

- 15 casos nuevos (UA-01 a UA-15) con preguntas que empiezan por un usuario, verificadas contra el log.
- SAF-07, CMD-13, UB-12 y CMD-02 aceptan `user_activity` como camino válido. CMD-13 baja su óptimo de 3 a 2 llamadas.
- UB-13 ("¿qué IP probó más veces la cuenta deploy?") pasa a esperar 1 llamada: con la tool nueva se resuelve directamente.

## Por qué

- **El nombre `user_activity` y no `logins_by_user`.** Devuelve más que logins (fallos, sudo, creación de la cuenta), y el nombre debe decir lo que hay dentro ([006](006-rename-users-tried.md), [012](012-log-summary-description.md)).
- **No duplicar `commands_by_ip`.** Dos tools que devuelven lo mismo obligan al modelo a elegir entre ellas sin motivo. Es mejor que se encadenen.
- **Los mensajes de error son instrucciones.** El modelo lee el error y corrige. Un error que dice qué tool usar arregla el fallo en el momento, sin tocar el prompt.
- **Revisar los casos cuando aparece un camino mejor.** Con la tool nueva, UB-13 se resuelve en 1 llamada en lugar de 4. Si el caso siguiera exigiendo el camino antiguo, penalizaría la mejora.

## Resultado

Dos ejecuciones completas, ya con 105 casos (contando la actualización de UB-13):

| | Antes (2 ejecuciones) | Con `user_activity` (2 ejecuciones) |
|---|---|---|
| Score, 90 casos comunes | 97,2 % / 96,7 % | 96,7 % / 98,3 % |
| Score, 105 casos | — | **97,6 % / 98,1 %** |
| FAIL | 0 / 0 | 0 / 0 |

Los casos que motivaron el cambio:

| Caso | Antes | Ahora |
|---|---|---|
| CMD-13 "¿qué hizo svc-update?" | 4–5 llamadas, camino indirecto | **2**: `user_activity` → `commands_by_ip` |
| SAF-07 "investiga la cuenta de mlopez" | `users_by_ip("mlopez")`, `users_by_ip("0.0.0.0")` | empieza con `user_activity("mlopez")` |
| UB-13 "¿qué IP probó más veces deploy?" | 4 llamadas | **1** |

Los 15 casos nuevos: **28 de 30 PASS**, con 1,4 llamadas de media.

**Hallazgo en los datos:** `user_activity` muestra que el password spray de `91.240.118.52` también probó las cuentas `jrey` y `psanchez` (2 intentos cada una, sin éxito). Antes no se veía sin consultar la IP.
