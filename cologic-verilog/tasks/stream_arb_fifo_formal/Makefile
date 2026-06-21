PYTHON ?= python3
RTL ?= rtl/stream_arb_fifo.sv
PROPS ?= formal/stream_arb_fifo_props.sv

.PHONY: prove cover test clean

prove:
	$(PYTHON) scripts/run_formal.py --mode prove --rtl $(RTL) --props $(PROPS)

cover:
	$(PYTHON) scripts/run_formal.py --mode cover --rtl $(RTL) --props $(PROPS)

test: prove cover

clean:
	rm -rf build reports
