# 018 — El parser entiende IPv6, `message repeated`, `publickey` y `keyboard-interactive`

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`, `tests/test_parser.py`, `tests/test_tools.py`, `README.md`

## Qué pasaba

El held-out ([017](017-holdout-suite.md)) mostró que el parser solo entendía las líneas del log de ejemplo:

- **IPv6:** la regex de IP era `[\d.]+`, así que el mayor atacante (`2001:db8:4f3a:12::17`, 600 intentos) era invisible.
- **`message repeated N times: [ … ]`:** rsyslog agrupa así las líneas idénticas consecutivas. Cada una de estas líneas representa N intentos, y se perdían todos.
- **`Failed publickey`:** solo se contaban los fallos de contraseña.
- **`keyboard-interactive/pam`:** logins habituales con VPN o doble factor, ni fallidos ni aceptados.

Resultado: las tools daban **826 fallos de 1.447** y **347 logins de 425**, y el top 1 de atacantes salía mal.

## Qué se cambió

- **IP de origen:** acepta IPv4 e IPv6 (`[0-9A-Fa-f:.]+`) y después se valida con `ipaddress`, así que un nombre de host o `999.1.1.1` se descartan.
- **Métodos de autenticación:** las regex de intento fallido y aceptado reconocen `password`, `publickey` y `keyboard-interactive/pam`. El método se guarda en cada evento (antes, todos los fallos se marcaban como `password`).
- **`message repeated N times`:** se desempaqueta el mensaje interior y, si es un intento fallido, se cuenta N veces. Si el mensaje repetido no es un intento (por ejemplo, `Connection closed`), se ignora.
- **Subredes:** `subnets_in_top` agrupa las IPv6 por `/64` y las IPv4 por `/24`.
- **11 tests unitarios nuevos**, con líneas escritas a mano siguiendo el formato de sshd y rsyslog, no copiadas del held-out.

## Por qué

- **Cada formato es un caso real de sshd.** No se ha adaptado el parser a los datos concretos del held-out, sino a los formatos que escribe sshd. Los tests usan otras IPs, otros usuarios y otros números.
- **Validar la IP después de la regex.** Una regex que acepte IPv6 completa y nada más es muy compleja. Es más sencillo dejar pasar cualquier cosa con forma de IP y que la valide el módulo `ipaddress`.
- **El evento guarda el método real.** Antes, el método de un fallo se ponía siempre como `password`, y eso ocultaba los ataques con claves.

## Resultado

**Sin cambios en el log de ejemplo.** Una foto de la salida de las 7 tools, con todas las IPs y usuarios del log, salió **idéntica** antes y después del cambio. Es más fuerte y más barato que una ejecución de evals, porque las tools son deterministas. No se lanzaron evals: ni las descripciones ni los datos que recibe el agente sobre ese log han cambiado.

**Tests:** 74 de 74. Para comprobar que los nuevos sirven se rompió el parser a propósito dos veces: ignorando el número de repeticiones (fallan 2 tests) y quitando la validación de IP (falla 1 test).

**Las tools contra la verdad del held-out**, sin ejecutar el agente:

| | Antes | Ahora | Verdad |
|---|---|---|---|
| Intentos fallidos | 826 | **1.447** | 1.447 |
| Logins exitosos | 347 | **425** | 425 |
| IPs con fallos | 138 | **145** | 145 |
| IP con más fallos | `198.51.100.23` | **`2001:db8:4f3a:12::17`** | `2001:db8:4f3a:12::17` |
| Fallos `publickey` | 0 | **21** | 21 |
| Logins `keyboard-interactive` | 0 | **78** | 78 |

Todas las cifras coinciden. Solo queda mal la red interna: `192.168.1.50` sigue saliendo como externa. Es el siguiente arreglo.
