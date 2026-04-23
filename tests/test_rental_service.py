from unittest.mock import MagicMock
from app.services.rental_service import RentalService
from app.models_rental import OfferQuery, RentRequest


def test_search_offers_calls_sdk_with_query_dict():
    fake_sdk = MagicMock()
    fake_sdk.search_offers.return_value = [
        {"id": 1, "ask_contract_id": 1, "machine_id": 2, "gpu_name": "RTX 4090",
         "num_gpus": 1, "gpu_ram": 24564, "dph_total": 0.4}
    ]
    svc = RentalService(api_key="k")
    svc._sdk = fake_sdk  # inject
    offers = svc.search_offers(OfferQuery(gpu_names=["RTX 4090"]))
    assert len(offers) == 1
    assert offers[0].gpu_name == "RTX 4090"
    assert offers[0].offer_type == "on-demand"
    assert offers[0].raw["_requested_storage_gib"] == 10.0
    _, kwargs = fake_sdk.search_offers.call_args
    assert kwargs["query"]["gpu_name"] == {"eq": "RTX 4090"}
    assert kwargs["type"] == "on-demand"
    assert kwargs["order"] == "score-"
    assert kwargs["storage"] == 10.0


def test_search_offers_marks_verified_from_verification_field():
    fake_sdk = MagicMock()
    fake_sdk.search_offers.return_value = [
        {
            "id": 1,
            "ask_contract_id": 1,
            "machine_id": 2,
            "gpu_name": "RTX 4090",
            "num_gpus": 1,
            "gpu_ram": 24564,
            "dph_total": 0.4,
            "verification": "verified",
            "rentable": True,
        }
    ]
    svc = RentalService(api_key="k")
    svc._sdk = fake_sdk

    offers = svc.search_offers(OfferQuery())

    assert offers[0].verified is True


def test_search_offers_accepts_qt_stringified_enum_values():
    fake_sdk = MagicMock()
    fake_sdk.search_offers.return_value = []
    svc = RentalService(api_key="k")
    svc._sdk = fake_sdk

    svc.search_offers(OfferQuery(offer_type="on-demand", sort="score-"))

    _, kwargs = fake_sdk.search_offers.call_args
    assert kwargs["type"] == "on-demand"
    assert kwargs["order"] == "score-"


def test_search_templates():
    fake_sdk = MagicMock()
    fake_sdk.search_templates.return_value = [
        {"id": 1, "hash_id": "abc", "name": "PyTorch 2.3",
         "image": "pytorch/pytorch:2.3-cuda12"}
    ]
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    tpls = svc.search_templates()
    assert tpls[0].name == "PyTorch 2.3"


def test_create_instance_happy_path():
    fake_sdk = MagicMock()
    fake_sdk.create_instance.return_value = {"success": True, "new_contract": 555}
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    res = svc.rent(RentRequest(
        offer_id=10, image="pytorch/pytorch:latest", disk_gb=25, label="x"
    ))
    assert res.ok
    assert res.new_contract_id == 555
    fake_sdk.create_instance.assert_called_once()
    kwargs = fake_sdk.create_instance.call_args.kwargs
    assert kwargs["id"] == 10
    assert kwargs["image"] == "pytorch/pytorch:latest"
    assert kwargs["disk"] == 25
    assert kwargs["label"] == "x"


def test_create_instance_failure():
    fake_sdk = MagicMock()
    fake_sdk.create_instance.return_value = {"success": False, "msg": "out of stock"}
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    res = svc.rent(RentRequest(offer_id=1, image="img"))
    assert not res.ok
    assert "out of stock" in res.message


import pytest
from app.services.vast_service import VastAuthError, VastNetworkError


def test_call_translates_auth_error():
    fake_sdk = MagicMock()
    fake_sdk.show_ssh_keys.side_effect = Exception("401 Unauthorized")
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    with pytest.raises(VastAuthError):
        svc.list_ssh_keys()


def test_call_translates_invalid_api_key_as_auth_error():
    fake_sdk = MagicMock()
    fake_sdk.show_ssh_keys.side_effect = Exception("Invalid API key")
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    with pytest.raises(VastAuthError):
        svc.list_ssh_keys()


def test_call_translates_network_error():
    fake_sdk = MagicMock()
    fake_sdk.show_ssh_keys.side_effect = Exception("connection reset")
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    with pytest.raises(VastNetworkError):
        svc.list_ssh_keys()


def test_search_offer_network_error_includes_payload():
    fake_sdk = MagicMock()
    fake_sdk.search_offers.side_effect = Exception("400 Bad Request")
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    with pytest.raises(VastNetworkError) as err:
        svc.search_offers(OfferQuery(gpu_names=["RTX 4090"], hosting_type="datacenter"))
    msg = str(err.value)
    assert "search_offers payload" in msg
    assert "RTX 4090" in msg
    assert "datacenter" in msg


def test_rent_success_with_status_msg():
    """SDK sometimes returns {"success": True, "new_contract": ..., "msg": "..."}"""
    fake_sdk = MagicMock()
    fake_sdk.create_instance.return_value = {"success": True, "new_contract": 77, "msg": "created"}
    svc = RentalService(api_key="k"); svc._sdk = fake_sdk
    res = svc.rent(RentRequest(offer_id=1, image="img"))
    assert res.ok
    assert res.new_contract_id == 77
