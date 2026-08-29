from app.models.registry import (
    model_registry, register_model, unregister_model, list_models, get_model,
    update_model_status, get_local_models, get_models_with_capability,
    get_capabilities, is_local_endpoint, validate_local_endpoint, capability_label,
)
from app.models.router import (
    route, route_task, classify_task, execute_routing, get_model_capabilities,
    NoLocalModelAvailable,
)
from app.models.client import model_loader, ModelClient, get_model_client

__all__ = [
    "model_registry",
    "register_model",
    "unregister_model",
    "list_models",
    "get_model",
    "update_model_status",
    "get_local_models",
    "get_models_with_capability",
    "get_capabilities",
    "is_local_endpoint",
    "validate_local_endpoint",
    "capability_label",
    "route",
    "route_task",
    "classify_task",
    "execute_routing",
    "get_model_capabilities",
    "NoLocalModelAvailable",
    "model_loader",
    "ModelClient",
    "get_model_client",
]
