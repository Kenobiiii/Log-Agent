# 028 — Segundo held-out: 74 % en un log nuevo, y un patrón de error claro

**Fecha:** 2026-11-17 · **Archivos:** `samples/generate_holdout2.py`, `samples/holdout2_auth.log`, `samples/holdout2_truth.json`, `evals/holdout2_cases.py`, `evals/run_evals.py`, `tests/test_eval_checks.py`

## Qué pasaba

El primer held-out ([017](017-holdout-suite.md)) guió los arreglos de 018 a 027, así que su 84 % ya no medía con justicia si el agente generaliza. Hacía falta otro examen que no se hubiera usado para nada.

## Qué se cambió

**1. Un tercer log** (`samples/holdout2_auth.log`), de otra empresa: el *bastion host* de un proveedor de hosting.

- Oficina en `10.50.0.0/16`, **VPN tipo Tailscale en `100.64.0.0/10`**, que no es RFC 1918, y un *jump host* IPv6 de administración.
- Situaciones nuevas:
  - root atacado por fuerza bruta y comprometido; como root no necesita sudo, solo se ven los cambios de cuentas que hace (crea la puerta trasera `support2`);
  - un ataque distribuido desde 30 IPs de **30 subredes /24 distintas**, que `subnets_in_top` no agrupa;
  - la cuenta `backup-svc`, que siempre entra con clave desde su servidor, usada con contraseña desde el ordenador de un empleado (tmorel) para volcar la base de datos;
  - un usuario con una sesión por VPN y otra desde una IP externa a la vez;
  - escalada con `su` a root, con éxito (ksato) y fallida (hmeyer). **El parser no lee las líneas de `su`.**
- **Se mantiene el formato clásico de fechas de syslog**, a propósito. Las versiones recientes de Debian y Ubuntu usan fechas ISO (`2026-12-15T08:00:01.123+01:00`). Con ellas el parser no leería nada, el resultado sería casi un 0 % y solo mediría eso. Queda como limitación conocida, para probarla con tests unitarios.

**2. 25 casos** (`evals/holdout2_cases.py`), con las respuestas esperadas sacadas de `holdout2_truth.json` y 3 evaluados por el juez. Se guardaron en un commit (`f2ec5f3`) **antes de ejecutar el agente**.

**3. Runner:** las suites se generalizan (`--suite holdout2`). En las suites held-out, las redes internas de la empresa se leen del archivo de verdad, como haría un administrador con `--internal-networks`.

## Resultado

**Las tools contra la verdad, sin el agente:** todas las cifras coinciden (fallos, logins, IPs, métodos, fallos contra root, cuenta creada, red interna de la VPN y login externo de root). No se ven, como estaba previsto, los `su` ni la agrupación del ataque distribuido.

**El agente, en una única ejecución:** el informe dice **78 %** (18 PASS, 3 WARN, 4 FAIL), pero **B-12 es un falso PASS**. El agente respondió *"ksato never switched to root with su"*, que es falso (fueron 4 veces), y el check lo aprobó porque busca el número 4 y este aparece en otra parte de la respuesta. **La puntuación real es 74 %.** Los números de una sola cifra son un check muy débil. No se ha cambiado el caso después de ver el resultado; se corrige aquí la cifra.

**Lo que generaliza bien:** el compromiso de root y su hora, la puerta trasera `support2` (que no pasa por sudo), el ataque distribuido (el agente lo detecta aunque las IPs no compartan subred), el uso indebido de `backup-svc` deduciendo que el ordenador era de tmorel, las sesiones simultáneas de ldubois, la VPN tratada como interna, y la honestidad sobre los comandos de root ("no sudo commands; commands run directly as root aren't recorded").

**Lo que falla tiene un patrón: el agente confunde "mis tools no lo muestran" con "el log no lo contiene".**

| Caso | Lo que afirma el agente | La realidad |
|---|---|---|
| B-11 | *"**No.** There are no failed `su` attempts in the log… no `su` entries at all"* | 3 `su` fallidos de hmeyer; el parser no lee `su` |
| B-12 | *"ksato never switched to root with su"* | 4 veces |
| B-18 | *"The log only records when sessions **start**, not when they end"* | El log sí registra el final, y `commands_by_ip` lo muestra; el agente usó `successful_logins_by_ip`, que no lo incluye |
| B-15 | *"el log no contiene usuarios de servicio habituales"* | Hay 3: `backup-svc`, `deploy-bot` y `zabbix` |

Es **el mismo error que H-12** ([022](022-holdout-remeasure.md)): el agente no sabe qué partes del log quedan fuera de sus tools, y cuando algo no aparece en ellas concluye que no existe. En [024](024-unverified-negatives-rule-rejected.md) una regla en el prompt no lo arregló. Lo que falta es **transparencia sobre lo que cubre cada tool**: que el agente sepa que hay líneas que no analiza, o que una tool no incluye ciertos datos.

**Otras carencias:** ninguna tool ordena a los usuarios por número de logins (B-24) ni enumera todas las cuentas que inician sesión (B-15).

## Siguiente paso

1. **Cobertura explícita:** que `log_summary` indique qué líneas del log no se analizan, agrupadas por proceso (por ejemplo, "26 líneas de `su` sin analizar"), para que el agente no confunda "no lo veo" con "no existe".
2. **Parsear `su`** e incluirlo en `privileged_activity`.
3. **Listado de usuarios por número de logins**, para B-15 y B-24.
4. **La hora de cierre de sesión en `successful_logins_by_ip`**, para B-18.
5. **Endurecer el check de números de una cifra**, que dio el falso PASS de B-12.

Este held-out queda como referencia: **74 %**. Igual que el anterior, a partir de aquí se gasta un poco con cada arreglo que se inspire en él.
