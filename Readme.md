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
make run SLEEP=10000
```