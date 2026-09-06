"""Non-cacheable HTTP boundary for read-only historical selection."""
import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError

from twinops.rag.demo_routes import _body
from twinops.rag.request_limits import MAX_ASSISTANT_REQUEST_BYTES

from .assistant_models import HistoricalQueryRequest

from .service import HistoryError


class HistoryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=400, content={'detail': 'invalid_historical_selection'},
                                    headers={'Cache-Control': 'no-store'})
            response.headers['Cache-Control'] = 'no-store'
            return response

        return no_store


def create_history_router():
    router = APIRouter(prefix='/api/history/v1', tags=['history'], route_class=HistoryRoute)

    def invoke(request, response, method, *args, **kwargs):
        response.headers['Cache-Control'] = 'no-store'
        service = getattr(request.app.state, 'history_service', None)
        if service is None:
            raise HTTPException(503, 'historical_unavailable', headers={'Cache-Control': 'no-store'})
        try:
            return getattr(service, method)(*args, **kwargs)
        except HistoryError as error:
            raise HTTPException(error.status_code, error.detail, headers={'Cache-Control': 'no-store'}) from None
        except Exception as error:
            logging.getLogger('twinops.history').warning('historical_unavailable error_type=%s', type(error).__name__)
            raise HTTPException(503, 'historical_unavailable', headers={'Cache-Control': 'no-store'}) from None

    @router.get('/datasets')
    def datasets(request: Request, response: Response):
        return invoke(request, response, 'datasets')

    @router.get('/datasets/{dataset_id}/context')
    def context(
        dataset_id: str, request: Request, response: Response,
        from_time: str | None = Query(None, alias='from', max_length=64),
        to_time: str | None = Query(None, alias='to', max_length=64),
        end_row: int | None = Query(None, alias='endRow', ge=1),
        limit: int = Query(300, ge=1, le=300),
    ):
        result = invoke(request, response, 'context', dataset_id,
                        from_time=from_time, to_time=to_time, end_row=end_row, limit=limit)
        result['capabilities']['copilot'] = getattr(request.app.state, 'historical_assistant_service', None) is not None
        return result

    @router.post('/datasets/{dataset_id}/assistant/query')
    async def query(dataset_id: str, request: Request):
        raw = await _body(request, MAX_ASSISTANT_REQUEST_BYTES)
        try:
            body = HistoricalQueryRequest.model_validate(raw)
        except ValidationError:
            raise HTTPException(422, 'invalid_request', headers={'Cache-Control': 'no-store'}) from None
        service = getattr(request.app.state, 'historical_assistant_service', None)
        if service is None:
            raise HTTPException(503, 'historical_assistant_unavailable', headers={'Cache-Control': 'no-store'})
        try:
            return await service.query(dataset_id, body)
        except HistoryError as error:
            raise HTTPException(error.status_code, error.detail, headers={'Cache-Control': 'no-store'}) from None
        except Exception as error:
            logging.getLogger('twinops.history').warning('historical_assistant_unavailable error_type=%s', type(error).__name__)
            raise HTTPException(503, 'historical_assistant_unavailable', headers={'Cache-Control': 'no-store'}) from None

    return router
