"""Create and probe Fireworks deployments from Modal.

The Fireworks API key is read from the Modal secret named `fireworks-api`, so
these helpers do not require local firectl auth or a local Fireworks API key.

Examples:
  modal run scripts/modal_fireworks_deploy.py::list_deployments --account sorenmadsen

  modal run scripts/modal_fireworks_deploy.py::create \
    --account sorenmadsen \
    --model accounts/sorenmadsen/models/cologic-qwen3-rtl-rft-0621b \
    --deployment-id cologic-qwen3-rft \
    --validate-only

  modal run scripts/modal_fireworks_deploy.py::probe \
    --account sorenmadsen \
    --target cologic-qwen3-rft
"""

from __future__ import annotations

import json
import time
from typing import Any

import modal

app = modal.App("rl-hdl-fireworks-deploy")

deploy_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fireworks-ai>=1.2.0a83", "openai>=1.0")
)


def _dump(obj: Any) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


def _account(account: str) -> str | None:
    return account or None


def _deployment_name(target: str, account: str) -> str:
    """Normalize a short deployment id into the model string used for inference."""
    if target.startswith("accounts/"):
        return target
    if target.startswith("deployments/"):
        if not account:
            raise ValueError("--account is required when --target starts with deployments/")
        return f"accounts/{account}/{target}"
    if not account:
        raise ValueError("--account is required when --target is a short deployment id")
    return f"accounts/{account}/deployments/{target}"


def _compact_deployment(data: dict) -> dict:
    return {
        "name": data.get("name"),
        "state": data.get("state"),
        "status": data.get("status") or data.get("statusMessage"),
        "base_model": data.get("baseModel"),
        "deployment_shape": data.get("deploymentShape"),
        "min_replica_count": data.get("minReplicaCount"),
        "max_replica_count": data.get("maxReplicaCount"),
        "desired_replica_count": data.get("desiredReplicaCount"),
        "ready_replica_count": data.get("readyReplicaCount"),
        "create_time": data.get("createTime"),
        "expire_time": data.get("expireTime"),
    }


def _compact_shape(data: dict) -> dict:
    return {
        "name": data.get("name"),
        "display_name": data.get("displayName"),
        "description": data.get("description"),
        "state": data.get("state"),
        "accelerator_type": data.get("acceleratorType"),
        "accelerator_count": data.get("acceleratorCount"),
        "precision": data.get("precision"),
        "base_model": data.get("baseModel"),
        "latest_version": data.get("latestVersion"),
    }


def _choose_shape(shapes: list[dict], hint: str) -> dict | None:
    if not shapes:
        return None

    def score(shape: dict) -> tuple[int, str]:
        haystack = json.dumps(shape, sort_keys=True).lower()
        if hint and hint.lower() in haystack:
            return (0, shape.get("name") or "")
        if "cost" in haystack or "minimal" in haystack:
            return (1, shape.get("name") or "")
        return (2, shape.get("name") or "")

    return sorted(shapes, key=score)[0]


