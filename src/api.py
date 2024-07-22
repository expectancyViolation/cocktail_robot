import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cocktail_24.cocktail.cocktail_bookkeeping import OrderId
from cocktail_24.cocktail_runtime import async_cocktail_runtime
from main import gen_run_robo, config_system

system, plan = config_system()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the ML model

    rt = async_cocktail_runtime(cocktail_gen=gen_run_robo(system, plan))

    t = asyncio.create_task(rt)
    yield
    # Clean up the ML models and release the resources
    t.cancel()
    # ml_models.clear()


app = FastAPI(lifespan=lifespan)


@app.get("/order/{order_id}")
async def get_order_details(order_id: OrderId):
    return str(system._robot_.robo_state)
