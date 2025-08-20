from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


@dataclass
class WorkItem:
    priority: int
    seq: int
    waveform: np.ndarray
    sample_rate: int
    future: asyncio.Future
    enqueued_ts: float


class Scheduler:
    def __init__(self, num_lanes: int, maxsize: int, run_fn: Callable[[np.ndarray, int], str]):
        self.num_lanes = num_lanes
        # store (priority, seq, WorkItem) so heap ordering is well-defined
        self.queue: "asyncio.PriorityQueue[tuple[int, int, WorkItem]]" = asyncio.PriorityQueue(maxsize=maxsize)
        self._run_fn = run_fn
        self._seq = itertools.count()
        self._lane_tasks: list[asyncio.Task] = []

    def start(self) -> None:
        for lane_id in range(self.num_lanes):
            task = asyncio.create_task(self._lane_worker(lane_id), name=f"lane-{lane_id}")
            self._lane_tasks.append(task)

    async def stop(self) -> None:
        for task in self._lane_tasks:
            task.cancel()
        await asyncio.gather(*self._lane_tasks, return_exceptions=True)

    def submit(self, waveform: np.ndarray, sample_rate: int, priority: int) -> asyncio.Future:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        item = WorkItem(
            priority=priority,
            seq=next(self._seq),
            waveform=waveform,
            sample_rate=sample_rate,
            future=fut,
            enqueued_ts=time.time(),
        )
        self.queue.put_nowait((item.priority, item.seq, item))
        return fut

    async def _lane_worker(self, lane_id: int) -> None:
        while True:
            _priority, _seq, item = await self.queue.get()
            try:
                start_ts = time.time()
                result_text = self._run_fn(item.waveform, item.sample_rate)
                inference_dt = time.time() - start_ts
                queue_wait = start_ts - item.enqueued_ts
                item.future.set_result((result_text, inference_dt, queue_wait))
            except Exception as e:
                if not item.future.done():
                    item.future.set_exception(e)
            finally:
                self.queue.task_done()


def bucket_priority(num_samples: int, sr: int = 16000) -> int:
    seconds = num_samples / max(1, sr)
    if seconds <= 10:
        return 0
    if seconds <= 30:
        return 1
    if seconds <= 60:
        return 2
    if seconds <= 180:
        return 3
    return 4
