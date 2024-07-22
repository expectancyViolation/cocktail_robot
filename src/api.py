import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cocktail_24.cocktail.cocktail_api import (
    CocktailApi,
    InMemoryCocktailBarStatePersistence,
)
from cocktail_24.cocktail.cocktail_bookkeeping import OrderId
from cocktail_24.cocktail_runtime import async_cocktail_runtime
from main import (
    gen_run_robo,
    configure_system,
    configure_management,
    configure_initial_state,
)

runtime_ok = False

system, system_config = configure_system()
persistence = InMemoryCocktailBarStatePersistence(
    initial_state=configure_initial_state()
)
management = configure_management(system, system_config, persistence=persistence)
cock_api = CocktailApi(state_persistence=persistence)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime_ok

    # TODO move this into runtime
    async def log_exceptions(awaitable):
        global runtime_ok
        try:
            return await awaitable
        except Exception as e:
            logging.exception(e)
            runtime_ok = False

    rt = async_cocktail_runtime(cocktail_gen=gen_run_robo(system, management))

    t = asyncio.create_task(log_exceptions(rt))
    runtime_ok = True
    logging.warning("started runtime task")
    yield
    t.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/order/{order_id}")
async def get_order_details(order_id: OrderId):
    cs = persistence.get_current_state()
    return cs


@app.get("/stort")
async def get_stort():
    cs = persistence.get_current_state()
    o_id = next(o_id for o_id in cs.orders)
    cock_api.enqueue_order(order_id=o_id)
    print(f"enqueued:{persistence.get_current_state()}")


@app.get("/order/{order_id}")
async def get_order_details(order_id: OrderId):
    # system.run_plan(plan)
    return str(system._robot_.robo_state)


@app.get("/system/run_plan")
async def run_plan():
    # system.run_plan(plan)
    return str(system._robot_.robo_state)


@app.get("/system/state")
async def get_system_state():
    return system._robot_.robo_state


@app.get("/system/runtime_status")
async def get_runtime_status():
    return {"runtime_ok": runtime_ok}
