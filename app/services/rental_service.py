from __future__ import annotations
from typing import Any
from app.models_rental import (
    Offer, OfferQuery, RentRequest, RentResult, Template, SshKey,
)
from app.services.offer_query import build_offer_query
from app.services.offer_parser import parse_offer
from app.services.vast_service import VastAuthError, VastNetworkError


def _enum_value(v):
    return getattr(v, "value", v)


class RentalService:
    """Wraps VastAI SDK rental operations: search offers, templates, ssh keys, rent."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._sdk = None

    def _client(self):
        if self._sdk is None:
            from vastai import VastAI
            self._sdk = VastAI(api_key=self.api_key)
        return self._sdk

    def _call(self, name: str, **kwargs):
        sdk = self._client()
        try:
            return getattr(sdk, name)(**kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "unauthori" in msg or "forbidden" in msg or "invalid api key" in msg:
                raise VastAuthError(str(e)) from e
            raise VastNetworkError(str(e)) from e

    # ---- Offers ----
    def search_offers(self, query: OfferQuery) -> list[Offer]:
        q_dict, order, limit, storage = build_offer_query(query)
        offer_type = str(_enum_value(query.offer_type))
        try:
            raw = self._call(
                "search_offers",
                query=q_dict, type=offer_type,
                order=order, limit=limit, storage=storage, no_default=True,
            )
        except VastNetworkError as e:
            raise VastNetworkError(
                f"{e}; search_offers payload="
                f"type={offer_type}, order={order}, limit={limit}, "
                f"storage={storage}, query={q_dict}"
            ) from e
        if not isinstance(raw, list):
            return []
        return [parse_offer(r) for r in raw if isinstance(r, dict) and "id" in r]

    def show_instance_filters(self) -> list[dict]:
        raw = self._call("show_instance_filters")
        return raw if isinstance(raw, list) else []

    # ---- Templates ----
    def search_templates(self, q: str | None = None) -> list[Template]:
        raw = self._call("search_templates", query=q) if q else self._call("search_templates")
        out: list[Template] = []
        if isinstance(raw, list):
            for t in raw:
                if not isinstance(t, dict):
                    continue
                out.append(Template(
                    id=int(t.get("id") or 0),
                    hash_id=str(t.get("hash_id") or t.get("hash") or ""),
                    name=t.get("name") or "Template",
                    image=t.get("image") or "",
                    description=t.get("description"),
                    recommended=bool(t.get("recommended")),
                    raw=t,
                ))
        return out

    # ---- SSH keys ----
    def list_ssh_keys(self) -> list[SshKey]:
        raw = self._call("show_ssh_keys")
        out: list[SshKey] = []
        if isinstance(raw, list):
            for k in raw:
                if not isinstance(k, dict):
                    continue
                out.append(SshKey(
                    id=int(k.get("id") or 0),
                    public_key=k.get("ssh_key") or k.get("public_key") or "",
                    label=k.get("name") or k.get("label"),
                ))
        return out

    def create_ssh_key(self, public_key: str) -> SshKey:
        raw = self._call("create_ssh_key", ssh_key=public_key) or {}
        return SshKey(
            id=int(raw.get("id") or 0),
            public_key=raw.get("ssh_key") or public_key,
            label=raw.get("name"),
        )

    # ---- Rent ----
    def rent(self, req: RentRequest) -> RentResult:
        kwargs: dict[str, Any] = {
            "id": req.offer_id,
            "image": req.image,
            "disk": req.disk_gb,
        }
        if req.template_hash:
            kwargs["template_hash"] = req.template_hash
        if req.label:
            kwargs["label"] = req.label
        if req.env:
            kwargs["env"] = req.env
        if req.onstart_cmd:
            kwargs["onstart_cmd"] = req.onstart_cmd
        if req.jupyter_lab:
            kwargs["jupyter_lab"] = True
            if req.jupyter_dir:
                kwargs["jupyter_dir"] = req.jupyter_dir
        if req.price is not None:
            kwargs["price"] = req.price
        if req.runtype:
            kwargs["runtype"] = req.runtype
        if req.args is not None:
            kwargs["args"] = req.args
        if req.force:
            kwargs["force"] = True
        if req.cancel_unavail:
            kwargs["cancel_unavail"] = True

        raw = self._call("create_instance", **kwargs) or {}
        # Vast SDK returns either {"success": bool, ...} or {"new_contract": id, ...} without success.
        # Only treat as failure when success is explicitly False OR no success key AND error/msg present.
        explicit = raw.get("success")
        if explicit is True:
            ok = True
        elif explicit is False:
            ok = False
        else:
            ok = "error" not in raw and "msg" not in raw
        new_id = raw.get("new_contract") or raw.get("contract_id") or raw.get("new_contract_id")
        msg = str(raw.get("msg") or raw.get("error") or ("created" if ok else "unknown"))
        return RentResult(ok=ok, new_contract_id=int(new_id) if new_id else None,
                          message=msg, raw=raw)
