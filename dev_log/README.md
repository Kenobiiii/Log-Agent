# Dev log

Diario de desarrollo del proyecto. Cada cambio importante tiene su entrada: qué pasaba, qué se cambió y por qué.

El objetivo es aprender. Por eso el razonamiento importa tanto como el código.

## Entradas

| # | Fecha | Cambio |
|---|---|---|
| [001](001-evals.md) | 2026-11-12 | Sistema de evals: 90 casos y análisis del camino del agente |
| [002](002-eval-diagnosis.md) | 2026-11-12 | Diagnóstico automático de los casos que fallan |
| [003](003-fix-ub-09-invalid-ip.md) | 2026-11-12 | Fix: UB-09 daba FAIL con una respuesta correcta |
| [004](004-eval-scores-and-comparison.md) | 2026-11-16 | Puntuación de los evals, historial y comparación entre ejecuciones |

## Plantilla

Las entradas se numeran (`004-titulo-corto.md`) y siguen esta estructura:

```markdown
# 00X — Título

**Fecha:** AAAA-MM-DD · **Archivos:** `archivo.py`

## Qué pasaba
El problema o la necesidad, con la evidencia (caso de eval, report, traza…).

## Qué se cambió
El cambio concreto, lo más corto posible.

## Por qué
El razonamiento: qué alternativas había y por qué se eligió esta.

## Resultado
Cómo se comprobó que funciona (antes / después).
```
