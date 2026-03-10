from PIL import Image
import sys
import os

# 50000 is around 1 sec on the vanilla interpreter
sleep = int(sys.argv[1]) if len(sys.argv) > 1 else 50000

frames = os.listdir("badapple-frames/out")
frames.sort()

def pixel_to_bit(pixel):
    r, g, b = pixel[:3]
    return 1 if (r + g + b) >= 3 * 128 else 0

def emit_plot(f, coord, bit, new):
    f.write(f"    let r1 0x{coord:08x}\n")
    if new:
        f.write(f"    let r2 {bit}\n")
    f.write("    call plot\n")

prev_bits = None

with open("out.asm", "w") as f:
    f.write("let r0 0x00fffffc\n")
    f.write("copy sp r0\n")
    f.write("jump main\n")
    f.write("\n")

    # wait()
    f.write("wait:\n")
    f.write("    let r2 0\n")
    f.write(f"    let r3 {sleep}\n")
    f.write("wait_loop:\n")
    f.write("    skip 1 iflt r2 r3\n")
    f.write("    jump wait_end\n")
    f.write("    add r2 r2 1\n")
    f.write("    jump wait_loop\n")
    f.write("wait_end:\n")
    f.write("    ret\n")
    f.write("\n")

    # plot(offset=r1, bit=r2)
    # r0 = framebuffer base
    # r1 = pixel offset in bytes
    # r2 = 0 or 1
    # clobbers r3
    f.write("plot:\n")
    f.write("    skip 1 ifeq r2 0\n")
    f.write("    jump plot_white\n")
    f.write("    let r3 0x00000000\n")
    f.write("    jump plot_draw\n")
    f.write("plot_white:\n")
    f.write("    let r3 0x00ffffff\n")

    f.write("plot_draw:\n")
    f.write("    copy r4 r1\n")

    # ligne 0
    f.write("    copy r5 r4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")

    # ligne 1
    f.write("    add r4 r4 2560\n")
    f.write("    copy r5 r4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")

    # ligne 2
    f.write("    add r4 r4 2560\n")
    f.write("    copy r5 r4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")

    # ligne 3
    f.write("    add r4 r4 2560\n")
    f.write("    copy r5 r4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")

    # ligne 4
    f.write("    add r4 r4 2560\n")
    f.write("    copy r5 r4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")
    f.write("    add r5 r5 4\n")
    f.write("    store [r0 + r5] r3\n")

    f.write("    ret\n\n")

    f.write("main:\n")
    f.write("    let r0 0x01000000\n")

    for frame in frames:
        img = Image.open(f"badapple-frames/out/{frame}")
        pixels = list(img.getdata())
        bits = [pixel_to_bit(p) for p in pixels]

        old_bit = -1
        for y in range(img.height):
            for x in range(img.width):
                idx = x + y * img.width
                bit = bits[idx]

                if prev_bits is not None and bit == prev_bits[idx]:
                    continue
                
                new = old_bit == -1 or old_bit != bit
                old_bit = bit
                coord = 5 * 4 * (x + y * 640)
                emit_plot(f, coord, bit, new)

        prev_bits = bits
        f.write("    call wait\n")

    f.write("    halt\n")