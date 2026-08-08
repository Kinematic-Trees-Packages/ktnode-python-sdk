# ktnode Python SDK

High-level Python wrapper over `libkt_node`.

Planned public API:

```python
from ktnode import Context, Node, NextStep, run

class VideoNode(Node):
    def step(self, ctx: Context) -> NextStep:
        ctx.set("video", b"...")
        return NextStep.CONTINUE

run(package_path, runtime_path, VideoNode())
```
