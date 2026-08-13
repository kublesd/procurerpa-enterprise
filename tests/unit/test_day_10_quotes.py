from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from enterprise.auth.dependencies import get_current_user
from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.procurement.comparison import compare_quotes, normalize_money, normalize_quantity
from enterprise.procurement.models import SupplierQuoteModel
from enterprise.procurement.routes import router


def _quote(quote_id, organization_id, supplier_id, price, freight="0", moq="1", delivery_days=5):
    return SimpleNamespace(
        quote_id=quote_id,
        task_id="task_a",
        organization_id=organization_id,
        department_id="dept_a",
        category_id="pc_a",
        supplier_id=supplier_id,
        material_name="SSD",
        quantity=Decimal("10"),
        unit="unit",
        currency="CNY",
        unit_price_cny=Decimal(price),
        freight_cny=Decimal(freight),
        moq=Decimal(moq),
        delivery_days=delivery_days,
        artifact_id=f"artifact_{quote_id}",
        created_by="user_a",
    )


def test_quote_model_uses_decimal_storage_and_scope_columns():
    columns = SupplierQuoteModel.__table__.c
    assert columns.unit_price_cny.type.scale == 2
    assert columns.freight_cny.type.scale == 2
    assert columns.quantity.type.scale == 6
    assert columns.moq.type.scale == 6
    assert {fk.target_fullname for fk in SupplierQuoteModel.__table__.foreign_keys} >= {
        "tasks.task_id",
        "organizations.organization_id",
        "departments.department_id",
        "procurement_categories.category_id",
        "artifacts.artifact_id",
    }


def test_quote_comparison_is_decimal_stable_and_explains_moq_exclusion():
    quotes = (
        _quote("q_expensive", "org_a", "supplier-b", "9.99", freight="20", delivery_days=2),
        _quote("q_recommended", "org_a", "supplier-a", "10.00", freight="5"),
        _quote("q_moq", "org_a", "supplier-c", "1.00", moq="11"),
    )

    result = compare_quotes(quotes)
    assert result.recommended_quote_id == "q_recommended"
    assert [item.quote_id for item in result.quotes] == ["q_recommended", "q_expensive", "q_moq"]
    assert result.quotes[0].rank == 1
    assert result.quotes[0].total_cny == Decimal("105.00")
    assert result.quotes[0].landed_unit_price_cny == Decimal("10.500000")
    assert result.quotes[-1].eligible is False
    assert "minimum order quantity" in result.quotes[-1].reason
    assert all(isinstance(item.total_cny, Decimal) for item in result.quotes)
    assert compare_quotes(quotes) == result
    assert normalize_money("1.005") == Decimal("1.01")
    assert normalize_quantity("1.2345678") == Decimal("1.234568")


def test_quote_list_and_compare_are_scoped_to_authenticated_organization(monkeypatch):
    user = UserContext(
        user_id="user_a",
        org_id="org_a",
        department_roles=[DepartmentRole(department_id="dept_a", department_name="A", role="operator")],
        business_line_ids=[],
        procurement_category_ids=["pc_a"],
    )
    quotes = [
        _quote("q_a", "org_a", "supplier-a", "10"),
        _quote("q_b", "org_a", "supplier-b", "11"),
        _quote("q_other", "org_b", "supplier-other", "1"),
    ]

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return self

        def all(self):
            return self.rows

        def scalar_one_or_none(self):
            return self.rows[0] if self.rows else None

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, statement):
            sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
            assert "organization_id = 'org_a'" in sql
            rows = [quote for quote in quotes if quote.organization_id == user.org_id]
            return Result(rows)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        "enterprise.procurement.routes.forge_app",
        SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())),
    )
    client = TestClient(app)

    listed = client.get("/enterprise/procurement/quotes").json()
    compared = client.get("/enterprise/procurement/quotes/compare/task_a").json()
    assert listed["total"] == 2
    assert {quote["organization_id"] for quote in listed["quotes"]} == {"org_a"}
    assert compared["recommended_quote_id"] == "q_a"
    assert {quote["quote_id"] for quote in compared["quotes"]} == {"q_a", "q_b"}


def test_quote_creation_derives_organization_from_authenticated_user(monkeypatch):
    user = UserContext(
        user_id="user_a",
        org_id="org_a",
        department_roles=[DepartmentRole(department_id="dept_a", department_name="A", role="operator")],
        business_line_ids=[],
        procurement_category_ids=["pc_a"],
    )
    added = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def scalar(self, statement):
            return SimpleNamespace() if "task_extensions" in str(statement) else "artifact_a"

        def add(self, value):
            added.append(value)

        async def commit(self):
            pass

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        "enterprise.procurement.routes.forge_app",
        SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())),
    )
    response = TestClient(app).post(
        "/enterprise/procurement/quotes",
        json={
            "task_id": "task_a",
            "department_id": "dept_a",
            "category_id": "pc_a",
            "supplier_id": "supplier-a",
            "material_name": "SSD",
            "quantity": "10",
            "unit_price_cny": "10.005",
            "freight_cny": "1.005",
            "moq": "1",
            "delivery_days": 5,
            "artifact_id": "artifact_a",
        },
    )
    assert response.status_code == 201
    assert response.json()["organization_id"] == "org_a"
    assert added[0].organization_id == "org_a"
    assert added[0].unit_price_cny == Decimal("10.01")
    assert added[0].freight_cny == Decimal("1.01")
