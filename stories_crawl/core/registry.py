from ..adapters.base import UnsupportedSourceError

NATIVE_ADAPTERS: list = []


def find_adapter_class(url: str):
    for cls in NATIVE_ADAPTERS:
        if cls.supports(url):
            return cls
    from ..adapters.lncrawl_bridge import LncrawlAdapter

    if LncrawlAdapter.supports(url):
        return LncrawlAdapter
    raise UnsupportedSourceError(f"Không có adapter nào hỗ trợ: {url}")
