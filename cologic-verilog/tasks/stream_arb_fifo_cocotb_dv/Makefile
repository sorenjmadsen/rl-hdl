SHELL := /bin/bash

PYTHON ?= python3
RTL ?= rtl/stream_arb_fifo.sv
FILELIST ?= filelist.f
TESTS ?= dv/cocotb/test_stream_arb_fifo.py
BUILD_DIR ?= build/cocotb
REPORT_DIR ?= reports
COVERAGE_FILE ?= $(REPORT_DIR)/coverage.json
BSG_INC := vendor/basejump_stl/bsg_misc

.PHONY: test clean

test:
	mkdir -p $(BUILD_DIR) $(REPORT_DIR)
	$(PYTHON) scripts/run_cocotb.py \
		--rtl $(RTL) \
		--tests $(TESTS) \
		--filelist $(FILELIST) \
		--include-dir $(BSG_INC) \
		--build-dir $(BUILD_DIR) \
		--coverage-file $(COVERAGE_FILE) \
		--results-xml $(REPORT_DIR)/results.xml

clean:
	rm -rf build reports