def _error(exc: Exception) -> dict:
    return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@app.function(
    image=deploy_image,
    secrets=[modal.Secret.from_name("fireworks-api")],
    timeout=300,
)
def create_remote(
    model: str,
    deployment_id: str,
    account: str,
    deployment_shape: str,
    auto_shape: bool,
    shape_hint: str,
    accelerator_type: str,
    accelerator_count: int,
    min_replica_count: int,
    max_replica_count: int,
    validate_only: bool,
    wait: bool,
    wait_seconds: int,
    poll_seconds: int,
) -> dict:
    from fireworks import Fireworks

    client = Fireworks(account_id=_account(account))
    kwargs: dict[str, Any] = {
        "account_id": _account(account),
        "base_model": model,
        "min_replica_count": min_replica_count,
        "max_replica_count": max_replica_count,
        "validate_only": validate_only,
    }
    if deployment_id:
        kwargs["deployment_id"] = deployment_id
    if deployment_shape and not deployment_shape.startswith("accounts/"):
        return {
            "ok": False,
            "error": (
                "The Fireworks Python SDK requires --deployment-shape to be a full "
                "resource name like accounts/fireworks/deploymentShapes/<id>. "
                "Omit --deployment-shape to let Fireworks choose the default shape."
            ),
            "action": "validate" if validate_only else "create",
            "request": {
                "model": model,
                "deployment_id": deployment_id or None,
                "account": account or None,
                "deployment_shape": deployment_shape or None,
                "auto_shape": auto_shape,
                "shape_hint": shape_hint or None,
                "accelerator_type": accelerator_type,
                "accelerator_count": accelerator_count,
                "min_replica_count": min_replica_count,
                "max_replica_count": max_replica_count,
                "validate_only": validate_only,
            },
        }
    if deployment_shape:
        kwargs["deployment_shape"] = deployment_shape
    elif auto_shape:
        try:
            shapes = [_dump(shape) for shape in client.deployment_shapes.list(
                account_id=_account(account), target_model=model
            )]
        except Exception as exc:  # noqa: BLE001
            return {
                **_error(exc),
                "action": "validate" if validate_only else "create",
                "request": {
                    "model": model,
                    "deployment_id": deployment_id or None,
                    "account": account or None,
                    "deployment_shape": None,
                    "auto_shape": auto_shape,
                    "shape_hint": shape_hint or None,
                    "min_replica_count": min_replica_count,
                    "max_replica_count": max_replica_count,
                    "validate_only": validate_only,
                },
            }
        selected_shape = _choose_shape(shapes, shape_hint)
        if selected_shape is None or not selected_shape.get("name"):
            return {
                "ok": False,
                "error": "No compatible Fireworks deployment shapes were visible for this model.",
                "action": "validate" if validate_only else "create",
                "request": {
                    "model": model,
                    "deployment_id": deployment_id or None,
                    "account": account or None,
                    "deployment_shape": None,
                    "auto_shape": auto_shape,
                    "shape_hint": shape_hint or None,
                    "min_replica_count": min_replica_count,
                    "max_replica_count": max_replica_count,
                    "validate_only": validate_only,
                },
                "shapes": [],
            }
        kwargs["deployment_shape"] = selected_shape["name"]
    elif accelerator_type:
        kwargs["accelerator_type"] = accelerator_type
        kwargs["accelerator_count"] = accelerator_count

    try:
        created = client.deployments.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {
            **_error(exc),
            "action": "validate" if validate_only else "create",
            "request": {
                "model": model,
                "deployment_id": deployment_id or None,
                "account": account or None,
                "deployment_shape": kwargs.get("deployment_shape") or deployment_shape or None,
                "auto_shape": auto_shape,
                "shape_hint": shape_hint or None,
                "accelerator_type": accelerator_type,
                "accelerator_count": accelerator_count,
                "min_replica_count": min_replica_count,
                "max_replica_count": max_replica_count,
                "validate_only": validate_only,
            },
        }
    created_data = _dump(created)
    name = created_data.get("name") or deployment_id
    result = {
        "action": "validate" if validate_only else "create",
        "request": {
            "model": model,
            "deployment_id": deployment_id or None,
            "account": account or None,
            "deployment_shape": kwargs.get("deployment_shape") or deployment_shape or None,
            "auto_shape": auto_shape,
            "shape_hint": shape_hint or None,
            "accelerator_type": accelerator_type,
            "accelerator_count": accelerator_count,
            "min_replica_count": min_replica_count,
            "max_replica_count": max_replica_count,
            "validate_only": validate_only,
        },
        "deployment": _compact_deployment(created_data),
        "raw": created_data,
    }

    if validate_only or not wait:
        return result

    deadline = time.time() + wait_seconds
    history = []
    while True:
        try:
            current = client.deployments.get(name, account_id=_account(account))
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["wait_history"] = history
            return result
        data = _dump(current)
        compact = _compact_deployment(data)
        history.append(compact)
        state = compact.get("state")
        if state in {"READY", "FAILED", "DELETED"}:
            result["deployment"] = compact
            result["wait_history"] = history
            result["raw"] = data
            return result
        if time.time() >= deadline:
            result["deployment"] = compact
            result["wait_history"] = history
            result["error"] = f"timed out waiting for deployment after {wait_seconds}s"
            result["raw"] = data
            return result
        time.sleep(poll_seconds)


