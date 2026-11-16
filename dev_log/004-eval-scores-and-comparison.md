# 004 — Puntuación de los evals y comparación entre ejecuciones

**Fecha:** 2026-11-16 · **Archivos:** `evals/run_evals.py`, `evals/history.csv`

## Qué pasaba

Cada ejecución de los evals generaba su propio informe, pero no había forma de saber si un cambio había mejorado el agente. Había que abrir dos `report.md` y compararlos a ojo.

## Qué se cambió

1. **Una puntuación por ejecución:** PASS = 1, WARN = 0,5 y el resto = 0. La media se expresa en porcentaje.
2. **`summary.json` en cada ejecución.** Guarda la puntuación y las métricas de cada caso y del total, y también **qué se ejecutó**: el commit de git (y si había cambios sin commit), el modelo y una huella (hash) del system prompt, de las tools y de los propios casos de eval.
3. **Comparación automática con la ejecución anterior** que tenga casos en común. Se calcula **solo sobre los casos comunes** y muestra:
   - la tabla antes / después / diferencia,
   - qué casos mejoraron y cuáles empeoraron,
   - qué casos hicieron menos o más llamadas aunque mantuvieran el estado,
   - qué cambió entre las dos ejecuciones (prompt, tools, modelo, evals),
   - un veredicto.
4. **`evals/history.csv`**: una fila por ejecución. Se sube a git, así que la evolución queda registrada.
5. **`--label`** permite describir la ejecución (por ejemplo, `--label "prompt más estricto"`) y **`--baseline`** permite elegir con qué ejecución comparar.

Al probarlo aparecieron dos fallos del propio eval, que se corrigieron:

- **UB-09, UB-08 y SL-15 daban WARN por "tool errors"**, pero en esos casos el error es lo correcto: la IP no es válida o no está en el log. Se añadió `expect_tool_error=True` a esos casos.
- **Cambiar los casos o la puntuación invalida la comparación.** Por eso se guarda también la huella de los evals, y el informe avisa si cambió.

## Por qué

- **Los LLM no son deterministas.** Sin cambiar nada, LS-01 pasó de 9 a 13 llamadas entre dos ejecuciones. Una diferencia de 1 o 2 casos puede ser simple azar. Por eso el veredicto lo advierte ("could be LLM randomness, re-run…") en lugar de declarar una mejora.
- **Comparar solo los casos comunes.** Si una ejecución tiene 6 casos y otra 90, comparar las medias no tiene sentido.
- **Ver caso por caso, no solo la media.** Una media igual puede esconder 3 casos que mejoran y 3 que empeoran. Esos empeoramientos (regresiones) son lo primero que hay que revisar.
- **Guardar la huella del prompt, las tools y los evals** sirve para saber qué se está comparando. Si cambió el eval, la diferencia de puntuación no dice nada del agente.

## Resultado

Se probó comparando ejecuciones antiguas, reconstruidas desde su `results.jsonl` porque no tenían `summary.json`, y con ejecuciones nuevas.

Primera fila del historial, la **baseline** con los 90 casos (`20261116-182804`):

| Score | PASS | WARN | FAIL | Avg tool calls |
|---|---|---|---|---|
| 79.4 % | 55 | 33 | 2 | 3.63 |

Todos los cambios siguientes se miden contra esta baseline.
