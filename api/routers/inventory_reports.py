from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Annotated
from pydantic import BaseModel
from datetime import date

from api.models import InvReport, InvReportItem, BranchProduct, Product, UserRole
from api.deps import db_dependency, role_required

router = APIRouter(
    prefix='/inventory-reports',
    tags=['inventory reports']
)

class InvReportItemBase(BaseModel):
    product_id: int
    beginning: int
    deliver: int
    transfer: int
    pull_out: int
    offtake: int
    selling_area: int

class InvReportCreate(BaseModel):
    branch_id: int
    items: List[InvReportItemBase]

class InvReportItemResponse(InvReportItemBase):
    id: int
    current_cost: float
    current_srp: float
    peso_value: float

    class Config:
        from_attributes = True

class InvReportResponse(BaseModel):
    id: int
    branch_id: int
    date_created: date
    last_edit: Optional[date]
    status: str
    items: List[InvReportItemResponse]

    class Config:
        from_attributes = True

@router.post('/', response_model=InvReportResponse, status_code=status.HTTP_201_CREATED)
def create_inventory_report(
    report: InvReportCreate,
    db: db_dependency,
    user: Annotated[dict, Depends(role_required(UserRole.PHARMACIST))]
):
    new_report = InvReport(branch_id=report.branch_id, date_created=date.today(), last_edit=date.today())
    db.add(new_report)
    db.flush()

    all_items_valid = True
    for item in report.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product with id {item.product_id} not found"
            )

        report_item = InvReportItem(
            **item.dict(),
            invreport_id=new_report.id,
            current_cost=product.cost,
            current_srp=product.srp
        )
        
        expected_selling_area = (
            item.beginning + item.deliver + item.transfer - item.pull_out - item.offtake
        )
        if item.selling_area != expected_selling_area:
            all_items_valid = False
        
        db.add(report_item)

    if all_items_valid:
        new_report.status = 'approved'
        
        for item in report.items:
            branch_product = db.query(BranchProduct).filter(
                BranchProduct.branch_id == report.branch_id,
                BranchProduct.product_id == item.product_id
            ).first()

            if branch_product:
                branch_product.quantity = item.selling_area
            else:
                new_branch_product = BranchProduct(
                    branch_id=report.branch_id,
                    product_id=item.product_id,
                    quantity=item.selling_area
                )
                db.add(new_branch_product)
    else:
        new_report.status = 'pending'

    db.commit()
    db.refresh(new_report)
    return new_report

@router.get('/{report_id}', response_model=InvReportResponse)
def get_inventory_report(
    report_id: int,
    db: db_dependency,
    user: Annotated[dict, Depends(role_required([UserRole.ADMIN, UserRole.PHARMACIST]))]
):
    report = db.query(InvReport).options(joinedload(InvReport.items)).filter(InvReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Inventory report not found")
    return report

from typing import List, Optional

@router.get('/', response_model=List[InvReportResponse])
def get_all_inventory_reports(
    db: db_dependency,
    user: Annotated[dict, Depends(role_required([UserRole.ADMIN, UserRole.PHARMACIST]))],
    skip: int = 0,
    limit: int = 100
):
    reports = db.query(InvReport).offset(skip).limit(limit).all()
    return reports

@router.get('/branch/{branch_id}', response_model=List[InvReportResponse])
def get_branch_inventory_reports(
    branch_id: int,
    db: db_dependency,
    user: Annotated[dict, Depends(role_required([UserRole.ADMIN, UserRole.PHARMACIST]))],
    skip: int = 0,
    limit: int = 100
):
    reports = db.query(InvReport).filter(InvReport.branch_id == branch_id).offset(skip).limit(limit).all()
    return reports