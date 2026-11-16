# Log-Agent

[English](#english) · [Español](#español)

---

## English

> **This is a learning project.** I'm building it step by step with the help of [Claude](https://claude.com/claude-code) to understand how LLM agents work in practice: designing tools, writing the agent loop, evaluating the agent with evals and improving it based on what they show. Every significant change, and the reasoning behind it, is documented in [`dev_log/`](dev_log/).

An LLM agent that analyzes SSH authentication logs (`auth.log` / syslog format) using the DeepSeek API with function calling.

The model never reads the raw log. Python tools parse it and compute exact figures, and the LLM decides which tools to call, chains them together and writes the final report. This keeps numbers accurate and token usage low.

### What it can do

| Tool | Description |
|---|---|
| `log_summary` | Overview: line count, failed/successful logins, unique IPs and users, sudo commands, time range, top 5 usernames by failed attempts |
| `top_failed_ips` | Ranking of IPs by failed login attempts |
| `users_by_ip` | Usernames tried from an IP, and whether they exist on the system |
| `successful_logins_by_ip` | Successful logins from an IP and how many failures preceded each one |
| `success_after_failures` | IPs that failed several times and then got in (possible compromised accounts) |
| `commands_by_ip` | sudo commands and account changes made during the sessions of an IP |

Every tool flags whether an IP belongs to the internal network. This helps the agent tell an attacker apart from an employee who mistyped their password.

### Project structure

```
log-agent/
├── agent.py          # Agent loop, system prompt and CLI
├── tools.py          # Log parser, analysis tools and their JSON schemas
├── evals/
│   └── run_evals.py  # 90 test cases, path analysis and LLM diagnosis
├── dev_log/          # One entry per significant change: problem, fix, reasoning
├── samples/
│   └── auth.log      # Synthetic 3-day log to try the agent
├── requirements.txt
└── .env.example
```

### How it works

```
user question
     │
     ▼
┌─────────────┐   tool_calls    ┌─────────────┐
│  DeepSeek   │ ──────────────► │  tools.py   │ ── parses the log
│   (LLM)     │ ◄────────────── │             │
└─────────────┘   JSON results  └─────────────┘
     │
     ▼ (no more tool calls)
final answer
```

1. The question is sent to the model together with the system prompt and the tool schemas.
2. If the model requests tools, `run_tool()` executes them and returns the results as JSON.
3. The loop repeats until the model answers without calling any tool, with a limit of 10 steps.

The log path is injected by the agent and is never exposed to the model, so it can't read arbitrary files.

### Installation

Requires Python 3.10+.

```bash
git clone https://github.com/Kenobiiii/Log-Agent.git
cd Log-Agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your DeepSeek API key
```

### Sample log

`samples/auth.log` is a synthetic log (~16,000 lines) covering 3 days on a server of a mid-size company with about 120 employees. All IPs, users and events are fictitious. Along with normal activity (office/VPN logins, service accounts, cron, internet scanners), it contains several attack scenarios for the agent to find:

- A brute-force attack against `root` and a username dictionary attack.
- A password spray over real employee names that ends in a successful login.
- A low-volume targeted attack that compromises a service account, creates a backdoor user with sudo rights and runs a downloaded script.
- A distributed low-and-slow attack from a /24 subnet.
- False positives: employees who mistype their password from the internal network.

### Usage

Interactive mode. Ask questions and follow-ups about the log:

```bash
python agent.py samples/auth.log
```

Single question:

```bash
python agent.py samples/auth.log -q "Which IP logged in after several failed attempts?"
```

Show the tool calls the agent makes:

```bash
python agent.py samples/auth.log -v -q "What did 203.0.113.77 do after logging in?"
```

It also works on a real server log, for example `/var/log/auth.log`.

| Option | Description |
|---|---|
| `-q`, `--question` | Ask a single question and exit |
| `-v`, `--verbose` | Print tool calls and their results to stderr |
| `-m`, `--model` | Model name (default `deepseek-chat`, or `DEEPSEEK_MODEL` env var) |

The agent replies in the language of the question.

### Evaluations

`evals/run_evals.py` runs 90 realistic analyst tasks (15 per tool) against the sample log and checks the answers against known ground truth. It also analyzes the path the agent took: which tools it used, repeated calls, errors, loops and wasted steps.

```bash
python evals/run_evals.py                    # all cases
python evals/run_evals.py --tool users_by_ip # one tool
python evals/run_evals.py --case UB-09       # specific cases
```

Each case ends as **PASS**, **WARN** (correct but inefficient), **FAIL**, **STUCK** or **ERROR**. For anything that isn't a PASS, a second LLM reviews the run and suggests the root cause and a fix. Results are written to `evals/results/<timestamp>/` (`report.md`, `summary.json` and `results.jsonl`).

Every run gets a score (PASS = 1, WARN = 0.5, rest = 0) and is compared with the previous run on the cases both share: which cases improved or regressed, and what changed in between (system prompt, tools, model or the evals themselves). Each run is also added to [`evals/history.csv`](evals/history.csv). Use `--label` to describe a run:

```bash
python evals/run_evals.py --label "stricter system prompt"
```

### Development log

[`dev_log/`](dev_log/) records every significant change: what was wrong, what was changed and why. Since this is a learning project, the reasoning matters as much as the code.

### Configuration

- **Internal networks:** edit `INTERNAL_NETWORKS` in `tools.py` (default `10.0.0.0/8`).
- **Max items per tool response:** `MAX_ITEMS` in `tools.py`.
- **Max agent steps:** `MAX_STEPS` in `agent.py`.

### Limitations

- `auth.log` only records **sudo** commands and account changes. Regular shell commands are not logged, so `commands_by_ip` can't show them. For full command auditing use `auditd`.
- sudo lines don't include the source IP. Commands are attributed to a session by user and time window. If the same user has overlapping sessions from different IPs, those commands are marked as `ambiguous`.
- Syslog timestamps have no year, so the current year is assumed.
- Only IPv4 addresses in `sshd` lines are parsed.

---

## Español

> **Este es un proyecto de aprendizaje.** Lo estoy construyendo paso a paso con ayuda de [Claude](https://claude.com/claude-code) para entender cómo funcionan los agentes LLM en la práctica: diseñar herramientas, escribir el bucle del agente, evaluarlo con evals y mejorarlo según lo que muestran. Cada cambio importante, y el razonamiento detrás, queda documentado en [`dev_log/`](dev_log/).

Un agente basado en LLM que analiza logs de autenticación SSH (formato `auth.log` / syslog) usando la API de DeepSeek con *function calling*.

El modelo nunca lee el log en bruto. Las herramientas en Python lo parsean y calculan cifras exactas, y el LLM decide qué herramientas llamar, las encadena y redacta el informe final. Así los números son exactos y se gastan pocos tokens.

### Qué puede hacer

| Herramienta | Descripción |
|---|---|
| `log_summary` | Visión general: líneas, logins fallidos y exitosos, IPs y usuarios únicos, comandos sudo, rango de fechas, los 5 usuarios con más intentos fallidos |
| `top_failed_ips` | Ranking de IPs por intentos de login fallidos |
| `users_by_ip` | Usuarios probados desde una IP y si existen en el sistema |
| `successful_logins_by_ip` | Logins exitosos desde una IP y cuántos fallos hubo antes de cada uno |
| `success_after_failures` | IPs que fallaron varias veces y después consiguieron entrar (posibles cuentas comprometidas) |
| `commands_by_ip` | Comandos sudo y cambios de cuentas realizados durante las sesiones de una IP |

Todas las herramientas indican si una IP pertenece a la red interna. Esto ayuda al agente a distinguir un atacante de un empleado que se equivocó de contraseña.

### Estructura del proyecto

```
log-agent/
├── agent.py          # Bucle del agente, system prompt y CLI
├── tools.py          # Parser del log, herramientas de análisis y sus esquemas JSON
├── evals/
│   └── run_evals.py  # 90 casos de prueba, análisis del camino y diagnóstico con LLM
├── dev_log/          # Una entrada por cambio importante: problema, arreglo, razonamiento
├── samples/
│   └── auth.log      # Log sintético de 3 días para probar el agente
├── requirements.txt
└── .env.example
```

### Cómo funciona

```
pregunta del usuario
     │
     ▼
┌─────────────┐   tool_calls    ┌─────────────┐
│  DeepSeek   │ ──────────────► │  tools.py   │ ── parsea el log
│   (LLM)     │ ◄────────────── │             │
└─────────────┘ resultados JSON └─────────────┘
     │
     ▼ (sin más llamadas)
respuesta final
```

1. La pregunta se envía al modelo junto con el system prompt y los esquemas de las herramientas.
2. Si el modelo pide herramientas, `run_tool()` las ejecuta y devuelve los resultados en JSON.
3. El bucle se repite hasta que el modelo responde sin llamar a ninguna herramienta, con un límite de 10 pasos.

La ruta del log la pone el agente y nunca se expone al modelo, así que este no puede leer archivos arbitrarios.

### Instalación

Requiere Python 3.10 o superior.

```bash
git clone https://github.com/Kenobiiii/Log-Agent.git
cd Log-Agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y añade tu API key de DeepSeek
```

### Log de ejemplo

`samples/auth.log` es un log sintético (~16.000 líneas) de 3 días en un servidor de una empresa mediana de unos 120 empleados. Todas las IPs, usuarios y eventos son ficticios. Además de la actividad normal (logins desde oficina y VPN, cuentas de servicio, cron, escáneres de internet), contiene varios escenarios de ataque para que el agente los encuentre:

- Un ataque de fuerza bruta contra `root` y otro de diccionario de nombres de usuario.
- Un *password spray* sobre nombres reales de empleados que termina en un login exitoso.
- Un ataque dirigido de bajo volumen que compromete una cuenta de servicio, crea un usuario puerta trasera con permisos sudo y ejecuta un script descargado.
- Un ataque distribuido y lento desde una subred /24.
- Falsos positivos: empleados que se equivocan de contraseña desde la red interna.

### Uso

Modo interactivo. Haz preguntas y preguntas de seguimiento sobre el log:

```bash
python agent.py samples/auth.log
```

Una sola pregunta:

```bash
python agent.py samples/auth.log -q "¿Qué IP consiguió entrar tras varios intentos fallidos?"
```

Ver las llamadas a herramientas que hace el agente:

```bash
python agent.py samples/auth.log -v -q "¿Qué hizo 203.0.113.77 después de entrar?"
```

También funciona con el log de un servidor real, por ejemplo `/var/log/auth.log`.

| Opción | Descripción |
|---|---|
| `-q`, `--question` | Hace una sola pregunta y termina |
| `-v`, `--verbose` | Muestra las llamadas a herramientas y sus resultados por stderr |
| `-m`, `--model` | Nombre del modelo (por defecto `deepseek-chat`, o la variable `DEEPSEEK_MODEL`) |

El agente responde en el idioma de la pregunta.

### Evaluaciones

`evals/run_evals.py` ejecuta 90 tareas realistas de analista (15 por herramienta) sobre el log de ejemplo y comprueba las respuestas contra datos conocidos. También analiza el camino que siguió el agente: qué herramientas usó, llamadas repetidas, errores, bucles y pasos innecesarios.

```bash
python evals/run_evals.py                    # todos los casos
python evals/run_evals.py --tool users_by_ip # una herramienta
python evals/run_evals.py --case UB-09       # casos concretos
```

Cada caso termina como **PASS**, **WARN** (correcto pero ineficiente), **FAIL**, **STUCK** o **ERROR**. Para todo lo que no es PASS, un segundo LLM revisa la ejecución y propone la causa raíz y un arreglo. Los resultados se guardan en `evals/results/<fecha>/` (`report.md`, `summary.json` y `results.jsonl`).

Cada ejecución recibe una puntuación (PASS = 1, WARN = 0,5, resto = 0) y se compara con la anterior sobre los casos que tienen en común: qué casos mejoraron o empeoraron y qué cambió entre medias (system prompt, tools, modelo o los propios evals). Cada ejecución se añade también a [`evals/history.csv`](evals/history.csv). Usa `--label` para describir una ejecución:

```bash
python evals/run_evals.py --label "system prompt más estricto"
```

### Diario de desarrollo

[`dev_log/`](dev_log/) registra cada cambio importante: qué fallaba, qué se cambió y por qué. Como es un proyecto de aprendizaje, el razonamiento importa tanto como el código.

### Configuración

- **Redes internas:** edita `INTERNAL_NETWORKS` en `tools.py` (por defecto `10.0.0.0/8`).
- **Máximo de elementos por respuesta de herramienta:** `MAX_ITEMS` en `tools.py`.
- **Máximo de pasos del agente:** `MAX_STEPS` en `agent.py`.

### Limitaciones

- `auth.log` solo registra comandos **sudo** y cambios de cuentas. Los comandos normales de la shell no se registran, así que `commands_by_ip` no puede mostrarlos. Para auditar todos los comandos usa `auditd`.
- Las líneas de sudo no incluyen la IP de origen. Los comandos se atribuyen a una sesión por usuario y franja horaria. Si el mismo usuario tiene sesiones simultáneas desde IPs distintas, esos comandos se marcan como `ambiguous`.
- Las fechas de syslog no incluyen el año, así que se asume el año actual.
- Solo se parsean direcciones IPv4 en las líneas de `sshd`.
