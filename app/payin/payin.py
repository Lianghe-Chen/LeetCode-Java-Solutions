from fastapi import FastAPI

from app.commons.context.app_context import AppContext


def create_payin_app(context: AppContext) -> FastAPI:
    # Declare sub app
    app = FastAPI(openapi_prefix="/payin", description="Payin service")

    @app.get("/charges")
    async def get_charges():
        return {"app": "Pay-In: Charges, Refunds, etc"}

    @app.get("/refunds")
    async def get_refunds():
        return {"app": "Pay-In: Charges, Refunds, etc"}

    return app
