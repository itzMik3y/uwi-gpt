# auth/middleware.py
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from .config import jwt_settings
from user_db.services import verify_token


class TokenVerificationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to verify JWT tokens but not block requests.
    This adds user information to request state if token is valid,
    but doesn't block unauthorized requests - that's the job of
    the route dependencies.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            # Skip token verification for auth endpoints and non-API endpoints
            if request.url.path.startswith("/auth/") or not request.url.path.startswith(
                "/api/"
            ):
                return await call_next(request)

            # Check for token in Authorization header
            authorization = request.headers.get("Authorization")
            if authorization and authorization.startswith("Bearer "):
                token = authorization.replace("Bearer ", "")

                try:
                    # Verify and decode token
                    payload = jwt.decode(
                        token,
                        jwt_settings.jwt_secret_key,
                        algorithms=[jwt_settings.jwt_algorithm],
                    )

                    # Add user_id to request state

                    request.state.user_id = payload.get("sub")

                    if str(payload.get("sub")).startswith("admin-"):
                        request.state.user_id = str(payload.get("sub")).split("-")[-1]

                    request.state.token_type = payload.get("type")

                    # If refresh token is used where access token should be, block the request
                    if (
                        request.state.token_type == "refresh"
                        and not request.url.path.endswith("/refresh")
                    ):
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={
                                "detail": "Cannot use refresh token for this endpoint"
                            },
                        )

                    # Verify token in database
                    db = request.app.state.db_pool
                    token_record = await verify_token(
                        db, token, request.state.token_type
                    )
                    if not token_record:
                        request.state.user_id = None
                        request.state.token_type = None

                except JWTError:
                    # Don't block the request - let the dependency handle that
                    request.state.user_id = None
                    request.state.token_type = None

            # Continue processing the request
            return await call_next(request)

        except Exception as e:
            # Log the error and return 500 response
            print(f"Middleware error: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )
