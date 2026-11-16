# 025 — Consumo de tokens y diagnóstico opcional

**Fecha:** 2026-11-17 · **Archivos:** `evals/run_evals.py`, `README.md`

## Qué pasaba

El panel de DeepSeek mostraba **9,3 M tokens en un día**: 6,0 M de input con *cache hit*, 2,5 M de input con *cache miss* y 0,77 M de output. Había que saber si era normal o si se perdían tokens en algún sitio.

## Análisis

Sumando los tokens que registran las propias ejecuciones (`results.jsonl`):

| Qué | Ejecuciones | Casos | Tokens |
|---|---|---|---|
| Evals completos (90–130 casos) | 17 | 1.745 | 8,1 M |
| Evals parciales y held-out | 7 | 100 | 0,6 M |
| **Total registrado** | | | **8,7 M** |

El resto (~0,6 M) son los diagnósticos con LLM (114 ese día), el juez y las pruebas A/B, que no se registran.

- **El input es 11 veces el output** porque en cada paso del bucle el agente reenvía todo el contexto: system prompt, descripciones de las tools y todos los mensajes y resultados anteriores. Un caso gasta de media ~4.700 tokens.
- **El 70 % del input sale de caché.** DeepSeek detecta que el principio de cada petición (system prompt y tools) es idéntico al de peticiones anteriores y lo cobra mucho más barato. Es el patrón normal de un eval.
- **No hay ninguna fuga:** el gasto lo explican casi entero las ejecuciones completas de los evals.

## Qué se cambió

**El diagnóstico con LLM pasa a ser opcional:** se activa con `--diagnose`, en lugar de desactivarse con `--no-diagnose`. Hace una llamada extra con un contexto grande por cada caso que no da PASS, y la mayoría de las veces nadie leía ese diagnóstico.

## Por qué

- **Las opciones caras no deberían estar activadas por defecto.** El diagnóstico es útil cuando se va a analizar un fallo, no en cada ejecución de comprobación.
- **Hábitos para gastar menos**, a partir de este análisis:
  1. Para un cambio que afecta a una sola tool: tests unitarios + foto de las tools (gratis) + los casos de esa tool (`--tool`) + **una** ejecución completa, en lugar de dos.
  2. Pruebas A/B con 5 repeticiones; solo se amplían si el resultado es dudoso.
  3. `--diagnose` solo cuando se vaya a leer el diagnóstico.
- **Lo que ya se ahorró:** reescribir el prompt ([009](009-system-prompt-rewrite.md)) bajó las llamadas por caso de 3,6 a ~2. Ese ahorro se nota también en cada pregunta real que se le haga al agente.
