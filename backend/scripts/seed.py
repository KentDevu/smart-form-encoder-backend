"""Seed script: creates admin user and sample form templates."""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import get_settings
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.form_template import FormTemplate
from app.database import Base

settings = get_settings()

ADMIN_EMAIL = "admin@smartform.dev"
ADMIN_PASSWORD = "admin1234"
ADMIN_NAME = "System Admin"

TEMPLATES = [
    {
        "name": "Business Permit Application",
        "description": "Application form for new or renewal of business permits in the City Hall.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "City / Municipality Office of the City Mayor",
            "title": "Business Permit Application Form",
            "sections": [
                {
                    "title": "Business Information",
                    "layout": "table",
                    "fields": [
                        {"name": "business_name", "label": "Business Name", "type": "text", "width": "full"},
                        {"name": "owner_name", "label": "Owner / Proprietor", "type": "text", "width": "full"},
                        {"name": "business_address", "label": "Business Address", "type": "text", "width": "full"},
                        {"name": "business_type", "label": "Type of Business", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "Contact & Identification",
                    "layout": "table",
                    "fields": [
                        {"name": "contact_number", "label": "Contact Number", "type": "text", "width": "half"},
                        {"name": "date_of_application", "label": "Date of Application", "type": "date", "width": "half"},
                        {"name": "tin_number", "label": "TIN Number", "type": "text", "width": "half"},
                        {"name": "ctc_number", "label": "CTC Number", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "Financial Details",
                    "layout": "table",
                    "fields": [
                        {"name": "capitalization", "label": "Capitalization", "type": "text", "width": "half"},
                        {"name": "number_of_employees", "label": "Number of Employees", "type": "text", "width": "half"},
                    ]
                },
            ],
            "footer": "I hereby certify that the above information is true and correct.",
            "fields": [
                {"name": "business_name", "label": "Business Name", "type": "text"},
                {"name": "owner_name", "label": "Owner / Proprietor", "type": "text"},
                {"name": "business_address", "label": "Business Address", "type": "text"},
                {"name": "business_type", "label": "Type of Business", "type": "text"},
                {"name": "contact_number", "label": "Contact Number", "type": "text"},
                {"name": "date_of_application", "label": "Date of Application", "type": "date"},
                {"name": "tin_number", "label": "TIN Number", "type": "text"},
                {"name": "ctc_number", "label": "CTC Number", "type": "text"},
                {"name": "capitalization", "label": "Capitalization", "type": "text"},
                {"name": "number_of_employees", "label": "Number of Employees", "type": "text"},
            ]
        },
    },
    {
        "name": "Community Tax Certificate (Cedula)",
        "description": "Application for Community Tax Certificate (Cedula) issuance.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "City / Municipality Treasury Office",
            "title": "Community Tax Certificate (Cedula)",
            "sections": [
                {
                    "title": "Personal Information",
                    "layout": "table",
                    "fields": [
                        {"name": "full_name", "label": "Full Name", "type": "text", "width": "full"},
                        {"name": "address", "label": "Address", "type": "text", "width": "full"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "place_of_birth", "label": "Place of Birth", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "Status & Employment",
                    "layout": "table",
                    "fields": [
                        {"name": "citizenship", "label": "Citizenship", "type": "text", "width": "half"},
                        {"name": "civil_status", "label": "Civil Status", "type": "text", "width": "half"},
                        {"name": "occupation", "label": "Occupation / Profession", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "Tax Information",
                    "layout": "table",
                    "fields": [
                        {"name": "tin_number", "label": "TIN Number", "type": "text", "width": "half"},
                        {"name": "gross_income", "label": "Gross Annual Income", "type": "text", "width": "half"},
                        {"name": "community_tax_due", "label": "Community Tax Due", "type": "text", "width": "half"},
                    ]
                },
            ],
            "footer": "I hereby certify that the information given above is true and correct.",
            "fields": [
                {"name": "full_name", "label": "Full Name", "type": "text"},
                {"name": "address", "label": "Address", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "place_of_birth", "label": "Place of Birth", "type": "text"},
                {"name": "citizenship", "label": "Citizenship", "type": "text"},
                {"name": "civil_status", "label": "Civil Status", "type": "text"},
                {"name": "occupation", "label": "Occupation / Profession", "type": "text"},
                {"name": "tin_number", "label": "TIN Number", "type": "text"},
                {"name": "gross_income", "label": "Gross Annual Income", "type": "text"},
                {"name": "community_tax_due", "label": "Community Tax Due", "type": "text"},
            ]
        },
    },
    {
        "name": "DTI Business Name Registration",
        "description": "DTI BNR Form No. 01-2018 – Sole Proprietorship Application Form for business name registration.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "Department of Trade and Industry",
            "title": "Business Name Registration – Sole Proprietorship Application Form",
            "template_component": "DTIBusinessNameRegistration",
            "sections": [],
            "fields": [
                {"name": "reg_type", "label": "Registration Type", "type": "radio", "options": ["new", "renewal"]},
                {"name": "certificate_no", "label": "Certificate No.", "type": "text"},
                {"name": "date_registered", "label": "Date Registered", "type": "text"},
                {"name": "tin_status", "label": "TIN Status", "type": "radio", "options": ["with_tin", "without_tin"]},
                {"name": "owners_tin", "label": "Owner's TIN", "type": "text"},
                {"name": "first_name", "label": "First Name", "type": "text"},
                {"name": "middle_name", "label": "Middle Name", "type": "text"},
                {"name": "last_name", "label": "Last Name", "type": "text"},
                {"name": "suffix", "label": "Suffix", "type": "text"},
                {"name": "dob_year", "label": "Date of Birth Year", "type": "text"},
                {"name": "dob_month", "label": "Date of Birth Month", "type": "text"},
                {"name": "dob_day", "label": "Date of Birth Day", "type": "text"},
                {"name": "civil_status", "label": "Civil Status", "type": "radio", "options": ["legally_separated", "single", "married", "widowed"]},
                {"name": "gender", "label": "Gender", "type": "radio", "options": ["male", "female"]},
                {"name": "is_refugee", "label": "Refugee", "type": "radio", "options": ["yes", "no"]},
                {"name": "is_stateless", "label": "Stateless Person", "type": "radio", "options": ["yes", "no"]},
                {"name": "citizenship", "label": "Citizenship", "type": "text"},
                {"name": "territorial_scope", "label": "Territorial Scope", "type": "radio", "options": ["barangay", "city_municipality", "regional", "national"]},
                {"name": "proposed_name_1", "label": "Proposed Business Name 1", "type": "text"},
                {"name": "proposed_name_2", "label": "Proposed Business Name 2", "type": "text"},
                {"name": "proposed_name_3", "label": "Proposed Business Name 3", "type": "text"},
                {"name": "biz_house_building", "label": "House/Building No. & Name", "type": "text"},
                {"name": "biz_street", "label": "Street", "type": "text"},
                {"name": "biz_barangay", "label": "Barangay", "type": "text"},
                {"name": "biz_city_municipality", "label": "City/Municipality", "type": "text"},
                {"name": "biz_province", "label": "Province", "type": "text"},
                {"name": "biz_region", "label": "Region", "type": "text"},
                {"name": "biz_phone", "label": "Phone No.", "type": "text"},
                {"name": "biz_mobile", "label": "Mobile No.", "type": "text"},
                {"name": "activity_manufacturer", "label": "Manufacturer/Producer", "type": "checkbox", "section": "G. PSIC", "hint": "Section G, Box 24 - Row 1, Column 1 (leftmost in top row)"},
                {"name": "activity_service", "label": "Service", "type": "checkbox", "section": "G. PSIC", "hint": "Section G, Box 24 - Row 1, Column 2 (middle in top row)"},
                {"name": "activity_retailer", "label": "Retailer", "type": "checkbox", "section": "G. PSIC", "hint": "Section G, Box 24 - Row 1, Column 3 (rightmost in top row)"},
                {"name": "activity_wholesaler", "label": "Wholesaler", "type": "checkbox", "section": "G. PSIC", "hint": "Section G, Box 24 - Row 2, Column 1 (leftmost in bottom row)"},
                {"name": "activity_importer", "label": "Importer", "type": "checkbox", "section": "G. PSIC", "hint": "Section G, Box 24 - Row 2, Column 2 (middle in bottom row)"},
                {"name": "activity_exporter", "label": "Exporter", "type": "checkbox", "section": "G. PSIC", "hint": "Section G, Box 24 - Row 2, Column 3 (rightmost in bottom row)"},
                {"name": "psic", "label": "PSIC", "type": "text"},
                {"name": "same_as_business", "label": "Same as Business Details", "type": "checkbox", "section": "H. Owner Details", "hint": "Section H - checkbox before 'Same as Business Details provided in box Nos. 16 to 23'"},
                {"name": "owner_house_building", "label": "Owner House/Building", "type": "text"},
                {"name": "owner_street", "label": "Owner Street", "type": "text"},
                {"name": "owner_barangay", "label": "Owner Barangay", "type": "text"},
                {"name": "owner_city_municipality", "label": "Owner City/Municipality", "type": "text"},
                {"name": "owner_province", "label": "Owner Province", "type": "text"},
                {"name": "owner_region", "label": "Owner Region", "type": "text"},
                {"name": "owner_phone", "label": "Owner Phone No.", "type": "text"},
                {"name": "owner_mobile", "label": "Owner Mobile No.", "type": "text"},
                {"name": "owner_email", "label": "Owner Email", "type": "text"},
                {"name": "partner_philhealth", "label": "PhilHealth", "type": "checkbox", "section": "I. Partner Agencies", "hint": "Section I, Box 35 - first checkbox, left side"},
                {"name": "partner_sss", "label": "SSS", "type": "checkbox", "section": "I. Partner Agencies", "hint": "Section I, Box 35 - second checkbox, middle"},
                {"name": "partner_pagibig", "label": "Pag-IBIG", "type": "checkbox", "section": "I. Partner Agencies", "hint": "Section I, Box 35 - third checkbox, right side"},
                {"name": "asset", "label": "Asset", "type": "text"},
                {"name": "capitalization", "label": "Capitalization", "type": "text"},
                {"name": "gross_sale_receipt", "label": "Gross Sale/Receipt", "type": "text"},
                {"name": "employees_male", "label": "Employees Male", "type": "text"},
                {"name": "employees_female", "label": "Employees Female", "type": "text"},
                {"name": "employees_total", "label": "Employees Total", "type": "text"},
            ],
        },
    },
    {
        "name": "Barangay Clearance",
        "description": "Barangay clearance certificate application form.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "Barangay Office",
            "title": "Barangay Clearance",
            "sections": [
                {
                    "title": "Applicant Information",
                    "layout": "table",
                    "fields": [
                        {"name": "full_name", "label": "Full Name", "type": "text", "width": "full"},
                        {"name": "address", "label": "Address", "type": "text", "width": "full"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "purpose", "label": "Purpose", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "CTC Reference",
                    "layout": "table",
                    "fields": [
                        {"name": "ctc_number", "label": "CTC Number", "type": "text", "width": "third"},
                        {"name": "ctc_date_issued", "label": "CTC Date Issued", "type": "date", "width": "third"},
                        {"name": "ctc_place_issued", "label": "CTC Place Issued", "type": "text", "width": "third"},
                    ]
                },
            ],
            "footer": "This certification is being issued upon the request of the above-named person for whatever legal purpose it may serve.",
            "fields": [
                {"name": "full_name", "label": "Full Name", "type": "text"},
                {"name": "address", "label": "Address", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "purpose", "label": "Purpose", "type": "text"},
                {"name": "ctc_number", "label": "CTC Number", "type": "text"},
                {"name": "ctc_date_issued", "label": "CTC Date Issued", "type": "date"},
                {"name": "ctc_place_issued", "label": "CTC Place Issued", "type": "text"},
            ]
        },
    },
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Seed admin user
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        admin = result.scalar_one_or_none()

        if admin is None:
            admin = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                full_name=ADMIN_NAME,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            print(f"✅ Admin user created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        else:
            print(f"ℹ️  Admin user already exists: {ADMIN_EMAIL}")

        # Seed templates
        for tmpl in TEMPLATES:
            result = await db.execute(
                select(FormTemplate).where(FormTemplate.name == tmpl["name"])
            )
            existing = result.scalar_one_or_none()

            if existing is None:
                template = FormTemplate(
                    name=tmpl["name"],
                    description=tmpl["description"],
                    field_schema=tmpl["field_schema"],
                )
                db.add(template)
                print(f"✅ Template created: {tmpl['name']}")
            else:
                existing.field_schema = tmpl["field_schema"]
                existing.description = tmpl["description"]
                print(f"🔄 Template updated: {tmpl['name']}")

        await db.commit()

    await engine.dispose()
    print("\n🎉 Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
