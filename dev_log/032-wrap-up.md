# 032 — Cierre del proyecto: lo aprendido y lo que queda

**Fecha:** 2026-11-17

Este proyecto sirvió para aprender cómo funcionan los agentes con LLM en la práctica: diseñar tools, escribir el bucle del agente, medirlo con evals y mejorarlo a partir de lo que muestran. Esta entrada cierra el proyecto: resume el recorrido, las lecciones y las limitaciones conocidas.

## El recorrido en cifras

| Momento | Entrada | Conjunto principal | Held-out 1 | Held-out 2 | Llamadas/caso |
|---|---|---|---|---|---|
| Primera medición (prompt original) | [004](004-eval-scores-and-comparison.md) | 79,4 % (90 casos) | — | — | 3,6 |
| …contando el idioma de la respuesta | [010](010-language-check.md) | ~52 % | — | — | 3,6 |
| Prompt reescrito | [009](009-system-prompt-rewrite.md) | ~72 % | — | — | 1,7 |
| Sin regla de idioma | [013](013-remove-language-rule.md) | 97 % | — | — | 1,6 |
| Primera medición held-out | [017](017-holdout-suite.md) | 97–98 % | **42 %** | — | — |
| Tras arreglar lo que mostró | [022](022-holdout-remeasure.md) | 99 % (120) | **84 %** | — | — |
| Segundo held-out | [028](028-holdout2.md) | 98 % (150) | — | **74 %** | 1,4 |
| Final | [031](031-summary-compromise.md) | **98 % (154 casos)** | — | — | **1,4** |

Seguridad ([029](029-prompt-injection.md), [030](030-subtle-injection.md)): el agente no obedeció ninguna instrucción inyectada en el log (0 de 50), tanto con instrucciones evidentes como disfrazadas de datos.

## Lecciones

**Sobre agentes**

1. **Las tools pesan más que el prompt.** Los nombres de los campos, las descripciones y lo que devuelve cada tool cambiaron más el comportamiento que cualquier regla del prompt ([006](006-rename-users-tried.md), [012](012-log-summary-description.md), [016](016-top-ips-count.md), [031](031-summary-compromise.md)).
2. **Los datos, en la tool: el LLM cuenta mal.** Cada vez que el agente tenía que contar elementos de una lista, se equivocaba de vez en cuando. Darle el número ya calculado lo resolvió siempre ([007](007-subnet-breakdown.md), [016](016-top-ips-count.md)).
3. **Una instrucción en el prompt puede causar lo contrario de lo que pretende.** La regla de idioma provocaba las respuestas en español ([013](013-remove-language-rule.md)), y la de "no niegues sin comprobar" hacía que a veces se rindiera sin buscar ([024](024-unverified-negatives-rule-rejected.md)). Antes de reforzar una regla que no funciona, hay que probar a quitarla.
4. **Las reglas incondicionales se aplican siempre.** "Empieza por `log_summary`" y "revisa cada IP externa" convertían cualquier pregunta en una investigación completa ([009](009-system-prompt-rewrite.md)).
5. **Muchos errores de razonamiento son, en el fondo, falta de capacidad.** El agente negaba cosas porque no tenía forma de comprobarlas ([026](026-privileged-activity.md)). El error que queda es el mismo: confunde "mis tools no lo muestran" con "el log no lo contiene" ([028](028-holdout2.md)).
6. **Los datos que controla un atacante hay que medirlos como riesgo, no suponerlos.** Aquí el resultado fue bueno, pero solo con los ataques probados ([030](030-subtle-injection.md)).

**Sobre evaluar**

7. **Sin evals no se sabe si un cambio mejora.** Varias mejoras "obvias" no mejoraban nada, y varias regresiones resultaron ser ruido.
8. **Los LLM no son deterministas.** Una ejecución de cada caso no basta para decidir: las regresiones se confirman repitiendo con las dos versiones ([007](007-subnet-breakdown.md), [016](016-top-ips-count.md)).
9. **Un eval solo detecta lo que comprueba.** Las respuestas en otro idioma ([010](010-language-check.md)) y las afirmaciones falsas con la tabla correcta ([016](016-top-ips-count.md)) pasaban los checks sin que nadie lo notara.
10. **Los evals también fallan.** Checks de texto que rechazan respuestas correctas (cinco veces), casos que se quedan anticuados cuando aparece una tool mejor, jueces que ven datos recortados ([005](005-fix-diagnosis-truncation.md)) o que se fían de tools equivocadas ([017](017-holdout-suite.md)). Por eso hay tests de los propios checks y validación manual de los jueces.
11. **Para medir de verdad hace falta un examen que no se haya usado para ajustar.** El conjunto principal llegó al 97 % mientras el primer held-out daba un 42 %. Y un held-out se gasta cada vez que se ajusta algo mirando sus fallos ([028](028-holdout2.md)).
12. **Una verdad independiente de las tools** es lo que permitió detectar fallos que ni el agente ni el juez veían ([017](017-holdout-suite.md)).
13. **Los tests se comprueban rompiendo el código a propósito.** Dos veces, los tests nuevos no detectaron ninguno de los errores introducidos ([026](026-privileged-activity.md)).

**Sobre el coste**

14. **La mayor parte del gasto está en medir, no en usar el agente.** Por eso conviene una ejecución completa por cambio, después solo los casos afectados, y las opciones caras desactivadas por defecto ([025](025-token-usage.md)). Reducir las llamadas por pregunta (de 3,6 a 1,4) abarata todo lo demás.

## Limitaciones conocidas

- **Fechas ISO** (`2026-12-15T08:00:01+01:00`), el formato por defecto en versiones recientes de Debian y Ubuntu: el parser no las lee y el agente no vería nada ([028](028-holdout2.md)).
- **`su`** y otros procesos (CRON, systemd…) no se analizan. Además, **ninguna tool informa de qué líneas quedan fuera**, que es lo que hace que el agente confunda "no lo veo" con "no existe".
- No hay ninguna tool que ordene a los usuarios por número de logins, y `successful_logins_by_ip` no da la hora de cierre de sesión.
- Syslog no incluye el año: se usa el actual, así que un log que cruce de diciembre a enero quedaría mal ordenado en las fechas mostradas.
- SAF-08 tiene una pregunta ambigua (10 o 16 fallos), y los checks de números de una cifra son débiles (falso PASS en B-12).
- `success_after_failures` y `external_logins` se solapan, y a veces el agente llama a las dos.
- **Todos los resultados son para `deepseek-chat`.** Con otro modelo habría que volver a medir: los evals y los held-out sirven para eso.
- Los dos held-out ya están parcialmente usados. Una medición nueva y honesta necesitaría un tercero.

## Cómo seguir, si se retoma

1. Cobertura explícita: `log_summary` indicaría qué líneas no se analizan, agrupadas por proceso.
2. Parsear `su` y fechas ISO, con tests unitarios.
3. Un tercer held-out para medir.
