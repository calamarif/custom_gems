from itertools import chain

from ..custom_typing import OrderedDictType


def add_ordereddicts(*odicts: OrderedDictType) -> OrderedDictType:
    items = [odict.items() for odict in odicts]
    return OrderedDictType(chain(*items))
