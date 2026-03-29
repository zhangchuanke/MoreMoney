# Lazy imports to avoid circular import with stdlib 'signal' module
# The project package 'signal' shadows stdlib signal; defer heavy imports.

def __getattr__(name):
    if name == 'news_filter_node':
        from .news_filter_node import news_filter_node
        return news_filter_node
    if name == 'NewsItem':
        from .news_filter import NewsItem
        return NewsItem
    if name == 'FilteredNewsResult':
        from .news_filter import FilteredNewsResult
        return FilteredNewsResult
    if name == 'OFFICIAL_DISCLOSURE_SOURCES':
        from .news_filter import OFFICIAL_DISCLOSURE_SOURCES
        return OFFICIAL_DISCLOSURE_SOURCES
    if name == 'SOURCE_CREDIBILITY':
        from .news_filter import SOURCE_CREDIBILITY
        return SOURCE_CREDIBILITY
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

__all__ = [
    'NewsItem',
    'FilteredNewsResult',
    'OFFICIAL_DISCLOSURE_SOURCES',
    'SOURCE_CREDIBILITY',
    'news_filter_node',
]
