# Bad Apple on Bisare

## Parameters

- `FPS`: number of frames extracted by `ffmpeg`
- `SLEEP`: delay between frames in the generated ASM program

`FPS` only affects frame extraction.

`SLEEP` only affects the wait loop inserted between displayed frames.

## Usage

Generate frames:

```bash
make frames FPS=2
```

Run:

```bash
make run FPS=2
```

The best quality avalaible now:

```bash
make framesQ2 FPS=5 fastrun 
```