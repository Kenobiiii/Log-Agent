# 019 — Redes internas: rangos privados por defecto y configurables

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`, `agent.py`, `tests/test_internal_networks.py`, `README.md`, `.env.example`

## Qué pasaba

`INTERNAL_NETWORKS` estaba fijo en `10.0.0.0/8`, porque la empresa del log de ejemplo usa esa red. En el held-out ([017](017-holdout-suite.md)) la oficina es `192.168.x.x` y la VPN `172.16.x.x`, así que **todos los empleados salían como externos**:

- **H-16:** el agente afirmó que el servidor de CI `192.168.1.50` era externo.
- **H-25:** a la pregunta del último login desde fuera respondió con un empleado de la oficina.
- **H-12:** hizo 14 llamadas para acabar diciendo que ningún empleado interno había usado sudo sin permiso.

Era un ajuste al log de ejemplo dentro del propio código.

## Qué se cambió

- **Por defecto**, los rangos privados reales: `10.0.0.0/8`, `172.16.0.0/12` y `192.168.0.0/16` (RFC 1918), y `fc00::/7` (el equivalente en IPv6).
- **Configurable** con la opción `--internal-networks 10.20.0.0/16,192.168.1.0/24` del agente o con la variable de entorno `LOG_AGENT_INTERNAL_NETWORKS`. Un valor inválido se rechaza con un error claro.
- 18 tests nuevos (92 en total).

## Por qué

- **No se usa `ipaddress.is_private`, aunque parecía lo natural.** Esa función considera "privados" los rangos reservados para documentación (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`), y en ellos están **todos los atacantes de los dos logs**. Con ella, el agente vería a los atacantes como internos: un fallo mucho peor que el que se quería arreglar. Ya se había evitado al principio del proyecto por la misma razón, y ahora queda un comentario en el código y un test que lo comprueba.
- **Rangos privados por defecto, y no una red concreta.** Casi cualquier empresa usa alguno de ellos, así que el valor por defecto funciona sin configurar nada. Quien tenga otra red, o quiera ser más estricto (por ejemplo, que solo la VPN cuente como interna), puede indicarla.
- **Variable de entorno además de la opción.** Así se puede fijar una vez en el `.env` y no repetirla en cada ejecución.

## Resultado

**Sin cambios en el log de ejemplo:** la foto de la salida de las 7 tools es idéntica, porque ese log no tiene ninguna IP `172.16.x` ni `192.168.x`.

**Tests:** 92 de 92, con la variable de entorno definida y sin ella. Si alguien sustituyera la lista por `is_private`, fallarían 7 tests; se comprobó introduciendo ese cambio.

**Las tools contra la verdad del held-out**, sin ejecutar el agente:

| | Antes (`10.0.0.0/8`) | Ahora (por defecto) |
|---|---|---|
| IPs mal clasificadas | 125 / 256 | **0 / 256** |
| Logins externos reales marcados como externos | 5 / 5 | 5 / 5 |
| `192.168.1.50` (servidor de CI) interna | No | **Sí** |
