# Log-Agent

[English](#english) · [Español](#español)

---

## English

An LLM agent that analyzes SSH authentication logs (`auth.log` / syslog format) using the DeepSeek API with function calling.

The model never reads the raw log. Python tools parse it and compute exact figures, and the LLM decides which tools to call, chains them together and writes the final report. This keeps numbers accurate and token usage low.

### What it can do

| Tool | Description |
|---|---|
| `log_summary` | Overview: line count, failed/successful logins, unique IPs and users, sudo commands, time range, most targeted users |
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

`samples/auth.log` is a synthetic log (~15,700 lines) covering 3 days on a server of a mid-size company with about 120 employees. All IPs, users and events are fictitious. Along with normal activity (office/VPN logins, service accounts, cron, internet scanners), it contains several attack scenarios for the agent to find:

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

Un agente basado en LLM que analiza logs de autenticación SSH (formato `auth.log` / syslog) usando la API de DeepSeek con *function calling*.

El modelo nunca lee el log en bruto. Las herramientas en Python lo parsean y calculan cifras exactas, y el LLM decide qué herramientas llamar, las encadena y redacta el informe final. Así los números son exactos y se gastan pocos tokens.

### Qué puede hacer

| Herramienta | Descripción |
|---|---|
| `log_summary` | Visión general: líneas, logins fallidos y exitosos, IPs y usuarios únicos, comandos sudo, rango de fechas, usuarios más atacados |
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

`samples/auth.log` es un log sintético (~15.700 líneas) de 3 días en un servidor de una empresa mediana de unos 120 empleados. Todas las IPs, usuarios y eventos son ficticios. Además de la actividad normal (logins desde oficina y VPN, cuentas de servicio, cron, escáneres de internet), contiene varios escenarios de ataque para que el agente los encuentre:

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

### Configuración

- **Redes internas:** edita `INTERNAL_NETWORKS` en `tools.py` (por defecto `10.0.0.0/8`).
- **Máximo de elementos por respuesta de herramienta:** `MAX_ITEMS` en `tools.py`.
- **Máximo de pasos del agente:** `MAX_STEPS` en `agent.py`.

### Limitaciones

- `auth.log` solo registra comandos **sudo** y cambios de cuentas. Los comandos normales de la shell no se registran, así que `commands_by_ip` no puede mostrarlos. Para auditar todos los comandos usa `auditd`.
- Las líneas de sudo no incluyen la IP de origen. Los comandos se atribuyen a una sesión por usuario y franja horaria. Si el mismo usuario tiene sesiones simultáneas desde IPs distintas, esos comandos se marcan como `ambiguous`.
- Las fechas de syslog no incluyen el año, así que se asume el año actual.
- Solo se parsean direcciones IPv4 en las líneas de `sshd`.
