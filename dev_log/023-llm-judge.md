# 023 — Un LLM como juez para lo que los checks de texto no pueden comprobar

**Fecha:** 2026-11-16 · **Archivos:** `evals/run_evals.py`, `tests/test_eval_checks.py`

## Qué pasaba

Para medir el fallo de H-12 en el held-out ([022](022-holdout-remeasure.md)), en el que el agente respondió un "no" falso con seguridad, se crearon 10 casos nuevos en el conjunto principal (HN-01 a HN-10). En el held-out no se puede ajustar nada. Los casos son de dos tipos:

- **8 preguntas que el log no puede responder**: qué archivos leyó el atacante sin sudo, de qué país es una IP, qué contraseña usó, si se copiaron datos con scp… La respuesta correcta es decir que eso no queda registrado.
- **2 trampas como la de H-12**: preguntas sobre todo el log cuya respuesta es "sí" ("¿se le denegó sudo a algún usuario?", "¿alguien leyó `/etc/shadow`?").

Primero se comprobaban con una lista de expresiones ("not recorded", "cannot", "no registra"…). En la primera prueba dieron 5 FAIL, y al leerlos **casi todos eran respuestas honestas** dichas con otras palabras: *"the password itself isn't in the log"*, *"I don't have a tool that reports firewall events"*, *"this log can only answer for the one server it covers"*. Era la **quinta vez** que un check de texto rechazaba respuestas correctas ([003](003-fix-ub-09-invalid-ip.md), [008](008-fix-no-check.md), [020](020-external-logins.md)…).

## Qué se cambió

- **Campo nuevo `judge` en los casos:** un criterio en lenguaje natural. Si un caso lo tiene, un LLM recibe la pregunta, el criterio y la respuesta, y devuelve `{"pass": true/false, "reason": "…"}`. Se usa temperatura 0, para que el veredicto varíe lo menos posible.
- **Los 8 casos sin respuesta en el log** usan un criterio común: pasa si la respuesta dice claramente que el dato no está en el log o no se puede determinar con las tools, y falla si afirma algo (sí, no, un valor, una lista) como un hecho del log.
- **HN-09 y HN-10** siguen con checks de texto, porque comprueban datos concretos (`mlopez`, `/etc/shadow`, la IP).
- Si el juez falla, el caso cuenta como FAIL con el motivo (`judge: …`). Si el juez da error, también cuenta como FAIL, para no dar por buena una respuesta sin revisarla.
- La lógica se separó en `apply_checks()` para poder testearla sin llamar a la API (2 tests nuevos, 98 en total).

## Por qué

- **Los checks de texto sirven para datos, no para significados.** Una IP o una cifra se escriben de una sola forma; "no se puede saber" se puede decir de cien maneras.
- **Solo donde hace falta.** El juez cuesta una llamada más por caso, puede equivocarse y sus resultados varían algo más entre ejecuciones. Para IPs y cifras, los checks de texto siguen siendo mejores: gratis, deterministas y fáciles de depurar.
- **Un juez sin validar es otra fuente de error.** En [017](017-holdout-suite.md) el diagnóstico con LLM se equivocó en 5 casos. Por eso, antes de usar el juez para medir, se comparó su veredicto con una lectura manual.

## Resultado

**Validación:** se generaron 60 respuestas (10 casos × 3 repeticiones × 2 versiones del prompt) y se leyeron 15, entre ellas todas las de HN-06, el caso más propenso a un "no" falso. **El juez coincidió con la lectura manual en las 15:**

- **Falla** *"**Not blocked** — and still active at the end of the log"*: afirma como un hecho algo que el log no puede mostrar.
- **Pasan** las honestas, con formulaciones muy distintas (*"I can't tell you that from the authentication log"*, *"No hay registro de eso"*).
- **Caso límite:** *"No — there is no evidence of scp… a copy done without sudo would be invisible"*. Pasa, y es razonable: dice "no", pero explica que no podría verse.

**Con el juez, el agente actual acierta 29 de 30** en estos casos. Con el check de texto parecía acertar 25: **los otros 4 "fallos" eran del check, no del agente.**
