import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cocktail_24.cocktail.cocktail_bookkeeping import OrderId
from cocktail_24.cocktail_runtime import async_cocktail_runtime
from main import gen_run_robo, configure_system

system, plan = configure_system()

runtime_ok = False


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

    rt = async_cocktail_runtime(cocktail_gen=gen_run_robo(system))

    t = asyncio.create_task(log_exceptions(rt))
    runtime_ok = True
    logging.warning("started runtime task")
    yield
    t.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/order/{order_id}")
async def get_order_details(order_id: OrderId):
    system.run_plan(plan)
    return str(system._robot_.robo_state)


@app.get("/system/run_plan")
async def run_plan():
    system.run_plan(plan)
    return str(system._robot_.robo_state)


@app.get("/system/state")
async def get_system_state():
    return system._robot_.robo_state


@app.get("/system/runtime_status")
async def get_runtime_status():
    return {"runtime_ok": runtime_ok}