@app.function(
    image=deploy_image,
    secrets=[modal.Secret.from_name("fireworks-api")],
    timeout=120,
)
def list_remote(account: str, raw: bool = False) -> dict:
    from fireworks import Fireworks

    client = Fireworks(account_id=_account(account))
    try:
        deployments = [_dump(dep) for dep in client.deployments.list(account_id=_account(account))]
    except Exception as exc:  # noqa: BLE001
        return {**_error(exc), "account": account or None}
    return {
        "account": account or None,
        "count": len(deployments),
        "deployments": deployments if raw else [_compact_deployment(dep) for dep in deployments],
    }


@app.function(
    image=deploy_image,
    secrets=[modal.Secret.from_name("fireworks-api")],
    timeout=120,
)
def list_shapes_remote(account: str, model: str, raw: bool = False) -> dict:
    from fireworks import Fireworks

    client = Fireworks(account_id=_account(account))
    try:
        shapes = [_dump(shape) for shape in client.deployment_shapes.list(
            account_id=_account(account), target_model=model
        )]
    except Exception as exc:  # noqa: BLE001
        return {**_error(exc), "account": account or None, "model": model}
    return {
        "account": account or None,
        "model": model,
        "count": len(shapes),
        "shapes": shapes if raw else [_compact_shape(shape) for shape in shapes],
    }


@app.function(
    image=deploy_image,
    secrets=[modal.Secret.from_name("fireworks-api")],
    timeout=900,
)
def probe_remote(target: str, account: str, wait_seconds: int, poll_seconds: int) -> dict:
    import os

    from openai import OpenAI

    model = _deployment_name(target, account)
    client = OpenAI(
        api_key=os.environ["FIREWORKS_API_KEY"],
        base_url=os.environ.get("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
        max_retries=1,
    )
    deadline = time.time() + wait_seconds
    attempts = []
    while True:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with OK."}],
                max_tokens=8,
                temperature=0,
            )
            return {
                "target": target,
                "model": model,
                "ok": True,
                "attempts": len(attempts) + 1,
                "text": response.choices[0].message.content or "",
            }
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            attempts.append(error)
            retryable = "503" in error or "scal" in error.lower() or "temporarily" in error.lower()
            if not retryable or time.time() >= deadline:
                return {
                    "target": target,
                    "model": model,
                    "ok": False,
                    "attempts": len(attempts),
                    "error": error,
                    "errors": attempts[-5:],
                }
            time.sleep(poll_seconds)


@app.local_entrypoint()
def create(
    model: str,
    deployment_id: str = "",
    account: str = "sorenmadsen",
    deployment_shape: str = "",
    auto_shape: bool = False,
    shape_hint: str = "cost",
    accelerator_type: str = "NVIDIA_H100_80GB",
    accelerator_count: int = 1,
    min_replica_count: int = 0,
    max_replica_count: int = 1,
    validate_only: bool = False,
    wait: bool = True,
    wait_seconds: int = 900,
    poll_seconds: int = 15,
):
    """Create or validate a bounded Fireworks on-demand deployment."""
    result = create_remote.remote(
        model=model,
        deployment_id=deployment_id,
        account=account,
        deployment_shape=deployment_shape,
        auto_shape=auto_shape,
        shape_hint=shape_hint,
        accelerator_type=accelerator_type,
        accelerator_count=accelerator_count,
        min_replica_count=min_replica_count,
        max_replica_count=max_replica_count,
        validate_only=validate_only,
        wait=wait,
        wait_seconds=wait_seconds,
        poll_seconds=poll_seconds,
    )
    print(json.dumps(result, indent=2))


@app.local_entrypoint()
def list_deployments(account: str = "sorenmadsen", raw: bool = False):
    """List Fireworks on-demand deployments visible to this account."""
    print(json.dumps(list_remote.remote(account, raw), indent=2))


@app.local_entrypoint()
def list_shapes(account: str = "sorenmadsen", model: str = "", raw: bool = False):
    """List Fireworks deployment shapes compatible with a model."""
    if not model:
        raise ValueError("--model is required")
    print(json.dumps(list_shapes_remote.remote(account, model, raw), indent=2))


@app.local_entrypoint()
def probe(
    target: str,
    account: str = "sorenmadsen",
    wait_seconds: int = 600,
    poll_seconds: int = 15,
):
    """Probe a deployment via the OpenAI-compatible Fireworks inference API."""
    print(json.dumps(probe_remote.remote(target, account, wait_seconds, poll_seconds), indent=2))
