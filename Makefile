FRAMES_DIR=badapple-frames
OUT_DIR=$(FRAMES_DIR)/out
VIDEO=$(FRAMES_DIR)/badapple.mp4

ASM=out.asm
BIN=out.bin

FPS?=2
SLEEP?=10000

.PHONY: all frames asm run clean

all: frames run

frames:
	rm -rf $(OUT_DIR)
	mkdir -p $(OUT_DIR)
	ffmpeg -i $(VIDEO) -r $(FPS) -s 48x36 $(OUT_DIR)/output_%04d.png

asm:
	python3 main.py $(SLEEP)

run: asm
	python3 bisare/asm.py $(ASM)
	printf "run\n" | python3 bisare/sim.py $(BIN)

clean:
	rm -f $(ASM) $(BIN)
	rm -rf $(OUT_DIR)