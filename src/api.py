import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from itertools import count

from fastapi import FastAPI

from cocktail_24.cocktail.cocktail_api import (
    CocktailApi,
    InMemoryCocktailBarStatePersistence,
    CocktailBarStatePersistence,
)
from cocktail_24.cocktail.cocktail_bookkeeping import OrderId
from cocktail_24.cocktail_management import CocktailManagement, FakeFulfillmentSystem
from cocktail_24.cocktail_runtime import async_cocktail_runtime
from main import (
    configure_system,
    configure_management,
    configure_initial_state,
)


FAKE_SYSTEM = False

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class Cocktail:
    persistence: CocktailBarStatePersistence
    api: CocktailApi
    management: CocktailManagement


def get_management(persistence, fake_system: bool = False):
    system, system_config = configure_system()
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
    persistence = InMemoryCocktailBarStatePersistence(
        initial_state=configure_initial_state()
    )
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
async def get_order_details(order_id: OrderId):
    cs = COCKTAIL.persistence.get_current_state()
    return cs


@app.get("/stort")
async def get_stort():
    cs = COCKTAIL.persistence.get_current_state()
    o_id = next(o_id for o_id in cs.orders)
    COCKTAIL.api.enqueue_order(order_id=o_id)
    print(f"enqueued:{COCKTAIL.persistence.get_current_state()}")


@app.get("/abort")
async def get_abort():
    COCKTAIL.management.get_system()._robot_.signal_stop()


@app.get("/system/state")
async def get_system_state():
    return str(COCKTAIL.management.get_system()._robot_.robo_state)


# @app.get("/system/runtime_status")
# async def get_runtime_status():
#     return {"runtime_ok": runtime_ok}
