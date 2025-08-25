from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass
from typing import Callable, Optional, List, Tuple

import numpy as np


@dataclass
class WorkItem:
    priority: int
    seq: int
    waveform: np.ndarray
    sample_rate: int
    future: asyncio.Future
    enqueued_ts: float


class MicroBatchScheduler:
    """
    Micro-batching scheduler that aggregates items for a short window or up to max batch size,
    then invokes a batch run function. Intended to improve GPU utilization.
    """

    def __init__(
        self,
        *,
        maxsize: int,
        run_batch_fn: Callable[[List[np.ndarray], List[int]], List[str]],
        window_ms: float = 15.0,
        max_batch: int = 4,
    ):
        # Priority queue of work items (earliest enqueued first)
        # Store entries as (priority_key, seq, WorkItem)
        self.queue: "asyncio.PriorityQueue[Tuple[float, int, WorkItem]]" = asyncio.PriorityQueue(maxsize=maxsize)
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

    def submit(self, waveform: np.ndarray, sample_rate: int) -> asyncio.Future:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        item = WorkItem(
            priority=0,
            seq=next(self._seq),
            waveform=waveform,
            sample_rate=sample_rate,
            future=fut,
            enqueued_ts=time.time(),
        )
        # Earlier enqueue time -> smaller key -> higher priority
        prio_key = time.monotonic()
        # Use seq for stable tiebreaking
        self.queue.put_nowait((prio_key, item.seq, item))
        return fut

    def qsize(self) -> int:
        return self.queue.qsize()

    def maxsize(self) -> int:
        return self._maxsize

    async def _aggregator(self) -> None:
        while True:
            # block for the first item
            _prio, _seq, first = await self.queue.get()
            batch_items: List[WorkItem] = [first]

            # compute deadline
            deadline = time.monotonic() + (self._window_ms / 1000.0)
            while len(batch_items) < self._max_batch:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    prio_seq_item = await asyncio.wait_for(self.queue.get(), timeout)
                    _prio2, _seq2, nxt = prio_seq_item
                    batch_items.append(nxt)
                except asyncio.TimeoutError:
                    break

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
                queue_wait = 0.0  # not exact here; main server tracks
                if not wi.future.done():
                    wi.future.set_result((text, inference_dt, queue_wait))
                self.queue.task_done()
