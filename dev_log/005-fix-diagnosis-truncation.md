# 005 — Fix: el diagnóstico culpaba a la tool de un recorte que hacía el propio eval

**Fecha:** 2026-11-16 · **Archivos:** `evals/run_evals.py`, `agent.py`

## Qué pasaba

En la baseline, el caso **TF-06** dio FAIL: el agente contó 24 IPs `194.26.29.x` en el top 30 y son 25. El diagnóstico con LLM dijo, con confianza *high*:

> "La herramienta top_failed_ips devolvió la lista truncada… El agente no tuvo forma de ver los IPs 12-30."

**Era falso.** El agente recibió el resultado completo: 3.177 caracteres con las 25 IPs. El recorte lo hacía el evaluador, que al preparar los datos del diagnóstico cortaba cada resultado a 1.200 caracteres **sin avisar**. El revisor vio una lista cortada a mitad y sacó una conclusión equivocada.

## Qué se cambió

- Cada resultado que se envía al diagnóstico incluye `result_chars` (el tamaño completo que vio el agente) y `truncated_for_review` (si se ha recortado para la revisión).
- El prompt del diagnóstico avisa: el recorte es solo para la revisión, el agente siempre recibió el resultado completo, y no se puede concluir que le faltaron datos por ese motivo.
- Límites: el diagnóstico recibe 4.000 caracteres por resultado (antes 1.200) y la traza de `agent.py` guarda 20.000 (antes 3.000). En la práctica, la traza guarda ahora los resultados completos.

## Por qué

- **Un evaluador que miente es peor que no tener evaluador.** El diagnóstico proponía cambiar la tool para arreglar un problema que no existía. Si se hubiera aplicado sin revisar, habríamos complicado la tool para nada.
- **Subir el límite no basta.** Siempre habrá un resultado más grande que el límite. Lo importante es que el revisor **sepa** que está viendo un recorte. Por eso se marca en cada resultado y además se explica en el prompt.
- **Lección:** cuando un LLM juzga a otro, hay que asegurarse de que el juez ve lo mismo que vio el juzgado, o de que sabe exactamente en qué se diferencia lo que ve.

## Resultado

Se volvió a diagnosticar el TF-06 guardado en la baseline, cuya traza aún tenía el recorte antiguo:

| | Antes | Después |
|---|---|---|
| Categoría | `tool_output` | `model_reasoning` |
| Causa | "la tool truncó la lista" (falso) | "recibió la lista completa y contó mal" (correcto) |

La causa real de TF-06, que el modelo cuenta mal las listas largas, se arregla en [007](007-subnet-breakdown.md).
