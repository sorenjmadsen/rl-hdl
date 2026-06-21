"""Linear-programming optimizer for chip resource allocation (OR-Tools GLOP).

Honest scope (the skill is right): LP optimizes a LINEAR objective over LINEAR
constraints. It does NOT generate or edit RTL — that stays the RL loop's job.
Use it exactly the way Modal uses GLOP for GPU fleets (see their LP blog): given
linear power/area/throughput cost models for the building blocks, pick how many
of each to allocate to hit a compute target at minimum power. The output is a
design *target* (e.g. MAC-unit count, buffer depth) you can feed into the
agent's prompt as the objective to hit.

ponytail: GLOP solves the continuous relaxation; hardware unit counts are
integers. Round the allocation and re-check feasibility, or switch the solver to
OR-Tools CP-SAT if integrality matters. Linear cost models are an approximation;
swap in synthesized power/area numbers once you have them.
"""
from dataclasses import dataclass


@dataclass
class Resource:
    name: str
    power: float          # power per unit (mW, lower better)
    area: float           # area per unit (um^2)
    throughput: float     # useful compute per unit (MACs/cycle)
    max_units: float = 1e9


def minimize_power(resources, target_throughput, area_budget):
    """Minimize total power s.t. throughput >= target and area <= budget.

    Returns {"allocation": {name: units}, "power_mw": float, "area": float},
    or None if the constraints are infeasible.
    """
    from ortools.linear_solver import pywraplp

    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("GLOP solver unavailable (install ortools)")

    x = {r.name: solver.NumVar(0.0, r.max_units, r.name) for r in resources}
    solver.Add(sum(r.throughput * x[r.name] for r in resources) >= target_throughput)
    solver.Add(sum(r.area * x[r.name] for r in resources) <= area_budget)
    solver.Minimize(sum(r.power * x[r.name] for r in resources))

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return None

    alloc = {name: var.solution_value() for name, var in x.items()}
    return {
        "allocation": alloc,
        "power_mw": round(solver.Objective().Value(), 4),
        "area": round(sum(r.area * alloc[r.name] for r in resources), 4),
    }


if __name__ == "__main__":
    # self-check: a cheap-slow PE vs a power-hungry-fast PE. To hit 64 MACs/cycle
    # under a generous area budget, GLOP should lean on the most power-efficient
    # throughput (slow PE: 0.5 mW per MAC/cyc vs fast PE: 0.8 mW per MAC/cyc).
    res = [
        Resource("pe_slow", power=1.0, area=2.0, throughput=2.0),   # 0.5 mW / (MAC/cyc)
        Resource("pe_fast", power=4.0, area=3.0, throughput=5.0),   # 0.8 mW / (MAC/cyc)
    ]
    sol = minimize_power(res, target_throughput=64.0, area_budget=1000.0)
    assert sol is not None, "should be feasible"
    # all-slow is cheapest per MAC: 32 slow PEs -> 64 throughput, 32 mW
    assert abs(sol["power_mw"] - 32.0) < 1e-6, sol
    assert sol["allocation"]["pe_fast"] < 1e-6, sol
    # tight area budget (< 64, all-slow's footprint) forces area-denser fast PEs
    # in -> power must rise above the all-slow floor
    tight = minimize_power(res, target_throughput=64.0, area_budget=50.0)
    assert tight is not None and tight["power_mw"] > 32.0, tight
    # impossible target -> infeasible
    assert minimize_power(res, target_throughput=1e9, area_budget=10.0) is None
    print("optimize self-check OK:", sol)
