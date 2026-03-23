import html
import json
import os
from collections import Counter
from typing import Any, Optional, Union

import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError

load_dotenv()

st.set_page_config(
    page_title="Auto-Match Comparator",
    page_icon=":material/swap_horiz:",
    layout="wide",
)

st.markdown(
    """
    <style>
      .stApp {
        background:
          radial-gradient(circle at top left, rgba(20, 184, 166, 0.10), transparent 28%),
          radial-gradient(circle at top right, rgba(245, 158, 11, 0.10), transparent 26%),
          linear-gradient(180deg, #f7f7f2 0%, #f4f1ea 100%);
      }
      .hero-card {
        padding: 1.4rem 1.6rem;
        border: 1px solid rgba(15, 23, 42, 0.08);
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.82);
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.06);
        margin-bottom: 1rem;
      }
      .eyebrow {
        color: #0f766e;
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .hero-title {
        margin: 0.25rem 0 0.45rem;
        font-size: 2.1rem;
        line-height: 1.1;
        color: #111827;
      }
      .hero-copy {
        color: #475569;
        max-width: 58rem;
      }
      .badge-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin: 0.35rem 0 0.6rem;
      }
      .badge {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 0.18rem 0.55rem;
        font-size: 0.76rem;
        font-weight: 700;
      }
      .badge-rank {
        background: #111827;
        color: #ffffff;
      }
      .badge-shared {
        background: #ccfbf1;
        color: #115e59;
      }
      .badge-only {
        background: #fee2e2;
        color: #991b1b;
      }
      .badge-source-market {
        background: #dcfce7;
        color: #166534;
      }
      .badge-source-internal {
        background: #ffedd5;
        color: #9a3412;
      }
      .badge-source-unknown {
        background: #e5e7eb;
        color: #374151;
      }
      .spec-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.5rem;
        margin-top: 0.75rem;
      }
      .spec-card {
        border: 1px solid rgba(15, 23, 42, 0.08);
        border-radius: 14px;
        padding: 0.65rem 0.8rem;
        background: rgba(248, 250, 252, 0.95);
      }
      .spec-label {
        color: #64748b;
        font-size: 0.73rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }
      .spec-value {
        color: #111827;
        font-weight: 600;
        margin-top: 0.18rem;
      }
      .muted {
        color: #64748b;
      }
      .small-gap {
        margin-top: 0.35rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except StreamlitSecretNotFoundError:
        pass
    return os.getenv(name, default)


DEFAULT_CONFIG = {
    "api_base_url": get_secret("AUTO_MATCH_API_BASE_URL", ""),
    "frontend_base_url": get_secret("AUTO_MATCH_FRONTEND_BASE_URL", ""),
    "token": get_secret("AUTO_MATCH_BEARER_TOKEN", ""),
    "engage_api_url": get_secret("AUTO_MATCH_ENGAGE_API_URL", ""),
    "engage_token": get_secret("AUTO_MATCH_ENGAGE_BEARER_TOKEN", ""),
    "limit": int(get_secret("AUTO_MATCH_DEFAULT_LIMIT", "20") or "20"),
}

DEFAULT_FORM_STATE = {
    "reference_property": "",
}


def init_state() -> None:
    for key, value in DEFAULT_CONFIG.items():
        st.session_state.setdefault(key, value)
    for key, value in DEFAULT_FORM_STATE.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("comparison_result", None)
    st.session_state.setdefault("comparison_error", "")


def clear_results() -> None:
    st.session_state["comparison_result"] = None
    st.session_state["comparison_error"] = ""


def sanitize_token(value: str) -> str:
    token = clean_string(value).replace("\n", "")
    if token.lower().startswith("bearer "):
        token = token[7:]
    return "".join(token.split())


def normalize_base_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def join_url(base: str, path: str) -> str:
    normalized_path = str(path or "").lstrip("/")
    if not base:
        return f"/{normalized_path}"
    return f"{normalize_base_url(base)}/{normalized_path}"


def clean_string(value: Any) -> str:
    return str("" if value is None else value).strip()


def read_optional_number(value: str, label: str) -> Optional[Union[int, float]]:
    raw = clean_string(value)
    if not raw:
        return None
    try:
        parsed = float(raw)
    except ValueError as error:
        raise ValueError(f"{label} must be a valid number.") from error
    if parsed.is_integer():
        return int(parsed)
    if parsed != parsed:
        raise ValueError(f"{label} must be a valid number.")
    return parsed


def parse_comma_separated(value: str) -> list[str]:
    return [item.strip() for item in clean_string(value).split(",") if item.strip()]


def build_preferences_payload() -> dict[str, Any]:
    reference_property = clean_string(st.session_state.reference_property)
    if not reference_property:
        raise ValueError("Reference listing ID or slug is required.")
    return {"referenceProperty": reference_property}


def build_filter_payload(limit: int) -> dict[str, Any]:
    return {
        "limit": limit,
        "query": {
            "statusPublic": "Published",
            "statusWebsite": "Published",
            "isArchived": False,
        },
    }


def request_json(path: str, token: str, preferences: dict[str, Any], filter_payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    engage_api_url = normalize_base_url(st.session_state.engage_api_url)
    engage_token = sanitize_token(st.session_state.engage_token)

    if engage_api_url:
        headers["x-engage-api-url"] = engage_api_url

    if engage_token:
        headers["x-engage-bearer-token"] = engage_token

    response = requests.get(
        join_url(st.session_state.api_base_url, path),
        params={
            "preferences": json.dumps(preferences),
            "filter": json.dumps(filter_payload),
        },
        headers=headers,
        timeout=45,
    )

    try:
        payload = response.json() if response.text else None
    except ValueError:
        payload = {"message": response.text or response.reason}

    if not response.ok:
        message = (
            payload.get("message") if isinstance(payload, dict) else None
        ) or (
            payload.get("error") if isinstance(payload, dict) else None
        ) or f"{response.status_code} {response.reason}"
        raise RuntimeError(str(message))

    return payload


def get_item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("_id") or item.get("reference") or "")


def result_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {get_item_id(item): {"item": item, "index": index} for index, item in enumerate(items)}


def normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [clean_string(value) for value in values if clean_string(value)]


def get_image_url(item: dict[str, Any]) -> Optional[str]:
    featured = item.get("featuredImage") or {}
    images = item.get("images") or []
    originals = item.get("originalImages") or []
    candidates = [
        featured.get("url"),
        featured.get("mediumResolutionUrl"),
        featured.get("thumbnailURL"),
        images[0].get("url") if images else None,
        images[0].get("mediumResolutionUrl") if images else None,
        images[0].get("thumbnailURL") if images else None,
        originals[0].get("url") if originals else None,
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def get_listing_source(item: dict[str, Any]) -> str:
    source = clean_string(item.get("listingSource")).lower()
    if source in {"market", "internal"}:
        return source
    return "unknown"


def get_source_badge(item: dict[str, Any]) -> tuple[str, str]:
    source = get_listing_source(item)
    if source == "market":
        return ("badge-source-market", "Market")
    if source == "internal":
        return ("badge-source-internal", "Internal")
    return ("badge-source-unknown", "Unknown")


def count_sources(items: list[dict[str, Any]]) -> Counter:
    return Counter(get_listing_source(item) for item in items)


def format_market_debug(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    market_debug = meta.get("marketDebug") if isinstance(meta.get("marketDebug"), dict) else {}
    source_counts = meta.get("sourceCounts") if isinstance(meta.get("sourceCounts"), dict) else {}

    if not market_debug.get("enabled"):
        return str(market_debug.get("reason") or "Disabled")

    return " • ".join(
        [
            f"Internal {source_counts.get('internal', 0)}",
            f"Market {source_counts.get('market', 0)}",
            f"Fetched {market_debug.get('lastFetchReturned', 0)}/{market_debug.get('lastFetchTotal', 0)}",
        ]
    )


def get_api_listing_url(api_base_url: str, item: dict[str, Any]) -> Optional[str]:
    if get_listing_source(item) == "market":
        links = item.get("_links") if isinstance(item.get("_links"), dict) else {}
        if links.get("self"):
            return str(links["self"])
        return None

    item_id = get_item_id(item)
    if not item_id:
        return None
    populate = json.dumps({"populate": "asset"})
    encoded_item_id = requests.utils.quote(str(item_id), safe="")
    return join_url(api_base_url, f"properties/listings/{encoded_item_id}?filter={requests.utils.quote(populate)}")


def build_public_listing_url(frontend_base_url: str, item: dict[str, Any]) -> Optional[str]:
    if item.get("url"):
        return str(item["url"])
    if not frontend_base_url or not item.get("slug"):
        return None
    asset = item.get("asset") if isinstance(item.get("asset"), dict) else {}
    asset_slug = asset.get("slug") or item.get("assetSlug") or ""
    if not asset_slug:
        return None
    return (
        f"{normalize_base_url(frontend_base_url)}/"
        f"{requests.utils.quote(str(asset_slug), safe='')}/properties/"
        f"{requests.utils.quote(str(item['slug']), safe='')}"
    )


def format_number(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def format_price_value(value: Any, currency: str = "") -> str:
    if value in (None, ""):
        return "—"
    prefix = f"{currency.strip()} " if clean_string(currency) else ""
    return f"{prefix}{format_number(value)}"


def format_price(item: dict[str, Any]) -> str:
    return format_price_value(item.get("price"), item.get("currency", ""))


def format_area(value: Any) -> str:
    if value in (None, ""):
        return "—"
    return f"{format_number(value)} sqft"


def max_numeric_value(items: list[dict[str, Any]], key: str) -> Optional[float]:
    values = []
    for item in items:
        try:
            values.append(float(item.get(key)))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def dominant_currency(items: list[dict[str, Any]]) -> str:
    counts = Counter(clean_string(item.get("currency")) for item in items if clean_string(item.get("currency")))
    return counts.most_common(1)[0][0] if counts else ""


def render_hero() -> None:
    st.markdown(
        """
        <section class="hero-card">
          <div class="eyebrow">Streamlit Tool</div>
          <h1 class="hero-title">Auto-Match Preference Comparator</h1>
          <div class="hero-copy">
            Enter a reference listing ID or slug, run both listing auto-match endpoints against the same API,
            and compare the returned properties, overlap, images, and max result values.
            If you provide only the reference listing, the backend derives the rest from that source property.
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_summary(v1_payload: dict[str, Any], v2_payload: dict[str, Any], overlap_ids: list[str], preferences: dict[str, Any]) -> None:
    v1_items = v1_payload.get("data") if isinstance(v1_payload.get("data"), list) else []
    v2_items = v2_payload.get("data") if isinstance(v2_payload.get("data"), list) else []
    v1_currency = dominant_currency(v1_items)
    v2_currency = dominant_currency(v2_items)
    requested_max_budget = (
        format_price_value(preferences.get("maxBudget"), v1_currency or v2_currency)
        if preferences.get("maxBudget") is not None
        else "Derived from reference"
        if preferences.get("referenceProperty")
        else "—"
    )

    metrics = [
        ("V1 Results", str(len(v1_items))),
        ("V2 Results", str(len(v2_items))),
        ("Overlap", str(len(overlap_ids))),
        ("Unique Delta", str(abs(len(v1_items) - len(v2_items)))),
        ("Requested Max Budget", requested_max_budget),
        ("V1 Max Price", format_price_value(max_numeric_value(v1_items, "price"), v1_currency)),
        ("V2 Max Price", format_price_value(max_numeric_value(v2_items, "price"), v2_currency)),
        ("V1 Max Area", format_area(max_numeric_value(v1_items, "totalArea"))),
        ("V2 Max Area", format_area(max_numeric_value(v2_items, "totalArea"))),
        ("V2 Market Debug", format_market_debug(v2_payload)),
    ]

    st.subheader("Summary")
    cols = st.columns(3)
    for index, (label, value) in enumerate(metrics):
        cols[index % 3].metric(label, value)


def render_badges(item: dict[str, Any], index: int, is_shared: bool, is_max_price: bool, is_max_area: bool) -> None:
    source_class, source_label = get_source_badge(item)
    badges = [
        '<span class="badge badge-rank">#{}</span>'.format(index + 1),
        '<span class="badge {}">{}</span>'.format(source_class, html.escape(source_label)),
        '<span class="badge {}">{}</span>'.format(
            "badge-shared" if is_shared else "badge-only",
            "Shared" if is_shared else "Only here",
        ),
    ]
    if is_max_price:
        badges.append('<span class="badge badge-shared">Max price</span>')
    if is_max_area:
        badges.append('<span class="badge badge-shared">Max area</span>')
    st.markdown('<div class="badge-row">{}</div>'.format("".join(badges)), unsafe_allow_html=True)


def render_specs(item: dict[str, Any]) -> None:
    specs = [
        ("Property Type", item.get("propertyType") or "—"),
        ("Listing Type", item.get("listingType") or "—"),
        ("Category", item.get("listingCategory") or "—"),
        ("Furnished", item.get("furnished") or "—"),
    ]
    first_col, second_col = st.columns(2, gap="small")
    target_columns = [first_col, second_col, first_col, second_col]

    for (label, value), column in zip(specs, target_columns):
        with column:
            with st.container(border=True):
                st.caption(label)
                st.write(str(value))


def numerically_matches(value: Any, target: Any) -> bool:
    try:
        return float(value) == float(target)
    except (TypeError, ValueError):
        return False


def render_result_item(
    item: dict[str, Any],
    index: int,
    is_shared: bool,
    api_base_url: str,
    frontend_base_url: str,
    max_values: dict[str, Any],
) -> None:
    image_url = get_image_url(item)
    location_bits = [clean_string(item.get(key)) for key in ("city", "location", "subLocation", "community")]
    location_text = " • ".join([bit for bit in location_bits if bit]) or "Location n/a"
    title = item.get("title") or "Untitled"
    bedrooms_value = item.get("bedrooms")
    bathrooms_value = item.get("bathrooms")
    bedrooms_text = f"{bedrooms_value} bed" if bedrooms_value is not None else "Bedrooms n/a"
    bathrooms_text = f"{bathrooms_value} bath" if bathrooms_value is not None else "Bathrooms n/a"

    price = item.get("price")
    total_area = item.get("totalArea")
    is_max_price = max_values.get("max_price") is not None and numerically_matches(price, max_values["max_price"])
    is_max_area = max_values.get("max_area") is not None and numerically_matches(total_area, max_values["max_area"])

    with st.container(border=True):
        left, right = st.columns([1, 1.4], gap="medium")
        with left:
            if image_url:
                st.image(image_url, use_container_width=True)
            else:
                st.caption("No image available")
        with right:
            st.markdown(f"#### {html.escape(str(title))}")
            st.caption(item.get("reference") or get_item_id(item))
            render_badges(item, index, is_shared, is_max_price, is_max_area)
            st.markdown(
                f"**{format_price(item)}**  \n"
                f"{bedrooms_text} • "
                f"{bathrooms_text} • "
                f"{format_area(total_area)}"
            )
            st.markdown(
                f"<div class='muted small-gap'>{html.escape(location_text)}</div>",
                unsafe_allow_html=True,
            )
            render_specs(item)
            public_url = build_public_listing_url(frontend_base_url, item)
            api_url = get_api_listing_url(api_base_url, item)
            if public_url and api_url:
                first_link, second_link = st.columns(2, gap="small")
                with first_link:
                    st.link_button("Open listing", public_url, use_container_width=True)
                with second_link:
                    st.link_button("Open API JSON", api_url, use_container_width=True)
            elif public_url:
                st.link_button("Open listing", public_url, use_container_width=True)
            elif api_url:
                st.link_button("Open API JSON", api_url, use_container_width=True)


def render_result_panel(
    title: str,
    items: list[dict[str, Any]],
    other_map: dict[str, dict[str, Any]],
    api_base_url: str,
    frontend_base_url: str,
) -> None:
    source_counts = count_sources(items)
    st.subheader(title)
    caption_parts = [f"{len(items)} rendered"]
    if source_counts.get("internal"):
        caption_parts.append(f"{source_counts['internal']} internal")
    if source_counts.get("market"):
        caption_parts.append(f"{source_counts['market']} market")
    if source_counts.get("unknown"):
        caption_parts.append(f"{source_counts['unknown']} unknown")
    st.caption(" • ".join(caption_parts))

    if not items:
        st.info("No results returned.")
        return

    max_values = {
        "max_price": max_numeric_value(items, "price"),
        "max_area": max_numeric_value(items, "totalArea"),
    }

    for index, item in enumerate(items):
        render_result_item(
            item=item,
            index=index,
            is_shared=get_item_id(item) in other_map,
            api_base_url=api_base_url,
            frontend_base_url=frontend_base_url,
            max_values=max_values,
        )


def run_comparison() -> None:
    token = sanitize_token(st.session_state.token)
    api_base_url = normalize_base_url(st.session_state.api_base_url)
    frontend_base_url = normalize_base_url(st.session_state.frontend_base_url)
    limit = min(75, max(1, int(st.session_state.limit or 20)))

    if not token:
        raise ValueError("Bearer token is required.")
    if not api_base_url:
        raise ValueError("API base URL is required.")

    preferences = build_preferences_payload()
    filter_payload = build_filter_payload(limit)

    v1_payload = request_json("properties/listings/auto-match", token, preferences, filter_payload)
    v2_payload = request_json("properties/listings/auto-match/v2", token, preferences, filter_payload)

    st.session_state["comparison_result"] = {
        "v1_payload": v1_payload,
        "v2_payload": v2_payload,
        "preferences": preferences,
        "api_base_url": api_base_url,
        "frontend_base_url": frontend_base_url,
    }
    st.session_state["comparison_error"] = ""


def render_inputs() -> None:
    st.subheader("Preferences")
    st.text_input("Reference Listing ID or Slug", key="reference_property", placeholder="Paste a listing Mongo ID or slug")
    st.caption(
        "Both endpoints receive only `preferences.referenceProperty`. API access, published website filters, and archive exclusion are all enforced behind the scenes."
    )

    action_cols = st.columns(2, gap="medium")
    compare_clicked = action_cols[0].button("Compare", type="primary", use_container_width=True)
    action_cols[1].button("Clear Results", use_container_width=True, on_click=clear_results)

    if compare_clicked:
        try:
            with st.spinner("Running auto-match and auto-match/v2 from the simplified form..."):
                run_comparison()
        except Exception as error:
            st.session_state["comparison_result"] = None
            st.session_state["comparison_error"] = str(error)


def render_results() -> None:
    error = st.session_state["comparison_error"]
    result = st.session_state["comparison_result"]

    if error:
        st.error(error)
        return

    if not result:
        st.info("Ready.")
        return

    v1_payload = result["v1_payload"]
    v2_payload = result["v2_payload"]
    api_base_url = result["api_base_url"]
    frontend_base_url = result["frontend_base_url"]
    preferences = result["preferences"]

    v1_items = v1_payload.get("data") if isinstance(v1_payload.get("data"), list) else []
    v2_items = v2_payload.get("data") if isinstance(v2_payload.get("data"), list) else []
    v1_map = result_map(v1_items)
    v2_map = result_map(v2_items)
    overlap_ids = [item_id for item_id in v1_map if item_id in v2_map]

    render_summary(v1_payload, v2_payload, overlap_ids, preferences)

    left, right = st.columns(2, gap="large")
    with left:
        render_result_panel("Auto-Match", v1_items, v2_map, api_base_url, frontend_base_url)
    with right:
        render_result_panel("Auto-Match / v2", v2_items, v1_map, api_base_url, frontend_base_url)


def main() -> None:
    init_state()
    render_hero()

    render_inputs()
    render_results()


if __name__ == "__main__":
    main()
