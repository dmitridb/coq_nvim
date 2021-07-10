from asyncio import Handle, get_running_loop
from itertools import chain
from typing import MutableSet, Optional, Sequence

from pynvim.api.nvim import Nvim
from pynvim_pp.api import buf_filetype, cur_buf, list_bufs
from pynvim_pp.lib import async_call, go
from std2.pickle import new_decoder

from ...registry import atomic, autocmd, rpc
from ...snippets.artifacts import SNIPPETS
from ...snippets.types import ParsedSnippet
from ...treesitter.request import async_request
from ..rt_types import Stack
from ..state import state

_SEEN: MutableSet[str] = set()

_DECODER = new_decoder(Sequence[ParsedSnippet])


@rpc(blocking=True)
def _ft_changed(nvim: Nvim, stack: Stack) -> None:
    buf = cur_buf(nvim)
    ft = buf_filetype(nvim, buf=buf)

    stack.bdb.ft_update(buf.number, filetype=ft)

    if ft not in _SEEN:
        _SEEN.add(ft)
        mappings = {
            f: _DECODER(SNIPPETS.snippets.get(f, ()))
            for f in chain(SNIPPETS.extends.get(ft, {}).keys(), (ft,))
        }
        stack.sdb.populate(mappings)


autocmd("FileType") << f"lua {_ft_changed.name}()"
atomic.exec_lua(f"{_ft_changed.name}()", ())


@rpc(blocking=True)
def _insert_enter(nvim: Nvim, stack: Stack) -> None:
    heavy_bufs = state().heavy_bufs
    buf = cur_buf(nvim)
    if not buf.number in heavy_bufs:

        async def cont() -> None:
            payloads = await async_request(nvim)
            await stack.tdb.new_nodes(
                {payload["text"]: payload["kind"] for payload in payloads}
            )

        go(nvim, aw=cont())


autocmd("InsertEnter") << f"lua {_insert_enter.name}()"

_HANDLE: Optional[Handle] = None


@rpc(blocking=True)
def _when_idle(nvim: Nvim, stack: Stack) -> None:
    global _HANDLE
    if _HANDLE:
        _HANDLE.cancel()

    def cont() -> None:
        bufs = list_bufs(nvim, listed=False)
        stack.bdb.vacuum({buf.number for buf in bufs})
        _insert_enter(nvim, stack=stack)
        stack.supervisor.notify_idle()

    get_running_loop().call_later(
        stack.settings.idle_time,
        lambda: go(nvim, aw=async_call(nvim, cont)),
    )


autocmd("CursorHold", "CursorHoldI") << f"lua {_when_idle.name}()"

