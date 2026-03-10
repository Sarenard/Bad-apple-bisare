from PIL import Image
import sys
import os

# 50000 is around 1 sec on the vanilla interpreter
sleep = int(sys.argv[1]) if len(sys.argv) > 1 else 50000

frames = os.listdir("badapple-frames/out")
frames.sort()

prev_pixels = None

with open("out.asm", "w") as f:

    f.write("let r0 0x00fffffc\n")
    f.write("copy sp r0\n")
    f.write("jump main\n")
    f.write("\n")

    f.write("wait:\n")
    f.write("   let r2 0\n")
    f.write(f"   let r3 {sleep}\n")
    f.write("   wait_loop:\n")
    f.write("   skip 1 iflt r2 r3\n")
    f.write("   jump wait_end\n")
    f.write("   add r2 r2 1\n")
    f.write("   jump wait_loop\n")
    f.write("   wait_end:\n")
    f.write("   ret\n\n")

    f.write("main:\n")
    f.write("    let r0 0x01000000\n")

    for frame in frames:

        img = Image.open(f"badapple-frames/out/{frame}")
        pixels = list(img.getdata())

        for y in range(img.height):
            for x in range(img.width):

                idx = x + y * img.width
                pixel = pixels[idx]

                if prev_pixels is not None and pixel == prev_pixels[idx]:
                    continue

                r, g, b = pixel
                f.write(f"    let r1 0x00{r:02x}{g:02x}{b:02x}\n")

                coordinates = f"0x{(4 * (x + y * 640)):08x}"
                f.write(f"    let r2 {coordinates}\n")
                f.write("    store [r0 + r2] r1\n")

        prev_pixels = pixels

        f.write("    call wait\n")
        
    f.write("    halt\n")