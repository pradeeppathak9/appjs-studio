import pytest

from studio.providers.fal import load_config as load_fal_config
from studio.providers.gemini import IMAGE_MODELS as GEMINI_IMAGE_MODELS
from studio.providers.openai_images import MODELS as OPENAI_MODELS
from studio.providers.pricing import PriceList, load_prices


def test_the_bundled_price_list_loads_and_names_real_models():
    prices = load_prices()
    assert prices.credit_usd > 0
    known = {
        "gemini": set(GEMINI_IMAGE_MODELS),
        "openai": set(OPENAI_MODELS),
        "fal": {m.id for m in load_fal_config().models},
        "fake": {"fake-image-1"},
    }
    for m in prices.models:
        assert m.model in known[m.provider], f"{m.provider} {m.model} is not a model Studio knows"


def test_duplicate_prices_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        PriceList.model_validate(
            {
                "checked": "2026-11-26",
                "credit_usd": 0.04,
                "models": [
                    {"provider": "fal", "model": "x", "usd": 0.01},
                    {"provider": "fal", "model": "x", "usd": 0.02},
                ],
            }
        )


async def test_signed_in_users_can_read_prices(admin, anon):
    r = await admin.get("/v1/model-prices")
    assert r.status_code == 200
    body = r.json()
    assert body["credit_usd"] == load_prices().credit_usd
    assert any(m["model"] == "gemini-3.1-flash-image" for m in body["models"])
    assert (await anon.get("/v1/model-prices")).status_code == 401
