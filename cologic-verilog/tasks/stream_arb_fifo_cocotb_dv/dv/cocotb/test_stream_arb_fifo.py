
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


WIDTH = 8
DEPTH = 8


def _coverage_file() -> Path | None:
    raw = os.environ.get("STREAM_ARB_COVERAGE_FILE")
    return Path(raw) if raw else None


def mark_coverage(point: str) -> None:
    path = _coverage_file()
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, bool] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data[point] = True
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _as_int(value) -> int:
    return int(value)


async def reset_dut(dut) -> None:
    dut.reset_i.value = 1
    dut.valid0_i.value = 0
    dut.valid1_i.value = 0
    dut.yumi_i.value = 0
    dut.data0_i.value = 0
    dut.data1_i.value = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")
    assert _as_int(dut.valid_o.value) == 0
    assert _as_int(dut.count_o.value) == 0
    dut.reset_i.value = 0
    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")


@cocotb.test()
async def lane0_basic_test(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, unit="ns").start())
    await reset_dut(dut)

    dut.data0_i.value = 0x42
    dut.valid0_i.value = 1
    dut.valid1_i.value = 0
    dut.yumi_i.value = 0
    await Timer(1, unit="ns")
    assert _as_int(dut.ready0_o.value) == 1
    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")

    dut.valid0_i.value = 0
    assert _as_int(dut.valid_o.value) == 1
    assert _as_int(dut.data_o.value) == 0x42
    assert _as_int(dut.count_o.value) == 1

    dut.yumi_i.value = 1
    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")
    dut.yumi_i.value = 0
    assert _as_int(dut.count_o.value) == 0
