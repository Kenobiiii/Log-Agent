# 001 — Sistema de evals

**Fecha:** 2026-11-12 · **Archivos:** `evals/run_evals.py`, `agent.py`, `samples/auth.log`

## Qué pasaba

El agente funcionaba, pero solo lo había probado a mano con un par de preguntas. Sin una forma de medirlo no hay manera de saber si un cambio en el prompt o en una tool lo mejora o lo empeora.

## Qué se cambió

Se creó `evals/run_evals.py`, con **90 casos: 15 por cada tool**. Cada caso tiene:

- **Una pregunta realista**, como la haría un analista. Algunas se resuelven con una llamada y otras necesitan encadenar varias tools.
- **Las tools que debería usar.**
- **Cuántas llamadas haría un camino razonable** (`optimal_calls`).
- **Qué debe aparecer en la respuesta:** IPs, usuarios o cifras exactas sacadas del log de ejemplo.

Para cada caso, el script ejecuta el agente, revisa la respuesta, analiza el camino que siguió y le asigna un estado:

| Estado | Significa |
|---|---|
| PASS | Respuesta correcta y camino eficiente |
| WARN | Respuesta correcta, pero con llamadas de más, repetidas o sin usar la tool esperada |
| FAIL | Respuesta incorrecta o incompleta |
| STUCK | El agente entra en bucle o agota los pasos |
| ERROR | Falla la API |

Cada ejecución guarda `report.md` (resumen) y `results.jsonl` (detalle completo) en `evals/results/<fecha>/`.

Cambios necesarios en otros archivos:

- **`agent.py`:** `LogAgent` guarda ahora una traza de cada ejecución (`last_trace`) con los pasos, las llamadas a tools y los tokens. Sin ella el eval solo vería la respuesta final, no el camino.
- **`samples/auth.log`:** al preparar los datos de referencia apareció una incoherencia. En un ataque, `admin` aparecía como usuario existente, y en el resto del log como inexistente. Se corrigió el generador y se regeneró el log.

## Por qué

- **Preguntas realistas y no triviales.** Las preguntas tipo "llama a X con Y" solo comprueban que la tool existe. Las que obligan al agente a decidir qué hacer son las que muestran sus fallos. Así lo recomienda la guía de Anthropic sobre escribir tools para agentes.
- **Comprobar el camino además de la respuesta.** Un agente puede acertar y aun así gastar 10 llamadas donde bastaba 1, lo que cuesta más tokens y más tiempo. Eso solo se ve analizando la traza.
- **Comprobaciones por texto y no con un LLM.** Son gratis, deterministas y fáciles de depurar. La contrapartida es que pueden dar falsos FAIL si el agente lo dice con otras palabras (ver [003](003-fix-ub-09-invalid-ip.md)).

## Resultado

Primera prueba con 1 caso por tool: **3 PASS y 3 WARN**. Los 3 WARN tienen la misma causa: el agente investiga de más. En LS-01 se le pedía un resumen y respondió con 9 llamadas, cuando bastaba 1. El origen está en el system prompt ("Start with log_summary", "use commands_by_ip on every external IP…"). Queda pendiente de arreglar.
