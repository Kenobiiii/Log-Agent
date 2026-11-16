# 017 — Conjunto held-out: un log y unas preguntas que el agente no ha visto nunca

**Fecha:** 2026-11-16 · **Archivos:** `samples/generate_holdout.py`, `samples/holdout_auth.log`, `samples/holdout_truth.json`, `evals/holdout_cases.py`, `evals/run_evals.py`, `tests/test_eval_checks.py`

## Qué pasaba

El agente sacaba un 97–98 % en los evals principales, pero esa nota ya no decía mucho: **todos los arreglos se habían hecho mirando los fallos de esos mismos 105 casos y de ese mismo log.** Podía haber aprendido a analizar logs o solo a responder bien ese examen (*overfitting*).

## Qué se cambió

**1. Un log nuevo** (`samples/holdout_auth.log`, generado por `samples/generate_holdout.py`), de otra empresa y con cosas que el agente no ha visto:

- Red interna `192.168.0.0/16` (oficina) y `172.16.0.0/12` (VPN), y usuarios con punto (`emma.wilson`).
- Formatos reales de sshd: atacante **IPv6**, líneas `message repeated N times` de rsyslog, logins `keyboard-interactive/pam` y `Failed publickey`.
- Ataques nuevos:
  - *credential stuffing* (1 o 2 intentos por cuenta, entra en 3);
  - una **clave SSH robada** (jenkins entra desde fuera sin ningún fallo previo);
  - un empleado que entra de madrugada desde una IP extranjera;
  - un empleado interno al que se le deniega sudo 4 veces.

**2. Una verdad independiente de las tools.** El generador calcula a partir de lo que escribe cuántos intentos hay, quién atacó y qué cuentas cayeron, y lo guarda en `samples/holdout_truth.json`. Así, si una tool falla con el formato nuevo, se detecta en lugar de copiar su error a la respuesta esperada.

**3. 25 casos nuevos** (`evals/holdout_cases.py`) que leen las respuestas esperadas de ese JSON. Se escribieron y se guardaron en un commit (`2f509af`) **antes de ejecutar el agente ni una vez**. Se ejecutan con `python evals/run_evals.py --suite holdout`.

**4. Un check nuevo, `excludes`:** texto que no debe aparecer. Por ejemplo, la pregunta sobre un ataque desde una subred no debe mencionar `194.26.29`, la subred del log anterior.

## Por qué

- **Un examen distinto mide si se ha aprendido.** Si el agente generaliza, la nota en el held-out se parecerá a la del conjunto principal.
- **Commit antes de ejecutar.** Así queda demostrado que los casos no se escribieron mirando las respuestas.
- **Regla: este conjunto no se usa para ajustar.** Los fallos que muestre se arreglan y se validan con el conjunto principal y con tests unitarios. El held-out solo se vuelve a ejecutar para medir. Si se ajusta mirando sus fallos, deja de ser "nunca visto".
- **Un test unitario detectó un caso mal escrito antes de ejecutar nada:** H-22 era demasiado corto para detectar que estaba en español, el mismo problema que UA-14 en [014](014-user-activity-tool.md).

## Resultado

**Primero, las tools contra la verdad, sin el agente:**

| | Tools | Verdad |
|---|---|---|
| Intentos fallidos | 826 | 1.447 |
| Logins exitosos | 347 | 425 |
| IP con más fallos | `198.51.100.23` | `2001:db8:4f3a:12::17` (IPv6, 600) |
| Logins `keyboard-interactive` | 0 | 78 |
| ¿`192.168.1.50` (servidor de CI) es interna? | No | Sí |

**Después, el agente:** **42 %** (10 PASS, 1 WARN, 14 FAIL), frente al **97–98 %** del conjunto principal.

**Ninguno de los 15 casos que no dan PASS se debe a que el modelo razone mal.** Todos vienen de limitaciones de las tools:

| Causa | Casos |
|---|---|
| El parser no entiende IPv6, `message repeated`, `Failed publickey` ni `keyboard-interactive` | H-01, 02, 03, 17, 18, 20, 22 |
| `INTERNAL_NETWORKS` está fijo en `10.0.0.0/8`: todos los empleados salen como externos | H-12 (WARN, 14 llamadas), H-16, H-25 |
| Ninguna tool lista los logins externos que no tuvieron fallos antes: **la clave robada de jenkins pasa desapercibida** | H-04, 05, 08, 23 |
| `user_activity` da los fallos por IP sin fechas: mezcla los del día 1 con los del día 3 | H-13 |

**Lo que sí generaliza bien:** cuando le faltan datos, el agente lo dice (*"I can't answer this from the available tools"*, en H-17, 18 y 20) en lugar de inventar.

**El diagnóstico con LLM falló en 5 casos.** Atribuyó H-01, 13, 16, 22 y 23 a errores del caso de eval (`eval_case`), cuando la verdad del generador era correcta. El diagnóstico se fía de lo que devuelven las tools, así que, si la tool está mal, culpa al test. **Lección:** un juez que solo ve las tools no puede detectar un fallo de las tools; hace falta una verdad independiente.

## Siguiente paso

Arreglar en este orden, validando con el conjunto principal y con tests unitarios nuevos (no mirando el held-out):

1. **Parser:** IPv6, `message repeated N times`, `Failed publickey` y `keyboard-interactive`.
2. **Redes internas configurables**, con todos los rangos privados (RFC 1918) por defecto, en lugar de solo `10.0.0.0/8`.
3. **Una forma de listar los logins desde IPs externas**, haya fallos antes o no.
4. **Fechas en los fallos de `user_activity`.**

Después, una única ejecución del held-out para medir.
