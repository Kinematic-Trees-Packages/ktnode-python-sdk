# ktrobotics Python SDK

High-level Python wrapper over `lib_ktrobotics.so.1`.

Planned public API:

```python
from ktrobotics import Context, Node, NextStep, run

class VideoNode(Node):
    def step(self, ctx: Context) -> NextStep:
        ctx.set("video", b"...")
        return NextStep.CONTINUE

run(package_path, runtime_path, VideoNode())
```
