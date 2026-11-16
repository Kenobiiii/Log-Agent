# 022 — Segunda medición del held-out: 42 % → 84 %

**Fecha:** 2026-11-16 · **Archivos:** `evals/history.csv`

## Qué pasaba

En [017](017-holdout-suite.md) el held-out dio un **42 %** frente al 97 % del conjunto principal, por cuatro causas, todas en las tools. Se arreglaron una a una, validando cada cambio con el conjunto principal, con tests unitarios y comparando las tools con la verdad del generador, **sin volver a ejecutar el agente sobre el held-out**:

| Entrada | Arreglo |
|---|---|
| [018](018-parser-formats.md) | El parser entiende IPv6, `message repeated`, `publickey` y `keyboard-interactive` |
| [019](019-internal-networks.md) | Redes internas: rangos privados por defecto y configurables |
| [020](020-external-logins.md) | `external_logins`: logins desde fuera con o sin fallos previos |
| [021](021-user-activity-dates.md) | `user_activity` fecha los fallos |

## Qué se cambió

Nada en el código. Es la medición prevista en [017](017-holdout-suite.md): una única ejecución del held-out con todos los arreglos aplicados.

## Resultado

| | Primera ejecución (017) | Ahora |
|---|---|---|
| Score | 42,0 % | **84,0 %** |
| PASS | 10 | 20 |
| WARN | 1 | 2 |
| FAIL | 14 | 3 |

**La clave robada de jenkins** se detecta ahora en las 4 preguntas sobre compromisos (H-04, 05, 08 y 23); antes no aparecía en ninguna.

**Lo que queda:**

| Caso | Qué pasa | Causa |
|---|---|---|
| H-20 (FAIL) | "¿Cuántos logins usaron keyboard-interactive?" El agente dice que no puede saberlo | Ninguna tool desglosa los logins por método de autenticación |
| H-18 (FAIL) | "¿Hubo fallos de clave pública? ¿Desde qué IPs?" El agente dice que no puede saberlo | Ninguna tool muestra el método de los fallos |
| H-12 (FAIL) | "¿Algún empleado interno usó sudo sin permiso?" El agente responde **"No"** y afirma que todos los sudo vienen de IPs externas. Fue `mason.clark`, 4 veces | No hay forma de ver los sudo denegados de todo el log, **y el agente afirma algo que no ha comprobado** |
| H-09 (WARN) | Lo resuelve con 1 llamada a `users_by_ip`, que ya indica qué usuarios entraron; el caso esperaba 2 | Caso anticuado; el camino del agente es mejor |
| H-04 (WARN) | 7 llamadas en vez de 3: revisa también IPs que no hacía falta | Exceso de investigación, con la respuesta correcta |

**H-12 es distinto de los demás.** En H-18 y H-20 el agente admite que no tiene los datos; en H-12 responde con seguridad algo falso. Es el único error de razonamiento real que ha aparecido en el held-out, y el más peligroso: un analista que se fíe de ese "No" no investigaría a `mason.clark`.

## Por qué importa cómo se ha medido

- **El agente no ha "estudiado" el held-out.** Entre las dos mediciones solo se compararon las tools con la verdad del generador. Ninguna respuesta del agente sobre el held-out se usó para cambiar nada.
- **Aun así, el held-out ya no es completamente "nuevo".** Los cuatro arreglos salieron de analizar sus fallos. Arreglar ahora estos tres y volver a medir lo desgastaría más: cada vuelta lo acerca a ser un conjunto de entrenamiento. Si se sigue mejorando a partir de él, convendría generar un **segundo held-out** para medir de verdad.

## Siguiente paso

1. **Desglose por método de autenticación** (logins y fallos), para H-18 y H-20.
2. **Una vista de los sudo denegados de todo el log**, para H-12.
3. **Una regla para no responder "no" sin haberlo comprobado:** cuando las tools no permiten verificar algo, el agente tiene que decirlo, como ya hace en H-18 y H-20.
