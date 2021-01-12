"""
DM Queue Module.

Pylint's too few public methods is disabled here since we're not really
using DMLock for a purpose that something else might satisfy better,
such as dataclasses.

The implementation here can be hard to follow, and while there is a
variable inside asyncio.Lock that would help with this (_waiters), that
is a private attribute, and hence we have to make do with an additional
waiting room.

Also this file has more comments than actual code so that's fun.
"""

from asyncio import Lock
from typing import Dict, Callable, Any


# pylint: disable=too-few-public-methods
class DMLock:
    """
    DM Lock Manager.

    To prevent users from receiving multiple DMs at the same time, this
    module queues DM role management tasks per user.
    """

    __slots__ = ["waiting", "executing", "waiting_lock", "executing_lock"]

    def __init__(self) -> None:
        """Initializer for the DMLock class."""
        self.waiting: Dict[int, Lock] = {}
        self.executing: Dict[int, Lock] = {}
        self.waiting_lock = Lock()
        self.executing_lock = Lock()

    async def queue_call(
            self,
            call: Callable,
            key: int,
            *args,
            **kwargs
    ) -> Any:
        """
        Enqueue an async call for a member.

        :param call: Callable to call once the key lock is free
        :param key: Key of FIFO queue
        """
        returner = None

        # Obtain the waiting room lock
        async with self.waiting_lock:
            key_wait_lock = self.waiting.setdefault(key, Lock())

        # Enter the waiting room.
        # If someone else is in the waiting room, that means there's 1
        # or 2 tasks in front of us, and we need to wait for them all
        # to at least start executing so that we can enter the waiting
        # room.
        await key_wait_lock.acquire()
        self_waiting = True
        try:
            # Obtain the execution lock
            async with self.executing_lock:
                key_execute_lock = self.executing.setdefault(key, Lock())

            # Start execution, after previous call is done.
            # At this point, the waiting room lock is held by us and is
            # locked, but the execusion lock might still be held by
            # someone else.
            async with key_execute_lock:
                # First thing to do during execusion is to release the
                # waiting room for the next person in line so that they
                # can wait for us to be done.
                key_wait_lock.release()
                self_waiting = False
                returner = await call(*args, **kwargs)

        finally:
            # No matter what happens, we want to exit the waiting room
            # ourselves. We check if the waiting room is locked, and if
            # we ourselves are waiting (which we keep track of using
            # the self_waiting bool). If we are not the ones waiting
            # and someone else is in the waiting room, we shouldn't
            # disturb them.
            if key_wait_lock.locked() and self_waiting:
                key_wait_lock.release()

            # Now we check if the waiting room is empty or full,
            # regardless of who it is inside. We know that we aren't
            # the ones inside, so it has to be someone else if it is
            # locked.
            removed_waiting = False
            async with self.waiting_lock:
                if not key_wait_lock.locked():
                    # If it is empty, that means we can safely remove
                    # the waiting room, because no one is using it.
                    await self.waiting.pop(key, None)
                    removed_waiting = True

            # If we removed the waiting room, there would only be the
            # execution lock left now. We were just in it but we've
            # since left - there can only be a maximum
            if removed_waiting:
                async with self.executing_lock:
                    if not key_execute_lock.locked():
                        # If the execution lock is empty, then we are
                        # pretty sure that we can remove it. We've
                        # already removed the waiting room, and since
                        # we can't be stuck between the waiting room
                        # and the execution (without being in either),
                        # that edge case is impossible.
                        await self.executing.pop(key, None)

        return returner
