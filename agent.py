"""SSH log analysis agent powered by DeepSeek function calling."""

import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOLS, run_tool

DEFAULT_MODEL = "deepseek-chat"
MAX_STEPS = 10

SYSTEM_PROMPT = """You are a security analyst reviewing an SSH authentication log.

You have tools that parse the log and return exact figures. Rules:
- Always use the tools to get numbers. Never guess or invent figures.
- Start with log_summary if you don't have an overview yet.
- The top failed IPs are not the whole story: use success_after_failures to find
  IPs that eventually got in, and investigate them with users_by_ip and
  successful_logins_by_ip.
- For every external IP that logged in, use commands_by_ip to see what it did
  (sudo commands, account changes). Treat commands marked "ambiguous" with care:
  they may belong to a legitimate session of the same user.
- Distinguish real threats from internal users who simply mistyped a password
  (the "internal" field tells you if an IP belongs to the company network).
- Be concise. Use short sections and tables. Highlight what needs action.
- Reply in the same language the user writes in."""


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

    def ask(self, question: str) -> str:
        self.messages.append({"role": "user", "content": question})

        for _ in range(MAX_STEPS):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOLS,
            )
            message = response.choices[0].message
            self.messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                return message.content or ""

            for call in message.tool_calls:
                result = run_tool(call.function.name, call.function.arguments, self.log_path)
                self._log_tool_call(call.function.name, call.function.arguments, result)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })

        return "Stopped: too many tool calls without a final answer."

    def _log_tool_call(self, name: str, arguments: str, result: str) -> None:
        if not self.verbose:
            return
        preview = result if len(result) <= 300 else result[:300] + "..."
        print(f"\033[2m-> {name}({arguments or ''})\n   {preview}\033[0m", file=sys.stderr)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Analyze an SSH auth log with an LLM agent.")
    parser.add_argument("log", help="path to the log file")
    parser.add_argument("-q", "--question", help="ask a single question and exit")
    parser.add_argument("-m", "--model", default=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL))
    parser.add_argument("-v", "--verbose", action="store_true", help="show tool calls")
    args = parser.parse_args()

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
