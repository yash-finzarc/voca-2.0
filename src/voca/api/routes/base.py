from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/")
async def root():
    """Root endpoint."""
    return {"message": "VOCA API", "version": "1.0.0", "status": "running"}


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.options("/{full_path:path}")
async def options_handler(full_path: str, request: Request):
    """Handle OPTIONS requests for CORS preflight."""
    origin = request.headers.get("origin", "*")

    response = Response(
        content="",
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Origin, X-Requested-With",
            "Access-Control-Max-Age": "3600",
        },
    )
    return response


