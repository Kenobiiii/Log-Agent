# 002 — Diagnóstico automático de fallos en los evals

**Fecha:** 2026-11-12 · **Archivos:** `evals/run_evals.py`, `agent.py`

## Qué pasaba

El report decía **qué** fallaba (por ejemplo, "9 tool calls, optimal ~1"), pero no **por qué** ni **cómo arreglarlo**. Para averiguarlo había que abrir `results.jsonl` y leer la traza a mano.

## Qué se cambió

Los casos que no salen PASS reciben dos tipos de ayuda:

1. **Pistas por reglas.** Son deterministas y no usan ningún LLM. Por ejemplo:
   - Si la primera llamada fue `log_summary` sin hacer falta → apunta a la regla del system prompt.
   - Si una llamada se repite → sugiere prohibir las repeticiones.
2. **Diagnóstico con LLM.** Un segundo modelo recibe el system prompt, las descripciones de las tools, el caso y la traza con los resultados de las tools, y devuelve un JSON con:
   - `category`: dónde está el problema (`system_prompt`, `tool_description`, `tool_output`, `missing_tool`, `model_reasoning` o `eval_case`).
   - `root_cause` y `evidence`: por qué pasa, citando la traza.
   - `fix` y `where`: qué cambiar y en qué archivo.

El report incluye ahora una sección "Suggested fixes by category" que agrupa los arreglos. En `agent.py`, la traza guarda también los primeros 3000 caracteres de cada resultado de tool, porque sin ellos el diagnóstico no puede saber si el dato estaba disponible.

## Por qué

- **Un segundo LLM como revisor** es una versión del patrón *evaluator* de Anthropic: un modelo genera y otro evalúa. Aquí no se itera automáticamente, solo se proponen arreglos para que los aplique una persona.
- **La categoría `eval_case` es clave.** Un test puede estar mal, y el diagnóstico tiene que poder decir "el agente lo hizo bien, el problema es el caso".
- **Las pistas por reglas y el LLM se complementan.** Las reglas son gratis y siempre dan lo mismo, pero solo detectan patrones conocidos. El LLM encuentra causas nuevas, pero puede equivocarse. Por eso incluye `evidence` y `confidence`, para poder comprobarlo.
- **Solo se diagnostica lo que no es PASS**, para no gastar llamadas de más. Se puede desactivar con `--no-diagnose`.

## Resultado

Se probó con 6 casos. Los 4 que no salieron PASS recibieron un diagnóstico coherente:

- **3 WARN** → `system_prompt`. Falta una regla que ajuste la investigación a lo que se pregunta.
- **1 FAIL** (UB-09) → `eval_case`. El agente había respondido bien; el error estaba en el test (ver [003](003-fix-ub-09-invalid-ip.md)).
