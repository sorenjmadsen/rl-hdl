import json

from cologic.rft import DEFAULT_RFT_TASK_IDS, rows_for_task_ids, write_jsonl
from cologic.tasks import BY_ID


def test_rft_rows_preserve_task_metadata():
    rows = rows_for_task_ids(["mux2", "vg_npu_int34_to_fp32"])

    assert [r["input_metadata"]["row_id"] for r in rows] == ["mux2", "vg_npu_int34_to_fp32"]
    assert rows[0]["input_metadata"]["dataset_info"]["task_id"] == "mux2"
    assert rows[1]["input_metadata"]["dataset_info"]["top_module"] == "npu_int34_to_fp32"
    assert rows[0]["messages"][0]["role"] == "system"
    assert rows[0]["messages"][-1]["role"] == "user"


def test_rft_smoke_rows_can_embed_golden_reference(tmp_path):
    rows = rows_for_task_ids(["mux2"], include_golden=True)
    out = write_jsonl(rows, tmp_path / "smoke.jsonl")

    [line] = out.read_text(encoding="utf-8").splitlines()
    row = json.loads(line)
    assert row["messages"][-1]["role"] == "assistant"
    assert BY_ID["mux2"].reference_rtl in row["messages"][-1]["content"]


def test_committed_rft_dataset_matches_default_task_ids():
    rows = [
        json.loads(line)
        for line in open("fireworks_rft/dataset.jsonl", encoding="utf-8")
        if line.strip()
    ]

    assert [r["input_metadata"]["row_id"] for r in rows] == DEFAULT_RFT_TASK_IDS
    assert all(r["messages"][-1]["role"] == "user" for r in rows)
