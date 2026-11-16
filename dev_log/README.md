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
| [005](005-fix-diagnosis-truncation.md) | 2026-11-16 | Fix: el diagnóstico culpaba a la tool de un recorte que hacía el propio eval |
| [006](006-rename-users-tried.md) | 2026-11-16 | Renombrar `users_tried` a `users_tried_before_success` (SAF-12) |
| [007](007-subnet-breakdown.md) | 2026-11-16 | `top_failed_ips` agrupa las IPs por subred (TF-06) |
| [008](008-fix-no-check.md) | 2026-11-16 | Fix: el check de "no" rechazaba respuestas correctas (TF-03) |
| [009](009-system-prompt-rewrite.md) | 2026-11-16 | Reescritura del system prompt: 79,7 % → 94,7 %, la mitad de llamadas |
| [010](010-language-check.md) | 2026-11-16 | Los evals comprueban el idioma: 1 de cada 4 respuestas estaba en otro idioma |
| [011](011-review-optimal-calls.md) | 2026-11-16 | Revisión de `optimal_calls`: 4 casos demasiado estrictos |
| [012](012-log-summary-description.md) | 2026-11-16 | Descripción de `log_summary`: nombre del ranking y cuándo usarla (LS-05) |
| [013](013-remove-language-rule.md) | 2026-11-16 | Quitar la regla de idioma: la propia regla causaba las respuestas en español (81,1 % → 97 %) |
| [014](014-user-activity-tool.md) | 2026-11-16 | Nueva tool `user_activity`: buscar por usuario en lugar de por IP |
| [015](015-unit-tests.md) | 2026-11-16 | Tests unitarios con pytest: 63 tests del parser, las tools y los checks de los evals |
| [016](016-top-ips-count.md) | 2026-11-16 | `top_failed_ips` dice cuántas IPs devuelve: afirmaciones falsas 13/15 → 0/15 (TF-12) |
| [017](017-holdout-suite.md) | 2026-11-16 | Conjunto held-out: 42 % frente al 97 % del principal; todos los fallos vienen de las tools |
| [018](018-parser-formats.md) | 2026-11-16 | El parser entiende IPv6, `message repeated`, `publickey` y `keyboard-interactive` |

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
