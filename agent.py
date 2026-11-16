"""SSH log analysis agent powered by DeepSeek function calling."""

import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

from tools import INTERNAL_NETWORKS_ENV, TOOLS, run_tool, set_internal_networks

DEFAULT_MODEL = "deepseek-chat"
MAX_STEPS = 10
TRACE_RESULT_CHARS = 20000

SYSTEM_PROMPT = """You are a security analyst answering questions about an SSH authentication log.
Your tools parse the log and return exact figures.

How to work:
- Answer exactly what the user asked, using the fewest tool calls that answer it.
  Then reply. Do not run a full investigation for a specific question.
- Every number in your answer must come from a tool result. Use counts the tools
  already computed (e.g. subnets_in_top, users_tried_before_success) instead of
  counting list items yourself.
- Never repeat a tool call with the same arguments; reuse the earlier result.
- Call log_summary only when the question needs overall figures (totals, time
  range, top usernames by failed attempts), not as a routine first step.
- If a follow-up would add value (e.g. checking what an IP did after logging in),
  offer it in one line at the end instead of doing it.

Only for broad requests ("analyze the log", "were we compromised?", incident review):
1. log_summary for the overview.
2. top_failed_ips for high-volume attacks.
3. external_logins for every login from outside the network, with or without
   failed attempts before it. Compromises with stolen keys or passwords have no
   failures and don't show up in the top or in success_after_failures.
4. For each external IP that got in: commands_by_ip to assess the impact. Commands
   marked "ambiguous" may belong to a legitimate session of the same user.

Interpreting results:
- The "internal" field tells you whether an IP is in the company network. Internal
  IPs with a few failures before a success are usually users mistyping their
  password, not attacks.

Answer style:
- Be concise: short sections and tables. Highlight what needs action."""


class LogAgent:
    def __init__(self, log_path: str, model: str = DEFAULT_MODEL, verbose: bool = False):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")

        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = model
        self.log_path = log_path
        self.verbose = verbose
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_trace = None

    def ask(self, question: str) -> str:
        """Run the agent loop for one question.

        After each call, `self.last_trace` holds the steps, tool calls and
        token usage of that run (used for logging and evaluation).
        """
        self.messages.append({"role": "user", "content": question})
        trace = {
            "steps": 0,
            "tool_calls": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "hit_max_steps": False,
        }
        self.last_trace = trace

        for step in range(1, MAX_STEPS + 1):
            trace["steps"] = step
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOLS,
            )
            if response.usage:
                trace["prompt_tokens"] += response.usage.prompt_tokens
                trace["completion_tokens"] += response.usage.completion_tokens

            message = response.choices[0].message
            self.messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                return message.content or ""

            for call in message.tool_calls:
                started = time.perf_counter()
                result = run_tool(call.function.name, call.function.arguments, self.log_path)
                trace["tool_calls"].append({
                    "step": step,
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                    "result_chars": len(result),
                    "result": result[:TRACE_RESULT_CHARS],
                    "error": _extract_error(result),
                    "seconds": round(time.perf_counter() - started, 4),
                })
                self._log_tool_call(call.function.name, call.function.arguments, result)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })

        trace["hit_max_steps"] = True
        return "Stopped: too many tool calls without a final answer."

    def _log_tool_call(self, name: str, arguments: str, result: str) -> None:
        if not self.verbose:
            return
        preview = result if len(result) <= 300 else result[:300] + "..."
        print(f"\033[2m-> {name}({arguments or ''})\n   {preview}\033[0m", file=sys.stderr)


def _extract_error(result: str) -> str | None:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return "non-JSON tool result"
    return data.get("error") if isinstance(data, dict) else None


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Analyze an SSH auth log with an LLM agent.")
    parser.add_argument("log", help="path to the log file")
    parser.add_argument("-q", "--question", help="ask a single question and exit")
    parser.add_argument("-m", "--model", default=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL))
    parser.add_argument("-v", "--verbose", action="store_true", help="show tool calls")
    parser.add_argument("--internal-networks", default=os.getenv(INTERNAL_NETWORKS_ENV),
                        help="comma-separated CIDRs of the company network "
                             "(default: 10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7)")
    args = parser.parse_args()

    if args.internal_networks:
        try:
            set_internal_networks(args.internal_networks)
        except ValueError as e:
            parser.error(f"--internal-networks: {e}")

    if not os.path.isfile(args.log):
        parser.error(f"file not found: {args.log}")

    agent = LogAgent(args.log, model=args.model, verbose=args.verbose)

    if args.question:
        print(agent.ask(args.question))
        return

    print(f"Analyzing {args.log}. Type 'exit' to quit.\n")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in {"exit", "quit"}:
            break
        if question:
            print(f"\n{agent.ask(question)}\n")


if __name__ == "__main__":
    main()
