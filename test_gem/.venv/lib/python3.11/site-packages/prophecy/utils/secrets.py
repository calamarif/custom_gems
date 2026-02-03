# ─────────────────────────────────────────────────────────────────────────────
# Secrets domain  ▸ enums, connection details, CRUD request & responses
# Paste this block into json_rpc_model.py below the existing models.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import traceback
from abc import ABC
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any, Dict, List, Optional, Type
import json

from requests import Response

from prophecy.jsonrpc.models import JsonRpcResult, RequestMethod, json_rpc_method

# from .json_rpc_layer import _Sealed, RequestMethod, json_rpc_method, json_result_type, JsonRpcResult


# --------------------------------------------------------------------- enums
class SecretsProvider(str, Enum):
    HASHICORP = "HashiCorp"
    DATABRICKS = "Databricks"
    ENVIRONMENT = "Environment"


class CrudOperation(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    UPSERT = "upsert"
    DELETE = "delete"
    LIST_SECRETS = "listsecrets"
    LIST_SCOPES = "listscopes"
    HEALTH = "health"


# ---------------------------------------------------------------- connection
class SecretsProviderConnectionDetails(ABC):
    """Marker base; discriminator is the subclass name (“type”)."""

    _conn_type: str = "<unknown>"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self._conn_type
        return d

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "SecretsProviderConnectionDetails":
        ctype = raw.get("_type")
        simple_type = ctype.rsplit(".", 1)[-1]
        cls = _conn_details_registry.get(simple_type)
        if cls is None:
            raise ValueError(
                f"Unknown SecretsProviderConnectionDetails: {simple_type!r}"
            )
        return cls(**{k: v for k, v in raw.items() if k != "_type"})


_conn_details_registry: Dict[str, Type[SecretsProviderConnectionDetails]] = {}


def conn_detail_type(
    cls: Type[SecretsProviderConnectionDetails],
) -> Type[SecretsProviderConnectionDetails]:
    cls._conn_type = cls.__name__  # type: ignore[attr-defined]
    _conn_details_registry[cls.__name__] = cls
    return cls


@conn_detail_type
@dataclass  # (slots #=True)
class HashiCorpConnectionDetails(SecretsProviderConnectionDetails):
    address: Optional[str] = None
    token: Optional[str] = None
    namespace: Optional[str] = None,
    allowedSecretPaths: Optional[list[str]] = None

    @staticmethod
    def environment_driven() -> "HashiCorpConnectionDetails":
        return HashiCorpConnectionDetails()  # every field None


# ---------------------------------------------------------------- request
@json_rpc_method("request/secretsCrud")
@dataclass  # (slots #=True)
class SecretCrudRequest(RequestMethod):
    session: str
    fabricId: str
    userId: str
    providerId: str
    providerType: SecretsProvider
    operation: CrudOperation
    secretScope: Optional[str] = None
    secretKey: Optional[str] = None
    secretValue: Optional[str] = None
    providerConnectionDetails: Optional[SecretsProviderConnectionDetails] = None

    def __repr__(self) -> str:
        # redacts secretValue
        return (
            "SecretCrudRequest("
            f"{self.session}, {self.fabricId}, {self.userId}, {self.providerId}, "
            f"{self.providerType}, {self.operation}, {self.secretScope}, "
            f"{self.secretKey}, <redacted>, {self.providerConnectionDetails})"
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecretCrudRequest":
        providerConnectionDetails = data.get("providerConnectionDetails")
        return cls(
            session=data.get("session"),
            fabricId=data.get("fabricId"),
            userId=data.get("userId"),
            providerId=data.get("providerId"),
            providerType=data.get("providerType"),
            operation=data.get("operation"),
            secretScope=data.get("secretScope"),
            secretKey=data.get("secretKey"),
            secretValue=data.get("secretValue"),
            providerConnectionDetails=(
                SecretsProviderConnectionDetails.from_dict(providerConnectionDetails)
                if providerConnectionDetails
                else None
            ),
        )


# ---------------------------------------------------------------- operation-response base
_op_registry: Dict[str, Type["SecretsOperationResponse"]] = {}


def secrets_op_type(
    cls: Type["SecretsOperationResponse"],
) -> Type["SecretsOperationResponse"]:
    cls._op_type = cls.__name__  # type: ignore[attr-defined]
    _op_registry[cls.__name__] = cls
    return cls


class SecretsOperationResponse(ABC):

    def _disc(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> dict:
        body = asdict(self)
        return {"type": self._disc(), self._disc(): body}

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "SecretsOperationResponse":
        rtype = raw.get("type")
        cls = _op_registry.get(rtype)
        if cls is None:
            raise ValueError(f"Unknown SecretsOperationResponse: {rtype!r}")
        return cls(**{k: v for k, v in raw.items() if k != "type"})


# ---------------------------------------------------------------- concrete operation responses
@secrets_op_type
@dataclass  # (slots #=True)
class HashiCorpHealthResponse(SecretsOperationResponse):
    isSealed: Optional[bool]
    isOnStandBy: Optional[bool]
    isInitialized: Optional[bool]
    canConnect: bool
    message: Optional[str]

    @staticmethod
    def from_rest_response(health_resp: dict):  # hvac returns a dict
        """
        Convert the JSON payload returned by
        `hvac.Client.sys.read_health_status()` into our dataclass.

        * `sealed`       → isSealed      (None ⇒ True)
        * `standby`      → isOnStandBy
        * `initialized`  → isInitialized
        * canConnect =  !sealed && initialized
        * message: human-friendly guidance if not connectable
        """
        # hvac returns dict, so accept either a dict or an object with getters
        sealed = (
            bool(health_resp.get("sealed"))
            if isinstance(health_resp, dict)
            else bool(health_resp.sealed)
        )
        initialized = (
            bool(health_resp.get("initialized"))
            if isinstance(health_resp, dict)
            else bool(health_resp.initialized)
        )
        standby = (
            bool(health_resp.get("standby"))
            if isinstance(health_resp, dict)
            else bool(health_resp.standby)
        )

        can_connect = (not sealed) and initialized
        msg = (
            "Vault isn't initialized. Please contact your administrator"
            if not initialized
            else (
                "Vault is sealed. Please contact your administrator" if sealed else None
            )
        )

        return HashiCorpHealthResponse(
            isSealed=sealed,
            isOnStandBy=standby,
            isInitialized=initialized,
            canConnect=can_connect,
            message=msg,
        )

    def __repr__(self):
        return (
            f"HashiCorpHealthResponse({self.isSealed}, {self.isOnStandBy}, "
            f"{self.isInitialized}, {self.canConnect}, <redacted>)"
        )


@secrets_op_type
@dataclass  # (slots #=True)
class CreateResponse(SecretsOperationResponse):
    secretScope: str
    secretKey: str
    data: Optional[Dict[str, str]]

    def __repr__(self):
        return f"CreateResponse({self.secretScope}, {self.secretKey}, <redacted>)"


@secrets_op_type
@dataclass  # (slots #=True)
class DeleteResponse(SecretsOperationResponse):
    secretScope: str
    secretKey: str
    data: Optional[Dict[str, str]]

    def __repr__(self):
        return f"DeleteResponse({self.secretScope}, {self.secretKey}, <redacted>)"


@secrets_op_type
@dataclass  # (slots #=True)
class ReadResponse(SecretsOperationResponse):
    secretScope: Optional[str]
    secretKey: str
    secretValue: Optional[str]
    data: Optional[Dict[str, str]]

    def __repr__(self):
        return f"ReadResponse({self.secretScope}, {self.secretKey}, <redacted>, <redacted>)"


@secrets_op_type
@dataclass  # (slots #=True)
class ListResponse(SecretsOperationResponse):
    secretScope: Optional[str]
    secrets: Optional[Dict[str, List[str]]]
    data: Optional[Dict[str, str]]

    def __repr__(self):
        return f"ListResponse({self.secretScope}, {self.secrets}, <redacted>)"


# ---------------------------------------------------------------- JsonRpcResult wrapper
# @json_result_type("LSecretsResponse")
@dataclass  # (slots #=True)
class LSecretsResponse(JsonRpcResult):
    session: str
    fabricId: str
    userId: str
    providerId: str
    operation: CrudOperation
    response: SecretsOperationResponse
    success: bool
    errorMsg: Optional[str]
    trace: Optional[str]

    # helper constructor mirroring Scala companion object
    @staticmethod
    def from_request(
        request: SecretCrudRequest,
        response: SecretsOperationResponse,
        success: bool,
        exception: Optional[Exception] = None,
    ) -> "LSecretsResponse":
        return LSecretsResponse(
            session=request.session,
            fabricId=request.fabricId,
            userId=request.userId,
            providerId=request.providerId,
            operation=request.operation,
            response=response,
            success=success,
            errorMsg=str(exception) if exception else None,
            trace="".join(traceback.format_exception(exception)) if exception else None,
        )

    # ------------ custom serializer -----------------------
    def to_dict(self) -> dict:

        d = asdict(self)
        d["type"] = self.__class__.__name__

        # # Ensure inner `response` is serialized via its own to_dict()
        if isinstance(self.response, SecretsOperationResponse):
            d["response"] = self.response.to_dict()

        return d

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(), **kw)


# ──────────────────────────────────────────────────────────────────────────
# Secrets “one-stop shop” facade (Python port of ProphecySecrets.scala)
# Drop this anywhere *after* the earlier SecretManager / enums definitions
# ──────────────────────────────────────────────────────────────────────────
import os


# ---------------------------------------------------------------- facade
class ProphecySecrets:
    """
    Tiny static facade that mirrors the Scala `ProphecySecrets` object.
    It simply forwards to SecretManager.
    """

    # scala: get(scope, key, provider)
    @staticmethod
    def get(scope: str, key: str, provider: str) -> str:
        provider = SecretsProvider(provider.capitalize())
        return SecretManager.get(scope, key, provider)

    # scala: get(key)  (environment variable fallback)
    @staticmethod
    def getenv(key: str) -> str:
        return SecretManager.get_env(key)


# ---------------------------------------------------------------- value-object
@dataclass  # (slots=True)
class SecretValue:
    """
    Config-friendly container that prints as the *resolved* secret string,
    matching the Scala case-class (which overrides `toString`).
    """

    providerType: Optional[str] = "Databricks"
    secretScope: Optional[str] = None
    secretKey: Optional[str] = None

    def __str__(self) -> str:  # noqa: D401
        return ProphecySecrets.get(
            self.secretScope or "",
            self.secretKey or "",
            self.providerType or "Environment",
        )


# ---------------------------------------------------------------- manager
class SecretManager:
    """
    Python twin of the Scala SecretManager.
    All methods are *blocking* – call them with `asyncio.to_thread` from
    async code (see handle_secrets_crud) to stay non-blocking.
    """

    # ── ENV provider ──────────────────────────────────────────────────────
    @staticmethod
    def get_env(key: str) -> str:
        try:
            return os.environ[key]
        except KeyError:
            raise RuntimeError(f"Environment variable '{key}' is not defined")

    # expose Scala-style shorthand SecretManager.get(key)
    @staticmethod
    def get(key: str) -> str:
        return SecretManager.get_env(key)

    # ── Dispatcher (Databricks / HashiCorp / Environment) ─────────────────
    @staticmethod
    def get(
        scope: str,
        key: str,
        provider: SecretsProvider,
        provider_connection_details: Optional[HashiCorpConnectionDetails] = None,
    ) -> str:
        if provider == SecretsProvider.DATABRICKS:
            return SecretManager._get_databricks_secret(scope, key)

        if provider == SecretsProvider.HASHICORP:
            conn = (
                provider_connection_details
                if isinstance(provider_connection_details, HashiCorpConnectionDetails)
                else HashiCorpConnectionDetails.environment_driven()
            )
            val = VaultUtils.get_secret(scope, key, conn)
            if val is None:
                raise RuntimeError(
                    f"No secret present at path '{scope}' and key '{key}' for vault {conn.address}"
                )
            return val

        if provider == SecretsProvider.ENVIRONMENT:
            return SecretManager.get_env(key)

        raise RuntimeError(f"Secrets provider '{provider}' not supported yet")

    # ── Health & listings (HashiCorp) ─────────────────────────────────────
    @staticmethod
    def health(conn: HashiCorpConnectionDetails):
        resp = VaultUtils.vault_health(conn)
        VaultUtils.token_health(conn)
        return resp

    @staticmethod
    def listHashiCorpSecrets(conn: HashiCorpConnectionDetails) -> Dict[str, List[str]]:
        return VaultUtils.list_secrets(conn)

    @staticmethod
    def listEnvVariables() -> List[str]:
        return list(os.environ.keys())

    # ── CRUD for HashiCorp KV-v1 (pass-through to VaultUtils) ─────────────
    @staticmethod
    def overwriteHashiCorpSecret(
        path: str, key: str, value: str, conn: HashiCorpConnectionDetails
    ):
        return VaultUtils.overwrite_secret(path, key, value, conn)

    @staticmethod
    def appendHashiCorpSecret(
        path: str, key: str, value: str, conn: HashiCorpConnectionDetails
    ):
        return VaultUtils.append_secret(path, key, value, conn)

    @staticmethod
    def deleteHashiCorpSecret(path: str, key: str, conn: HashiCorpConnectionDetails):
        return VaultUtils.delete_secret(path, key, conn)

    # ── Databricks helper ────────────────────────────────────────────────
    @staticmethod
    def _get_databricks_secret(scope: str, key: str) -> str:
        try:
            from databricks.sdk.runtime import dbutils  # public, forward-compatible

            return dbutils.secrets.get(scope, key)
        except Exception as exc:
            raise RuntimeError("Failed to get Databricks secret") from exc


# ──────────────────────────────────────────────────────────────────────────
# SECRETS HANDLER
# Async handler for SecretCrudRequest  (drop this below other handlers)
# Depends on the Secrets domain, ProphecySecrets & SecretManager blocks
# you added earlier.
# ──────────────────────────────────────────────────────────────────────────

import asyncio

# Make sure SecretManager is imported from the facade we defined earlier
# (or from your real bridge to Scala/JVM).


async def handle_secrets_crud(req: SecretCrudRequest) -> LSecretsResponse:
    """
    Direct Python port of Scala `processSecretsRequests`.
    All potentially blocking SecretManager calls are executed in a worker
    thread via `asyncio.to_thread` so this coroutine never blocks the event-loop.
    """

    logger.info(f"Handling SecretCrudRequest : {req}")

    provider = req.providerType
    op = req.operation

    # ------------------------------------------------------------------ HashiCorp
    if provider == SecretsProvider.HASHICORP:
        # Normalise connection-details object
        conn = (
            req.providerConnectionDetails
            if isinstance(req.providerConnectionDetails, HashiCorpConnectionDetails)
            else HashiCorpConnectionDetails.environment_driven()
        )

        # ---------- HEALTH
        if op == CrudOperation.HEALTH:
            try:
                resp = await asyncio.to_thread(SecretManager.health, conn)
                out = HashiCorpHealthResponse.from_rest_response(resp)
                logger.info(f"Returning health response {out}")
                return LSecretsResponse.from_request(req, out, True)
            except Exception as exc:
                msg = (
                    "Couldn't connect to HashiCorp endpoint. "
                    "Make sure your cluster has access to Vault"
                )
                out = HashiCorpHealthResponse(None, None, None, False, message=msg)
                return LSecretsResponse.from_request(req, out, False, exc)

        # ---------- CREATE / UPDATE / UPSERT  (append/overwrite secret)
        elif op in {CrudOperation.CREATE, CrudOperation.UPDATE, CrudOperation.UPSERT}:
            try:
                lr = await asyncio.to_thread(
                    SecretManager.appendHashiCorpSecret,
                    req.secretScope or "",
                    req.secretKey or "",
                    req.secretValue or "",
                    conn,
                )
                data = None if lr is None else dict(lr.getData() or {})
                out = CreateResponse(req.secretScope or "", req.secretKey or "", data)
                return LSecretsResponse.from_request(req, out, True)
            except Exception as exc:
                out = CreateResponse(req.secretScope or "", req.secretKey or "", None)
                return LSecretsResponse.from_request(req, out, False, exc)

        # ---------- READ
        elif op == CrudOperation.READ:
            try:
                val = await asyncio.to_thread(
                    SecretManager.get,
                    req.secretScope or "",
                    req.secretKey or "",
                    provider,
                    req.providerConnectionDetails,
                )
                out = ReadResponse(req.secretScope, req.secretKey or "", val, None)
                return LSecretsResponse.from_request(req, out, True)
            except Exception as exc:
                out = ReadResponse(req.secretScope, req.secretKey or "", None, None)
                return LSecretsResponse.from_request(req, out, False, exc)

        # ---------- DELETE
        elif op == CrudOperation.DELETE:
            try:
                lr = await asyncio.to_thread(
                    SecretManager.deleteHashiCorpSecret,
                    req.secretScope or "",
                    req.secretKey or "",
                    conn,
                )
                data = None if lr is None else dict(lr.getData() or {})
                out = DeleteResponse(req.secretScope or "", req.secretKey or "", data)
                return LSecretsResponse.from_request(req, out, True)
            except Exception as exc:
                out = DeleteResponse(req.secretScope or "", req.secretKey or "", None)
                return LSecretsResponse.from_request(req, out, False, exc)

        # ---------- LIST SECRETS
        elif op == CrudOperation.LIST_SECRETS:
            try:
                secrets = await asyncio.to_thread(
                    SecretManager.listHashiCorpSecrets, conn
                )
                out = ListResponse(req.secretScope, secrets, None)
                return LSecretsResponse.from_request(req, out, True)
            except Exception as exc:
                out = ListResponse(req.secretScope, None, None)
                return LSecretsResponse.from_request(req, out, False, exc)

        else:
            raise RuntimeError(
                f"Secret operation {op} for HashiCorp is not supported yet"
            )

    # ------------------------------------------------------------------ Environment
    elif provider == SecretsProvider.ENVIRONMENT:
        # ---------- READ
        if op == CrudOperation.READ:
            try:
                val = await asyncio.to_thread(
                    SecretManager.get_env, req.secretKey or ""
                )
                out = ReadResponse(req.secretScope, req.secretKey or "", val, None)
                return LSecretsResponse.from_request(req, out, True)
            except Exception as exc:
                out = ReadResponse(req.secretScope, req.secretKey or "", None, None)
                return LSecretsResponse.from_request(req, out, False, exc)

        # ---------- LIST SECRETS
        elif op == CrudOperation.LIST_SECRETS:
            try:
                lst = await asyncio.to_thread(SecretManager.listEnvVariables)
                out = ListResponse(req.secretScope, {"global": lst}, None)
                return LSecretsResponse.from_request(req, out, True)
            except Exception as exc:
                out = ListResponse(req.secretScope, None, None)
                return LSecretsResponse.from_request(req, out, False, exc)

        else:
            raise RuntimeError(
                f"Secret operation {op.value} for Environment provider is not supported yet"
            )

    # ------------------------------------------------------------------ Unsupported provider
    raise RuntimeError(
        f"Secret operation {op.value} for provider {provider.value} with "
        f"connection {req.providerConnectionDetails} is not supported yet"
    )


# ---------------------------------------------------------------------------
# Fixed / cleaned-up VaultUtils  (replace the broken version with this one)
# ---------------------------------------------------------------------------
import asyncio
import logging
import os
import re
from collections import defaultdict
from functools import lru_cache, partial
from typing import Dict, List, Optional

import hvac  # pip install hvac

logger = logging.getLogger("VaultUtils")


# ────────────────────────────────────────────────────────────────────────────────
#  Helper regex / util
# ────────────────────────────────────────────────────────────────────────────────
_FIRST_SEG_RX = re.compile(r"^([^/]+)/?(.*)$")  # captures:   mount,  rest-of-path


def _split_mount_and_path(full_path: str) -> tuple[str, str]:
    """Return `(mount, inner_path)`   e.g.  "secret/foo"  -> ("secret", "foo")"""
    m = _FIRST_SEG_RX.match(full_path.lstrip("/"))
    if not m:
        raise ValueError(f"Illegal Vault path: {full_path!r}")
    return m.group(1), f"{m.group(2).strip('/')}/"


# ────────────────────────────────────────────────────────────────────────────────
#  VaultUtils
# ────────────────────────────────────────────────────────────────────────────────
class VaultUtils:
    # ------------------------------------------------------------------ #
    # 1.  get_vault_config  (unchanged from your original code)
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_vault_config(
        address: Optional[str] = None,
        token: Optional[str] = None,
        namespace: Optional[str] = None,
        namespace_agnostic: bool = False,
    ) -> dict:
        """
        Resolve Vault connection parameters.

        • If address / token are omitted, fall back to VAULT_ADDR / VAULT_TOKEN
        • If namespace_agnostic is True → ignore namespace entirely
        • Otherwise:
              - explicit namespace argument wins
              - else fall back to spark.conf "spark.prophecy.execution.hashicorp.namespace"
        """

        addr = address or os.getenv("VAULT_ADDR")
        tok = token or os.getenv("VAULT_TOKEN")

        if not addr or not tok:
            raise RuntimeError("Vault address/token must be supplied or set in env")

        # ---------------- namespace resolution -------------------------
        if namespace_agnostic:
            ns: Optional[str] = None
        else:
            if namespace is not None:
                ns = namespace
            else:
                # Optional spark lookup for cluster-level default
                try:
                    from server_rest import SparkSessionProxy  # lazy import

                    spark_proxy = SparkSessionProxy.get_instance()
                    ns = spark_proxy.conf.get(
                        "spark.prophecy.execution.hashicorp.namespace", None
                    )
                except Exception:
                    ns = None

            if ns:
                logger.info("Using Vault namespace %s", ns)

        return {"address": addr, "token": tok, "namespace": ns}

    # ------------------------------------------------------------------ #
    # 2.  Low-level hvac client construction
    # ------------------------------------------------------------------ #
    @staticmethod
    def _hvac_client(address: str, token: str, namespace: Optional[str]) -> hvac.Client:
        return hvac.Client(url=address, token=token, namespace=namespace)

    @staticmethod
    def _client_from_conn(
        conn: "HashiCorpConnectionDetails", namespace_agnostic=False
    ) -> hvac.Client:
        cfg = VaultUtils.get_vault_config(
            conn.address,
            conn.token,
            conn.namespace,
            namespace_agnostic=namespace_agnostic,
        )
        return VaultUtils._hvac_client(cfg["address"], cfg["token"], cfg["namespace"])

    # ────────────────────────────────────────────────────────────────────
    # 2-bis.  Health-check helpers  ❱ OSS + HCP/Enterprise
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def vault_health(conn: "HashiCorpConnectionDetails") -> Response:
        """
        Return the JSON payload at  /sys/health
        Equivalent to:  vault status  (or hvac.sys.read_health_status())
        """
        logger.info(f"Checking hashicorp health")
        cli = VaultUtils._client_from_conn(
            conn, namespace_agnostic=True
        )  # namespace-agnostic OK
        return cli.sys.read_health_status(method="GET")

    @staticmethod
    def token_health(conn: "HashiCorpConnectionDetails") -> dict:
        """
        Return the lookup-self payload for the caller’s token.
        Shows TTL, policies, display-name, etc.
        """
        cli = VaultUtils._client_from_conn(
            conn, namespace_agnostic=True
        )  # namespace-agnostic OK
        return cli.auth.token.lookup_self()

    # ------------------------------------------------------------------ #
    # 3.  Mount-version discovery  (cached)
    # ------------------------------------------------------------------ #
    @lru_cache(maxsize=256)
    def _kv_version_for_mount(cli: hvac.Client, mount_point: str) -> int:
        try:  # Enterprise/HCP first
            md = (
                cli.sys.adapter.get("/v1/sys/internal/ui/mounts")
                .get("data", {})
                .get("secret", {})
                .get(f"{mount_point}/", {})
            )
        except hvac.exceptions.InvalidPath:
            md = cli.sys.read_mount_configuration(mount_point)["data"]

        return int(md.get("options", {}).get("version", "1"))

    # ------------------------------------------------------------------ #
    # 4.  Internal helpers to read / write (v1 or v2)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_kv(cli, mount, inner, kv_ver):
        if kv_ver == 2:
            return cli.secrets.kv.v2.read_secret_version(
                path=inner or "", mount_point=mount
            )["data"]["data"]
        else:
            return cli.secrets.kv.v1.read_secret(path=inner or "", mount_point=mount)[
                "data"
            ]

    @staticmethod
    def _write_kv(cli, mount, inner, data, kv_ver):
        if kv_ver == 2:
            cli.secrets.kv.v2.create_or_update_secret(
                path=inner or "", mount_point=mount, secret=data
            )
        else:
            cli.secrets.kv.v1.create_or_update_secret(
                path=inner or "", mount_point=mount, secret=data
            )

    # ------------------------------------------------------------------ #
    # 5.  Public CRUD (works for KV1 + KV2)
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_secret(full_path: str, key: str, conn: "HashiCorpConnectionDetails"):
        logger.info(f"get_secret for full_path {full_path}")
        cli = VaultUtils._client_from_conn(conn)
        mount, inner = _split_mount_and_path(full_path)
        print(f"mount and inner {mount, inner}")
        kv = VaultUtils._kv_version_for_mount(cli, mount)
        try:
            data = VaultUtils._read_kv(cli, mount, inner, kv)
            return data.get(key)
        except hvac.exceptions.InvalidPath:
            return None

    @staticmethod
    def overwrite_secret(full_path, key, value, conn):
        cli = VaultUtils._client_from_conn(conn)
        mount, inner = _split_mount_and_path(full_path)
        kv = VaultUtils._kv_version_for_mount(cli, mount)
        VaultUtils._write_kv(cli, mount, inner, {key: value}, kv)

    @staticmethod
    def append_secret(full_path, key, value, conn):
        cli = VaultUtils._client_from_conn(conn)
        mount, inner = _split_mount_and_path(full_path)
        kv = VaultUtils._kv_version_for_mount(cli, mount)
        data = {}
        try:
            data = VaultUtils._read_kv(cli, mount, inner, kv)
        except hvac.exceptions.InvalidPath:
            logger.info(f"Secret path '{mount}/{inner}' does not exist – creating it now.")

        data[key] = value
        VaultUtils._write_kv(cli, mount, inner, data, kv)

    @staticmethod
    def delete_secret(full_path, key, conn):
        cli = VaultUtils._client_from_conn(conn)
        mount, inner = _split_mount_and_path(full_path)
        kv = VaultUtils._kv_version_for_mount(cli, mount)
        data = VaultUtils._read_kv(cli, mount, inner, kv) or {}
        data.pop(key, None)
        VaultUtils._write_kv(cli, mount, inner, data, kv)

    # ------------------------------------------------------------------ #
    # 6.  Recursive list (works for v1 + v2)
    # ------------------------------------------------------------------ #
    @staticmethod
    def list_secrets(conn: "HashiCorpConnectionDetails") -> Dict[str, List[str]]:
        cli = VaultUtils._client_from_conn(conn)
        out: Dict[str, List[str]] = defaultdict(list)

        # discover mounts
        try:
            mounts = cli.sys.adapter.get("/v1/sys/internal/ui/mounts")["data"]["secret"]
        except hvac.exceptions.InvalidPath:
            mounts = cli.sys.list_mounted_secrets_engines()

        if conn.allowedSecretPaths:
            for path in conn.allowedSecretPaths:
                mount, inner_path = _split_mount_and_path(path)
                VaultUtils._walk_kv(cli, mount, inner_path, None, out)
        else:
            for mount, meta in mounts.items():
                if meta["type"] != "kv":
                    continue
                kv = int(meta.get("options", {}).get("version", "1"))
                VaultUtils._walk_kv(cli, mount.rstrip("/"), "", kv, out)

        return dict(out)

    # result format we want
    # {
    #   "secret/sample-secret": ["first-secret", "second-secret"],
    #   "kv2/team/db"         : ["username", "password"]
    # }

    def _walk_kv(
        cli: hvac.Client,
        mount: str,  # e.g. "secret"
        inner: str,  # folder path *inside* mount  ("" at root)
        kv_ver: int,
        acc: Dict[str, List[str]],
    ):
        """Depth-first walk; for every leaf secret record  {full_path: [keys…]}."""
        path = inner or ""
        try:
            if kv_ver == 2:
                resp = cli.secrets.kv.v2.list_secrets(
                    path=path, mount_point=mount
                )
            elif kv_ver == 1:
                resp = cli.secrets.kv.v1.list_secrets(
                    path=path, mount_point=mount
                )
            else:
                try:
                    resp = cli.secrets.kv.v2.list_secrets(path=path, mount_point=mount)
                    kv_ver = 2
                    logger.info(f'Setting kv engine version as 2 for mount={mount} and path={path}')
                except Exception as e:
                    resp = cli.secrets.kv.v1.list_secrets(path=path, mount_point=mount)
                    kv_ver = 1
                    logger.info(f'Setting kv engine version as 1 for mount={mount} and path={path}')

            keys = resp["data"]["keys"]
        except hvac.exceptions.InvalidPath:
            keys = [""]

        for k in keys:
            if k.endswith("/"):  # folder → recurse
                VaultUtils._walk_kv(cli, mount, f"{inner}{k}", kv_ver, acc)
            else:  # leaf secret holder
                full_path = f"{mount}/{inner}{k}".rstrip("/")
                # ---------------- open the secret & grab inner keys ------------
                try:
                    if kv_ver == 2:
                        secret = cli.secrets.kv.v2.read_secret_version(
                            path=f"{inner}{k}", mount_point=mount
                        )["data"]["data"]
                    else:
                        secret = cli.secrets.kv.v1.read_secret(
                            path=f"{inner}{k}", mount_point=mount
                        )["data"]
                    print(full_path, inner, k)
                    acc[full_path] = list(secret.keys())
                except hvac.exceptions.InvalidPath:  # race / ACL issue
                    logger.warning(f'Got Invalid Path : {full_path}')
                    pass

    # ------------------------------------------------------------------ #
    # 7.  Async wrapper (unchanged)
    # ------------------------------------------------------------------ #
    @staticmethod
    async def aio(func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))