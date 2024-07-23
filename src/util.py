import uuid
from itertools import product

from pydantic import RootModel

from cocktail_24.cocktail.cocktail_bookkeeping import OrderFulfilledEvent, OrderId
from cocktail_24.cocktail_robo import CocktailPosition, ALLOWED_COCKTAIL_MOVES


def pydantic_dataclass_to_json(el):
    return RootModel[el.__class__](el).model_dump_json(indent=4)


def pydantic_dataclass_from_json(class_, json_data: str):
    return RootModel[class_].model_validate_json(json_data)


def check_pydantic_json_roundtrip(event):
    encoded = pydantic_dataclass_to_json(event)
    decoded = pydantic_dataclass_from_json(event.__class__, encoded)
    print(f"{event} vs. {decoded}")
    assert decoded == RootModel[event.__class__](event)


def bfs_preds(edges, start):
    frontier = {start}
    preds = {start: None}
    while frontier:
        nf = set()
        for el in frontier:
            for v1, v2 in edges:
                if v1 == el:
                    if v2 not in preds:
                        preds[v2] = el
                        nf.add(v2)
        frontier = nf
    return preds


def get_shortest_path(edges, start, target):
    preds = bfs_preds(edges, start)
    path = []
    curr_pos = target
    while curr_pos != start:
        path.append(curr_pos)
        curr_pos = preds[curr_pos]
    return path[::-1]


def test_bfs():
    for p1, p2 in product(range(1, 7), repeat=2):
        p1 = CocktailPosition(p1)
        p2 = CocktailPosition(p2)
        print(f"move {p1} to {p2}")
        for el in get_shortest_path(ALLOWED_COCKTAIL_MOVES, p1, p2):
            print(el)
        print("----")


def test_pydantic_dataclass_to_json():
    event = OrderFulfilledEvent(order_id=OrderId(uuid.uuid4()))
