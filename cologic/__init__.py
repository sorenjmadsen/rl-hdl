"""rl-hdl: an RLVR environment for Verilog/RTL generation graded by real silicon tooling.

The reward seam both tracks build against:

    grade(completion: str, task: Task) -> GradeResult(reward: float, info: dict)
"""

from cologic.schema import GradeResult, Port, Task
from cologic.verifier import grade

__all__ = ["Task", "Port", "GradeResult", "grade"]
