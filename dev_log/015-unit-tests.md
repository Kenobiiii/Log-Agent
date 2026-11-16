# 015 — Tests unitarios con pytest

**Fecha:** 2026-11-16 · **Archivos:** `tests/`, `pytest.ini`, `requirements-dev.txt`, `README.md`

## Qué pasaba

El proyecto no tenía tests de las tools. La única red de seguridad eran los evals, que:

- **son lentos y cuestan dinero**: llaman al LLM 105 veces;
- **tienen ruido**: el mismo caso puede dar PASS o WARN sin cambiar nada;
- **detectan los fallos de forma indirecta.** Si el parser empezara a contar dos veces cada fallo, lo veríamos como "el agente responde mal", no como "el parser cuenta mal".

Además, el agente se ha ajustado a esos mismos evals, así que una nota alta ya no garantiza que todo esté bien por debajo.

## Qué se cambió

63 tests en tres archivos, que tardan menos de un segundo y no llaman al LLM:

| Archivo | Qué comprueba |
|---|---|
| `test_parser.py` | Cada regla del parser, con un log mínimo escrito a mano: un intento fallido cuenta una vez aunque genere 4 líneas, usuarios inválidos, días con doble espacio, sesiones abiertas y cerradas, sudo permitido y denegado, cambios de cuenta, líneas mal formadas, invalidación de la caché |
| `test_tools.py` | La lógica de cada tool con ese log mínimo, la validación de entradas (incluidos los avisos de tool correcta de [014](014-user-activity-tool.md)), las cifras del log de ejemplo y `run_tool` (errores siempre en JSON, el modelo no puede elegir el archivo, todo esquema tiene su función) |
| `test_eval_checks.py` | Los checks de los evals: números con separadores de miles, detección de idioma, `classify` (PASS, WARN, STUCK, `expect_tool_error`) y que los casos estén bien formados |

Para instalar pytest: `pip install -r requirements-dev.txt`. Para ejecutarlos: `pytest`.

## Por qué

- **Dos tipos de prueba para dos preguntas distintas.** Los evals responden "¿el agente usa bien los datos?". Los tests unitarios responden "¿los datos que recibe son correctos?". Si los segundos fallan, los primeros no significan nada.
- **Un log mínimo escrito a mano.** Con 15 líneas se sabe exactamente qué debe salir; con el log de ejemplo, de 16.000 líneas, un error puede quedar oculto entre las cifras grandes.
- **También se testea el log de ejemplo, como regresión.** Sus cifras (4147, 1850, 25 IPs en la subred…) son las respuestas esperadas de los evals. Si cambian, los evals están mal.
- **Los checks de los evals también se testean.** Los falsos FAIL de [003](003-fix-ub-09-invalid-ip.md), [008](008-fix-no-check.md) y el de UA-14 en [014](014-user-activity-tool.md) venían de ellos. `test_spanish_cases_are_detected_as_spanish` habría detectado el de UA-14 antes de gastar una ejecución.

## Resultado

63 de 63 tests pasan en 0,5 segundos.

**Para comprobar que los tests sirven, se rompió el código a propósito** (*mutation testing* manual) y se miró si fallaban:

| Error introducido en `tools.py` | ¿Lo detectan? |
|---|---|
| `>` en lugar de `>=` en `success_after_failures` | Sí, fallan 2 tests |
| El campo `internal` siempre `False` | Sí, falla 1 test |
| Contar también las líneas `Invalid user` (doble conteo) | Sí: `test_counts_each_failed_attempt_once` da 4 en lugar de 3 |

**Lección:** un test que pasa a la primera puede estar comprobando algo o no estar comprobando nada. Para saberlo, hay que romper el código a propósito y ver si falla.
