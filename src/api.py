import asyncio
import dataclasses
import logging
import uuid
from contextlib import asynccontextmanager
from itertools import count
from typing import List

from fastapi import FastAPI
from pydantic.dataclasses import dataclass

from cocktail_24.cocktail.cocktail_api import (
    CocktailApi,
    CocktailBarStatePersistence,
    SqliteCocktailBarStatePersistence,
)
from cocktail_24.cocktail.cocktail_bookkeeping import OrderId, Order, SlotStatus
from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe, RecipeId
from cocktail_24.cocktail_management import CocktailManagement, FakeFulfillmentSystem
from cocktail_24.cocktail_robot_interface import CocktailRobotState
from cocktail_24.cocktail_runtime import async_cocktail_runtime
from cocktail_24.cocktail_system import CocktailSystemStatus
from cocktail_24.pump_interface.pump_interface import PumpStatus
from configure import configure_system, configure_management, configure_system_config

FAKE_SYSTEM = True

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclasses.dataclass
class Cocktail:
    persistence: CocktailBarStatePersistence
    api: CocktailApi
    management: CocktailManagement


def get_management(persistence, fake_system: bool = False):
    system = configure_system()
    system_config = configure_system_config()
    if fake_system:
        system = FakeFulfillmentSystem()
    return configure_management(system, system_config, persistence=persistence)


# management needs to be driven
async def update_fake_management():
    assert FAKE_SYSTEM
    while True:
        COCKTAIL.management.check_update()
        await asyncio.sleep(0.0001)


def get_cocktail(fake_system: bool = False):
    # persistence = InMemoryCocktailBarStatePersistence(
    #     initial_state=configure_initial_state()
    # )
    persistence = SqliteCocktailBarStatePersistence("/tmp/cocktails_2.db")
    cock_api = CocktailApi(state_persistence=persistence)
    return Cocktail(
        persistence=persistence,
        api=cock_api,
        management=get_management(persistence, fake_system=fake_system),
    )


def gen_run_robo():

    for system_epoch in count():
        logging.warning("system epoch started:%s", system_epoch)
        system = COCKTAIL.management.get_system()
        management = COCKTAIL.management
        yield from system.gen_initialize(connect=system_epoch == 0)

        try:
            execution = system.gen_run()
            effect = next(execution)
            while True:
                send = yield effect
                effect = execution.send(send)

                management.check_update()
        except StopIteration:
            logging.warning("system epoch ended:%s", system_epoch)
            management.abort()
            COCKTAIL.management = get_management(COCKTAIL.persistence)


COCKTAIL = get_cocktail(fake_system=FAKE_SYSTEM)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runtime_ok

    # TODO move this into runtime
    async def log_exceptions(awaitable):
        global runtime_ok
        try:
            return await awaitable
        except Exception as e:
            logging.exception(e)
            runtime_ok = False

    if not FAKE_SYSTEM:
        rt = async_cocktail_runtime(cocktail_gen=gen_run_robo())
        t = asyncio.create_task(log_exceptions(rt))
        runtime_ok = True
        logging.warning("started runtime task")
    else:
        t = asyncio.create_task(log_exceptions(update_fake_management()))
        logging.warning("not starting runtime. faking!")
    yield
    t.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/order/{order_id}")
async def get_order_details(order_id: OrderId) -> Order:
    cs = COCKTAIL.persistence.get_current_state()
    return cs.orders[order_id]


@app.get("/orders")
async def get_orders() -> List[OrderId]:
    cs = COCKTAIL.persistence.get_current_state()
    return [order.order_id for order in cs.orders.values()]


@app.get("/slots")
async def get_slots() -> List[SlotStatus]:
    cs = COCKTAIL.persistence.get_current_state()
    return [*cs.slots]


@app.post("/slot_refill")
async def slot_refill(slot: SlotStatus):
    COCKTAIL.api.refill_slot(slot)


@app.get("/recipe/{recipe_id}")
async def get_recipe_details(recipe_id: RecipeId) -> CocktailRecipe:
    cs = COCKTAIL.persistence.get_current_state()
    return cs.recipes[recipe_id]


@app.get("/recipes")
async def get_recipes() -> List[RecipeId]:
    cs = COCKTAIL.persistence.get_current_state()
    return [*cs.recipes.keys()]


@app.post("/create_recipe")
async def create_recipe(recipe: CocktailRecipe):
    COCKTAIL.api.create_recipe(recipe)


@app.post("/place_order")
async def place_order(recipe_id: RecipeId):
    COCKTAIL.api.place_order(recipe_id)


@app.post("/enqueue_order")
async def enqueue_order(order_id: OrderId):
    COCKTAIL.api.enqueue_order(order_id)


@app.post("/cancel_order")
async def cancel_order(order_id: OrderId):
    COCKTAIL.api.cancel_order(order_id)


@dataclass
class PlanProgress:
    plan_id: uuid.UUID | None
    queued_step_pos: int
    finished_step_pos: int


@dataclass
class CocktailSystemState:
    status: CocktailSystemStatus
    plan_progress: PlanProgress | None
    robot_state: CocktailRobotState
    pump_status: PumpStatus


@app.get("/system/status")
async def get_system_status() -> CocktailSystemState:
    state = COCKTAIL.management.get_system().get_state()
    return CocktailSystemState(
        plan_progress=(
            PlanProgress(
                plan_id=(state.plan_progress.plan.plan_id),
                queued_step_pos=state.plan_progress.queued_step_pos,
                finished_step_pos=state.plan_progress.finished_step_pos,
            )
            if state.plan_progress is not None
            else None
        ),
        status=state.status,
        pump_status=state.pump_status,
        robot_state=state.robot_state,
    )


@app.post("/system/abort")
async def get_abort():
    COCKTAIL.management.get_system()._robot_.signal_stop()


# @app.get("/system/runtime_status")
# async def get_runtime_status():
#     return {"runtime_ok": runtime_ok}
