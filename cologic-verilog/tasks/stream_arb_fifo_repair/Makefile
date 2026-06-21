SHELL := /bin/bash

VERILATOR ?= verilator
YOSYS ?= yosys
PYTHON ?= python3
AR ?= /usr/bin/ar
RANLIB ?= /usr/bin/ranlib
export PATH := /opt/homebrew/bin:$(HOME)/utils/oss-cad-suite/bin:/usr/bin:/bin:/usr/sbin:/sbin:$(PATH)
unexport LC_ALL
export LANG := en_US.UTF-8
export LC_CTYPE := en_US.UTF-8
export AR
export RANLIB

RTL := rtl/stream_arb_fifo.sv
VISIBLE_TB := dv/visible_tb.sv
BUILD_DIR := build
REPORT_DIR := reports

.PHONY: test synth lint clean

test:
	mkdir -p $(BUILD_DIR)
	$(VERILATOR) --binary --timing -Wno-fatal --top-module stream_arb_fifo_visible_tb \
		-Mdir $(BUILD_DIR)/obj_visible -o stream_arb_fifo_visible \
		$(RTL) $(VISIBLE_TB)
	$(BUILD_DIR)/obj_visible/stream_arb_fifo_visible

synth:
	mkdir -p $(REPORT_DIR)
	$(YOSYS) -q -s synth/synth.ys
	$(PYTHON) scripts/check_latches.py $(REPORT_DIR)/proc.json

lint:
	$(VERILATOR) --lint-only -Wall -Wno-fatal --top-module stream_arb_fifo $(RTL)

clean:
	rm -rf $(BUILD_DIR) $(REPORT_DIR)
