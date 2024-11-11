from pydantic import BaseModel, Field
from typing import Optional, Annotated, List
from fastapi import APIRouter, HTTPException, status, Depends

from api.models import Product, UserRole, Branch, BranchProduct
from api.deps import db_dependency, user_dependency, role_required

router = APIRouter(
    prefix='/products',
    tags=['products']
)

class ProductBase(BaseModel):
    name: str
    cost: float
    srp: float
    low_stock_threshold: int = Field(gt=0, default=50)

class AddProduct(ProductBase):
    pass

class UpdateProduct(BaseModel):
    name: Optional[str] = None
    cost: Optional[float] = None
    srp: Optional[float] = None
    low_stock_threshold: Optional[int] = Field(gt=0, default=None)

@router.get('/')
def get_product(db: db_dependency, user: user_dependency, product_id: int):
    # Allow all authenticated users to view products
    return db.query(Product).filter(Product.id == product_id).first()

@router.get('/products')
def get_products(db: db_dependency, user: user_dependency):
    # Allow all authenticated users to view products
    return db.query(Product).all()

@router.post('/', status_code=status.HTTP_201_CREATED)
def add_product(
    db: db_dependency, 
    product: AddProduct, 
    user: Annotated[dict, Depends(role_required(UserRole.ADMIN))]
):
    # Create the product
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.flush()  # This assigns an ID to db_product without committing
    
    # Get all branches
    branches = db.query(Branch).filter(Branch.is_active == True).all()
    
    # Create branch_products entries for each branch
    for branch in branches:
        branch_product = BranchProduct(
            branch_id=branch.id,
            product_id=db_product.id,
            quantity=0,  # Initial quantity set to 0
            is_available=False  # Explicitly set as unavailable
        )
        db.add(branch_product)
    
    try:
        db.commit()
        db.refresh(db_product)
        return db_product
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.put('/{product_id}', status_code=status.HTTP_200_OK)
def update_product(
    product_id: int,
    product: UpdateProduct,
    db: db_dependency,
    user: Annotated[dict, Depends(role_required(UserRole.ADMIN))]
):
    # Only ADMIN can update products
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    for key, value in product.model_dump(exclude_unset=True).items():
        setattr(db_product, key, value)
    
    db.commit()
    db.refresh(db_product)
    return db_product

@router.delete('/{product_id}')
def delete_product(
    product_id: int,
    db: db_dependency, 
    user: Annotated[dict, Depends(role_required(UserRole.ADMIN))]
):
    # Only ADMIN can delete products
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(db_product)
    db.commit()
    return {"detail": "Product deleted successfully"}