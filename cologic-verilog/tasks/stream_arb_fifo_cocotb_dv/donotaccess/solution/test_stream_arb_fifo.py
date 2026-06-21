
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


WIDTH = 8
DEPTH = 8
COVERAGE_POINTS = [
    "reset",
    "lane0_basic",
    "lane1_only",
    "round_robin_contention",
    "full_pop_push",
    "reset_restarts_arbitration",
    "wraparound_order",
]


def _coverage_file() -> Path | None:
    raw = os.environ.get("STREAM_ARB_COVERAGE_FILE")
    return Path(raw) if raw else None


def mark_coverage(point: str) -> None:
    if point not in COVERAGE_POINTS:
        raise AssertionError(f"unknown coverage point {point!r}")
    path = _coverage_file()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, bool] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data[point] = True
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def as_int(value) -> int:
    return int(value)


class FifoModel:
    def __init__(self) -> None:
        self.queue: list[int] = []
        self.rr_next = 0

    def expected(self, v0: int, d0: int, v1: int, d1: int, y: int):
        valid = len(self.queue) != 0
        pop = bool(y and valid)
        can_accept = len(self.queue) < DEPTH or pop
        ready0 = 0
        ready1 = 0
        selected = 0
        if can_accept:
            if v0 and v1:
                ready0 = 0 if self.rr_next else 1
                ready1 = 1 if self.rr_next else 0
                selected = self.rr_next
            elif v0:
                ready0 = 1
                selected = 0
            elif v1:
                ready1 = 1
                selected = 1
        push0 = bool(ready0 and v0)
        push1 = bool(ready1 and v1)
        return valid, pop, ready0, ready1, selected, push0, push1

    def apply(self, pop: bool, push0: bool, d0: int, push1: bool, d1: int) -> None:
        if pop:
            assert self.queue
            self.queue.pop(0)
        if push0:
            self.queue.append(d0 & 0xFF)
            self.rr_next = 1
        elif push1:
            self.queue.append(d1 & 0xFF)
            self.rr_next = 0
        assert 0 <= len(self.queue) <= DEPTH


async def reset_dut(dut, model: FifoModel) -> None:
    dut.reset_i.value = 1
    dut.valid0_i.value = 0
    dut.valid1_i.value = 0
    dut.yumi_i.value = 0
    dut.data0_i.value = 0
    dut.data1_i.value = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")
    assert as_int(dut.valid_o.value) == 0, "reset should clear valid_o"
    assert as_int(dut.count_o.value) == 0, "reset should clear count_o"
    dut.reset_i.value = 0
    model.queue.clear()
    model.rr_next = 0
    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")
    mark_coverage("reset")


async def drive_cycle(
    dut,
    model: FifoModel,
    *,
    v0: int = 0,
    d0: int = 0,
    v1: int = 0,
    d1: int = 0,
    y: int = 0,
    label: str = "cycle",
) -> None:
    dut.valid0_i.value = v0
    dut.data0_i.value = d0
    dut.valid1_i.value = v1
    dut.data1_i.value = d1
    dut.yumi_i.value = y
    await Timer(1, unit="ns")

    valid, pop, ready0, ready1, selected, push0, push1 = model.expected(v0, d0, v1, d1, y)
    assert as_int(dut.valid_o.value) == int(valid), f"{label}: valid_o mismatch"
    assert as_int(dut.ready0_o.value) == ready0, f"{label}: ready0_o mismatch"
    assert as_int(dut.ready1_o.value) == ready1, f"{label}: ready1_o mismatch"
    assert as_int(dut.count_o.value) == len(model.queue), f"{label}: count_o mismatch"
    assert as_int(dut.selected_lane_o.value) == selected, f"{label}: selected_lane_o mismatch"
    if valid:
        assert as_int(dut.data_o.value) == model.queue[0], f"{label}: data_o mismatch"

    await RisingEdge(dut.clk_i)
    model.apply(pop, push0, d0, push1, d1)
    await Timer(1, unit="ns")
    assert as_int(dut.count_o.value) == len(model.queue), f"{label}: post-count mismatch"


@cocotb.test()
async def comprehensive_stream_fifo_verification(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, unit="ns").start())
    model = FifoModel()
    await reset_dut(dut, model)

    await drive_cycle(dut, model, v0=1, d0=0x42, label="lane0_basic_push")
    await drive_cycle(dut, model, y=1, label="lane0_basic_pop")
    mark_coverage("lane0_basic")

    for value in [0x81, 0x82, 0x83]:
        await drive_cycle(dut, model, v1=1, d1=value, label="lane1_only_push")
    for _ in range(3):
        await drive_cycle(dut, model, y=1, label="lane1_only_pop")
    mark_coverage("lane1_only")

    for i in range(6):
        await drive_cycle(
            dut,
            model,
            v0=1,
            d0=0x10 + i,
            v1=1,
            d1=0xA0 + i,
            label=f"round_robin_push_{i}",
        )
    for i in range(6):
        await drive_cycle(dut, model, y=1, label=f"round_robin_pop_{i}")
    mark_coverage("round_robin_contention")

    for i in range(DEPTH):
        await drive_cycle(dut, model, v0=1, d0=0x30 + i, label=f"fill_{i}")
    await drive_cycle(dut, model, v1=1, d1=0xEE, y=1, label="full_pop_push")
    for i in range(DEPTH):
        await drive_cycle(dut, model, y=1, label=f"drain_after_full_{i}")
    mark_coverage("full_pop_push")

    await drive_cycle(dut, model, v0=1, d0=0x55, v1=1, d1=0xAA, label="pre_reset_contention")
    await reset_dut(dut, model)
    await drive_cycle(dut, model, v0=1, d0=0x66, v1=1, d1=0xBB, label="post_reset_contention")
    await drive_cycle(dut, model, y=1, label="post_reset_pop")
    mark_coverage("reset_restarts_arbitration")

    for i in range(DEPTH):
        await drive_cycle(dut, model, v0=1, d0=0xC0 + i, label=f"wrap_fill_{i}")
    for i in range(5):
        await drive_cycle(dut, model, y=1, label=f"wrap_partial_drain_{i}")
    for i in range(5):
        await drive_cycle(dut, model, v1=1, d1=0xD0 + i, label=f"wrap_refill_{i}")
    while model.queue:
        await drive_cycle(dut, model, y=1, label="wrap_final_drain")
    mark_coverage("wraparound_order")
