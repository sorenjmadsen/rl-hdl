"""Plan / Forge / Prove — three roles, one self-improvement loop.

From the design meeting (Jun 20): the three "agents" are tools, effectively one
model improving a Verilog design in a loop until it stops getting better
("watch it get better"). They wire around the existing cologic seam:

  Plan  (Claude)  -> a short strategy/critique hint for the next attempt
  Forge (policy)  -> writes/rewrites the candidate Verilog            (cologic.prompt)
  Prove (Verilator) -> grades candidate vs golden reference, maps outputs -> feedback
                                                                      (cologic.verifier.grade)

The model and grader are injected callables so the loop is testable offline
(see demo() at the bottom — no API key, no Verilator needed). The real defaults
hit Fireworks + Verilator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from cologic.prompt import build_messages
from cologic.schema import GradeResult, Task

# A model is just: messages -> completion text. Fireworks/Gemma, Claude, or a stub.
ModelFn = Callable[[list[dict]], str]
# A grader is: (completion, task) -> GradeResult. Defaults to cologic.verifier.grade.
GraderFn = Callable[[str, Task], GradeResult]


def feedback_from(result: GradeResult) -> str:
    """Prove's 'output mapper': turn a GradeResult into a one-line critique the
    next attempt can act on. Stable against the info contract in cologic.schema."""
    info = result.info
    stage = info.get("stage")
    if stage == "no_module":
        return "No Verilog module was found in your output. Emit exactly one module."
    if stage == "compile_error":
        return "It did not compile. Fix the syntax/port errors:\n" + info.get("log", "")[:800]
    if stage == "sim_error":
        return "It compiled but the simulation failed to run:\n" + info.get("log", "")[:800]
    passed, total = info.get("passed", 0), info.get("total", 0)
    if total and passed == total:
        return f"All {total} output comparisons match the reference. Correct."
    return (f"Compiles, but {total - passed}/{total} output comparisons mismatch the "
            f"reference. The logic is wrong on some inputs — re-derive it.")


@dataclass
class Plan:
    """Planning agent (Claude). Produces a strategy hint for the next forge.

    Default is a pass-through of Prove's feedback (lazy but honest: the critique
    already says what to fix). Swap in a Claude-backed planner by passing model_fn
    — it gets the spec + history and returns a richer plan. ponytail: pass-through
    until a planner measurably beats it."""

    model_fn: ModelFn | None = None

    def __call__(self, task: Task, last_feedback: str, history: list["Attempt"]) -> str:
        if not last_feedback:
            return ""  # first attempt: no plan needed, the spec is the plan
        if self.model_fn is None:
            return last_feedback
        msgs = [
            {"role": "system", "content": "You are a hardware design planner. Given a "
             "Verilog spec and the grader's critique of the last attempt, reply with a "
             "short, concrete plan (2-4 bullets) for fixing it. No code."},
            {"role": "user", "content": f"Spec:\n{task.spec}\n\nCritique:\n{last_feedback}"},
        ]
        return self.model_fn(msgs)


@dataclass
class Forge:
    """Forging agent. Writes / rewrites the candidate Verilog via the policy model."""

    model_fn: ModelFn

    def __call__(self, task: Task, plan_hint: str, prev: "Attempt | None") -> str:
        msgs = build_messages(task)
        if prev is not None:
            # Feed back the last attempt + the plan so the model revises, not restarts.
            msgs.append({"role": "assistant", "content": prev.completion})
            critique = plan_hint or prev.feedback
            msgs.append({"role": "user", "content": critique + "\n\nReturn the corrected module."})
        return self.model_fn(msgs)


@dataclass
class Prove:
    """Proving agent. Grades the candidate with real silicon tooling (Verilator)."""

    grader: GraderFn | None = None

    def __call__(self, task: Task, completion: str) -> GradeResult:
        grade = self.grader
        if grade is None:
            from cologic.verifier import grade as grade  # lazy import: Verilator only when real
        return grade(completion, task)


@dataclass
class Attempt:
    iteration: int
    completion: str
    reward: float
    feedback: str
    info: dict = field(default_factory=dict)


def improve(
    task: Task,
    *,
    forge_model: ModelFn,
    plan_model: ModelFn | None = None,
    grader: GraderFn | None = None,
    max_iters: int = 6,
    target_reward: float = 1.0,
    patience: int = 2,
) -> tuple[Attempt, list[Attempt]]:
    """Run Plan->Forge->Prove until the design hits target_reward, stops improving
    for `patience` rounds, or max_iters. Returns (best_attempt, full_history)."""
    plan, forge, prove = Plan(plan_model), Forge(forge_model), Prove(grader)
    history: list[Attempt] = []
    best: Attempt | None = None
    stale = 0

    for i in range(max_iters):
        prev = history[-1] if history else None
        last_feedback = prev.feedback if prev else ""
        hint = plan(task, last_feedback, history)
        completion = forge(task, hint, prev)
        result = prove(task, completion)
        att = Attempt(i, completion, result.reward, feedback_from(result), result.info)
        history.append(att)

        if best is None or att.reward > best.reward:
            best, stale = att, 0
        else:
            stale += 1
        if best.reward >= target_reward or stale >= patience:
            break

    assert best is not None
    return best, history


def demo() -> None:
    """Offline self-check of the loop control flow — no API key, no Verilator.

    Stub model emits broken RTL first, then 'golden'; stub grader scores them.
    Asserts the loop climbs to a correct design and stops at it."""
    from cologic.schema import Port

    task = Task(task_id="t", spec="a AND b", top_module="m",
                interface=[Port("a", "input"), Port("b", "input"), Port("y", "output")],
                reference_rtl="module m(input a,b,output y); assign y=a&b; endmodule")

    def stub_model(msgs: list[dict]) -> str:
        # revision turn present (assistant echoed back) => return the good answer
        revising = any(m["role"] == "assistant" for m in msgs)
        return "module m(...); GOOD endmodule" if revising else "module m(...); BROKEN"

    def stub_grader(completion: str, _task: Task) -> GradeResult:
        if "GOOD" in completion:
            return GradeResult(1.0, {"stage": "graded", "compiled": True, "passed": 4, "total": 4})
        return GradeResult(0.05, {"stage": "compile_error", "compiled": False,
                                  "passed": 0, "total": 0, "log": "syntax error"})

    best, history = improve(task, forge_model=stub_model, grader=stub_grader, max_iters=6)
    assert history[0].reward == 0.05, history[0]          # started broken
    assert best.reward == 1.0, best                       # improved to correct
    assert best.iteration == 1, best                      # on the first revision
    assert len(history) == 2, history                     # stopped once correct
    assert "mismatch" not in best.feedback                # output mapper read PASS
    print(f"demo ok: {len(history)} attempts, best reward {best.reward}")


if __name__ == "__main__":
    demo()
