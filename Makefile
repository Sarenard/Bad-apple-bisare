FRAMES_DIR=badapple-frames
OUT_DIR=$(FRAMES_DIR)/out
VIDEO=$(FRAMES_DIR)/badapple.mp4

ASM=out.asm
BIN=out.bin

FPS?=2

.PHONY: all framesQ1 framesQ2 asm run fastrun clean

framesQ1:
	rm -rf $(OUT_DIR)
	mkdir -p $(OUT_DIR)
	ffmpeg -i $(VIDEO) -r $(FPS) -s 48x36 $(OUT_DIR)/output_%04d.png

framesQ2:
	rm -rf $(OUT_DIR)
	mkdir -p $(OUT_DIR)
	ffmpeg -i $(VIDEO) -r $(FPS) -s 96x72 $(OUT_DIR)/output_%04d.png

asm:
	python3 main.py $(FPS)

run:
	python3 bisare/asm.py $(ASM)
	printf "run\n" | python3 bisare/sim.py $(BIN)

fastrun:
	cd bisare_sim_rs && cargo run --release -p asm ../$(ASM) ../$(BIN)
	cd bisare_sim_rs && cargo run --release -p simu ../$(BIN)

clean:
	rm -f $(ASM) $(BIN)
	rm -rf $(OUT_DIR)