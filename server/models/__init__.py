from fastapi.responses import JSONResponse
from fastapi import status
from log import logger


def success_response(data=None):
    log_text = f"success_response, data:{data}"
    logger.debug(log_text[:400] + "..." if len(log_text) > 400 else log_text)
    if data is not None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"code": 200, "message": "success", "data": data}
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"code": 200, "message": "success"}
        )


def error_response(msg, status_code: int = 200):
    logger.debug(f"error_response, msg:{msg}")
    return JSONResponse(
        status_code=status_code,
        content={"code": 0, "message": msg}
    )



