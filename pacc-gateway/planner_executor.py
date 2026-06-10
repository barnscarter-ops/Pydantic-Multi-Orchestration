import argparse
import asyncio
import json
import httpx
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any

EXECUTOR_URL = "http://127.0.0.1:8080/v1"
EXECUTOR_MODEL = "qwen3-14b"


@dataclass
class Step:
    id: int
    action: str         # write_file | create_file | explain
    file: str
    instruction: str
    context_files: List[str] = field(default_factory=list)


@dataclass
class Plan:
    task: str
    reasoning: str
    steps: List[Step]


async def execute_step(step: Step, executor_url: str = EXECUTOR_URL) -> str:
    context_block = ""
    for file_path in (step.context_files or []):
        p = Path(file_path)
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")
            context_block += f"[FILE: {file_path}]\n{content}\n[/FILE]\n"

    user_message = (context_block + "\n\n" if context_block else "") + f"Task: {step.instruction}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{executor_url}/chat/completions",
            json={
                "model": EXECUTOR_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert software engineer. Implement exactly what is asked. Output only the raw file content with no markdown fences, no explanation."
                    },
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.2,
                "max_tokens": 4096,
                "stream": False
            },
            headers={"Authorization": "Bearer local", "Content-Type": "application/json"}
        )

    if response.status_code != 200:
        raise RuntimeError(f"Step {step.id} failed (HTTP {response.status_code}): {response.text[:300]}")

    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Step {step.id} bad response: {e}")


async def execute_plan(plan: Plan, output_dir: Path) -> Dict[str, Any]:
    results = []
    steps_ok = 0

    for step in plan.steps:
        print(f"  [{step.id}/{len(plan.steps)}] {step.action}: {step.file}")
        try:
            output = await execute_step(step)
            success = True
        except Exception as e:
            print(f"  ERROR: {e}")
            output = str(e)
            success = False

        if success and step.action in ("write_file", "create_file") and step.file:
            target = output_dir / step.file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output, encoding="utf-8")
            print(f"  written -> {target}")
            steps_ok += 1
        elif success:
            steps_ok += 1

        results.append({
            "step": step.id,
            "file": step.file,
            "action": step.action,
            "success": success,
            "output": output if step.action == "explain" else (f"written to {output_dir / step.file}" if success else output)
        })

    return {
        "task": plan.task,
        "steps_total": len(plan.steps),
        "steps_ok": steps_ok,
        "results": results
    }


def load_plan_from_json(path: str) -> Plan:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = [Step(**s) for s in data["steps"]]
    return Plan(task=data["task"], reasoning=data["reasoning"], steps=steps)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Planner/executor: run a JSON step plan against the local model.")
    parser.add_argument("--plan", required=True, help="Path to JSON plan file")
    parser.add_argument("--output-dir", default="./pe_output", help="Directory to write generated files (default: ./pe_output)")
    parser.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    args = parser.parse_args()

    plan = load_plan_from_json(args.plan)
    print(f"\nTask:      {plan.task}")
    print(f"Reasoning: {plan.reasoning}")
    print(f"Steps:     {len(plan.steps)}\n")

    if args.dry_run:
        for step in plan.steps:
            print(f"  [{step.id}] {step.action}: {step.file}")
            print(f"       {step.instruction[:80]}...")
        raise SystemExit(0)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = asyncio.run(execute_plan(plan, output_dir))
    print(f"\n--- DONE: {summary['steps_ok']}/{summary['steps_total']} steps succeeded ---")
    for r in summary["results"]:
        status = "OK" if r["success"] else "FAIL"
        print(f"  [{status}] {r['action']}: {r['file']}")
