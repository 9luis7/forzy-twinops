"""HTTP boundary for isolated replay controls."""
from typing import Literal
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from .repository import DemoError


class DemoRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def no_store(request):
            try:
                response = await handler(request)
            except RequestValidationError as exc:
                # Validation failures belong to the same non-cacheable session boundary.
                return JSONResponse(status_code=422, content={'detail': jsonable_encoder(exc.errors())},
                                    headers={'Cache-Control': 'no-store'})
            response.headers['Cache-Control'] = 'no-store'
            return response
        return no_store


class CreateRun(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    datasetId: str = Field(min_length=1, max_length=128)
    scenario: Literal['guided', 'full']
    speed: Literal[1, 2, 5]


class Advance(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    commandId: str = Field(min_length=1, max_length=128)
    expectedRevision: int = Field(ge=0)


class Control(Advance):
    action: Literal['play', 'pause', 'resume', 'step', 'restart', 'speed']
    speed: Literal[1, 2, 5] | None = None


def create_demo_router():
    router = APIRouter(prefix='/api/demo/v1', tags=['demo'], route_class=DemoRoute)

    def invoke(request, response, method, *args):
        response.headers['Cache-Control'] = 'no-store'
        service = getattr(request.app.state, 'demo_service', None)
        if service is None:
            raise HTTPException(503, 'dataset_unavailable', headers={'Cache-Control': 'no-store'})
        try:
            return getattr(service, method)(*args)
        except DemoError as exc:
            raise HTTPException(exc.status_code, exc.detail, headers={'Cache-Control': 'no-store'}) from None

    def token(authorization):
        return authorization[7:] if authorization and authorization.startswith('Bearer ') else ''

    @router.get('/datasets')
    def datasets(request: Request, response: Response):
        return invoke(request, response, 'datasets')

    @router.post('/runs')
    def create(body: CreateRun, request: Request, response: Response):
        return invoke(request, response, 'create_run', body.datasetId, body.scenario, body.speed)

    @router.get('/runs/{run_id}/context')
    def context(run_id: str, request: Request, response: Response, authorization: str | None = Header(None)):
        return invoke(request, response, 'context', run_id, token(authorization))

    @router.post('/runs/{run_id}/control')
    def control(run_id: str, body: Control, request: Request, response: Response, authorization: str | None = Header(None)):
        return invoke(request, response, 'control', run_id, token(authorization), body)

    @router.post('/runs/{run_id}/advance')
    def advance(run_id: str, body: Advance, request: Request, response: Response, authorization: str | None = Header(None)):
        return invoke(request, response, 'advance', run_id, token(authorization), body)

    return router
