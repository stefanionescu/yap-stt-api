from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass
from typing import Callable, Optional, List, Tuple

import numpy as np


@dataclass
class WorkItem:
    priority: int  # 0 = highest (finals), 1 = partials
    seq: int
    waveform: np.ndarray
    sample_rate: int
    future: asyncio.Future
    enqueued_ts: float


class MicroBatchScheduler:
    """
    Priority micro-batching scheduler.
    - Single GPU lane (no concurrent model calls).
    - Finals (priority 0) always preempt partials (priority 1).
    - Batches items of the same priority only within a short window.
    """

    def __init__(
        self,
        *,
        maxsize: int,
        run_batch_fn: Callable[[List[np.ndarray], List[int]], List[str]],
        window_ms: float = 15.0,
        max_batch: int = 4,
    ):
        # Priority queue of work items.
        # Store entries as (priority, enqueue_monotonic, seq, WorkItem)
        self.queue: "asyncio.PriorityQueue[Tuple[int, float, int, WorkItem]]" = asyncio.PriorityQueue(maxsize=maxsize)
        self._maxsize = int(maxsize)
        self._seq = itertools.count()
        self._run_batch_fn = run_batch_fn
        self._window_ms = max(0.0, float(window_ms))
        self._max_batch = max(1, int(max_batch))
        self._aggregator_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._aggregator_task = asyncio.create_task(self._aggregator(), name="microbatch-aggregator")

    async def stop(self) -> None:
        if self._aggregator_task is not None:
            self._aggregator_task.cancel()
            await asyncio.gather(self._aggregator_task, return_exceptions=True)

    def submit(self, waveform: np.ndarray, sample_rate: int, *, priority: int = 1) -> asyncio.Future:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        item = WorkItem(
            priority=int(priority),
            seq=next(self._seq),
            waveform=waveform,
            sample_rate=sample_rate,
            future=fut,
            enqueued_ts=time.time(),
        )
        key = (item.priority, time.monotonic(), item.seq, item)
        self.queue.put_nowait(key)
        return fut

    def qsize(self) -> int:
        return self.queue.qsize()

    def maxsize(self) -> int:
        return self._maxsize

    async def _aggregator(self) -> None:
        while True:
            # Block for the first item
            prio, _, _, first = await self.queue.get()
            batch_items: List[WorkItem] = [first]

            # Collect more items of the SAME priority within window
            deadline = time.monotonic() + (self._window_ms / 1000.0)
            pushed_back: List[Tuple[int, float, int, WorkItem]] = []
            while len(batch_items) < self._max_batch:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    tup = await asyncio.wait_for(self.queue.get(), timeout)
                except asyncio.TimeoutError:
                    break
                p2, t2, s2, wi2 = tup
                if p2 == prio:
                    batch_items.append(wi2)
                else:
                    # Return mismatched priority to the queue and continue
                    pushed_back.append(tup)
                    # If the very next item is higher priority, preempt current batch
                    if len(batch_items) == 1 and p2 < prio:
                        # Push back the first and switch to higher priority
                        pushed_back.append((prio, time.monotonic(), first.seq, first))
                        batch_items.clear()
                        prio = p2
                        batch_items.append(wi2)
                        deadline = time.monotonic() + (self._window_ms / 1000.0)
            # Return mismatched priority items to the queue
            for tup in pushed_back:
                self.queue.put_nowait(tup)

            waveforms = [wi.waveform for wi in batch_items]
            sample_rates = [wi.sample_rate for wi in batch_items]
            try:
                # Offload the potentially heavy batch run off the event loop
                texts = await asyncio.to_thread(self._run_batch_fn, waveforms, sample_rates)
            except Exception as e:
                # set exception on all futures
                for wi in batch_items:
                    if not wi.future.done():
                        wi.future.set_exception(e)
                for _ in batch_items:
                    self.queue.task_done()
                continue

            # deliver results
            now = time.time()
            for wi, text in zip(batch_items, texts):
                inference_dt = max(0.0, now - wi.enqueued_ts)  # coarse estimate
                queue_wait = 0.0  # placeholder; main server tracks
                if not wi.future.done():
                    wi.future.set_result((text, inference_dt, queue_wait))
                self.queue.task_done()
