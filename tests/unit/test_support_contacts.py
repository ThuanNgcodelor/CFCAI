from __future__ import annotations

from src.chatbot.modules.workflows.support_contacts import SupportContactDirectory
from src.chatbot.shared.enums import PageCode, WorkflowType


def _directory() -> SupportContactDirectory:
    return SupportContactDirectory.from_file(
        "config/business/support_contacts.json"
    )


def test_price_route_uses_sales_manager_and_company_hotline() -> None:
    selection = _directory().select(
        PageCode.CFC,
        WorkflowType.PRICE_HANDOFF,
        customer_key="customer-price",
        customer_text="xin giá",
    )

    assert selection is not None
    assert selection.primary is not None
    assert selection.primary.name == "Lê Trọng Nhơn"
    assert selection.primary.title == "Trưởng phòng Kinh doanh"
    assert selection.primary.phone == "0981205448"
    assert selection.hotline is not None
    assert selection.hotline.display_phone == "1900 5307"


def test_agronomy_route_is_stable_per_customer_and_balances_configured_people() -> None:
    directory = _directory()
    first = directory.select(
        PageCode.CFC,
        WorkflowType.AGRICULTURE_ADVICE,
        customer_key="same-customer",
        customer_text="cách bón cho cây",
    )
    second = directory.select(
        PageCode.CFC,
        WorkflowType.AGRICULTURE_ADVICE,
        customer_key="same-customer",
        customer_text="cách bón cho cây",
    )

    assert first is not None and first.primary is not None
    assert second is not None and second.primary is not None
    assert first.primary.contact_id == second.primary.contact_id

    selected_ids = {
        selection.primary.contact_id
        for index in range(100)
        if (
            selection := directory.select(
                PageCode.CFC,
                WorkflowType.AGRICULTURE_ADVICE,
                customer_key=f"customer-{index}",
                customer_text="tư vấn kỹ thuật",
            )
        )
        and selection.primary is not None
    }
    assert selected_ids == {
        "agronomist-le-thanh-dam",
        "agronomist-cao-van-duoc",
    }


def test_contact_request_routes_by_need_and_never_leaks_to_zeo() -> None:
    directory = _directory()
    technical = directory.select(
        PageCode.CFC,
        WorkflowType.CONTACT_SUPPORT,
        customer_key="customer-technical",
        customer_text="Cho xin số kỹ sư nông nghiệp tư vấn kỹ thuật",
    )
    zeo = directory.select(
        PageCode.ZEO,
        WorkflowType.CONTACT_SUPPORT,
        customer_key="customer-technical",
        customer_text="Cho xin số kỹ sư nông nghiệp",
    )

    assert technical is not None
    assert technical.purpose == "agronomy"
    assert technical.primary is not None
    assert technical.primary.title == "Khuyến nông"
    assert zeo is None
