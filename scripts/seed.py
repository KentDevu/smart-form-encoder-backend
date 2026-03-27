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
from app.services.forms.template_schema import normalize_template_schema

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
    {
        "name": "Barangay Business Clearance",
        "description": "Barangay business clearance certificate for business permit application.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "Barangay Business Clearance",
            "title": "Office of the Barangay Captain",
            "sections": [
                {
                    "title": "A. OWNER'S INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "owner_full_name", "label": "Full Name of Owner", "type": "text", "width": "full"},
                        {"name": "owner_address", "label": "Owner's Complete Address", "type": "text", "width": "full"},
                        {"name": "owner_contact_number", "label": "Contact Number", "type": "text", "width": "half"},
                        {"name": "owner_civil_status", "label": "Civil Status", "type": "select", "width": "half", "options": ["Single", "Married", "Widowed", "Separated"]},
                    ]
                },
                {
                    "title": "B. BUSINESS INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "business_name", "label": "Business Name", "type": "text", "width": "full"},
                        {"name": "business_nature", "label": "Nature of Business", "type": "text", "width": "full"},
                        {"name": "business_address", "label": "Business Address (Barangay)", "type": "text", "width": "full"},
                        {"name": "business_started_year", "label": "Year Business Started", "type": "number", "width": "quarter"},
                        {"name": "business_started_month", "label": "Month", "type": "number", "width": "quarter"},
                        {"name": "number_of_employees", "label": "No. of Employees", "type": "number", "width": "half"},
                        {"name": "monthly_rent", "label": "Monthly Rent (if applicable)", "type": "text", "width": "half"},
                        {"name": "capitalization", "label": "Capitalization", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "C. PERMIT DETAILS",
                    "layout": "table",
                    "fields": [
                        {"name": "dti_registration_no", "label": "DTI Registration No.", "type": "text", "width": "half"},
                        {"name": "dti_date_registered", "label": "DTI Date Registered", "type": "date", "width": "half"},
                        {"name": "tin_number", "label": "TIN No.", "type": "text", "width": "half"},
                        {"name": "permit_type", "label": "Type of Permit", "type": "select", "width": "half", "options": ["New", "Renewal"]},
                    ]
                },
                {
                    "title": "D. CTC INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "ctc_number", "label": "CTC No.", "type": "text", "width": "third"},
                        {"name": "ctc_date_issued", "label": "CTC Date Issued", "type": "date", "width": "third"},
                        {"name": "ctc_place_issued", "label": "CTC Place Issued", "type": "text", "width": "third"},
                        {"name": "ctc_amount", "label": "Amount Paid", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "E. REQUIREMENTS",
                    "layout": "table",
                    "fields": [
                        {"name": "req_dti_cert", "label": "DTI Certificate of Registration", "type": "checkbox"},
                        {"name": "req_sss_clearance", "label": "SSS Clearance", "type": "checkbox"},
                        {"name": "req_philhealth", "label": "PhilHealth Certificate", "type": "checkbox"},
                        {"name": "req_pagibig", "label": "Pag-IBIG Certificate", "type": "checkbox"},
                        {"name": "req_bir", "label": "BIR Certificate of Registration", "type": "checkbox"},
                        {"name": "req_sanitary", "label": "Sanitary Permit", "type": "checkbox"},
                        {"name": "req_fire_safety", "label": "Fire Safety Inspection Certificate", "type": "checkbox"},
                        {"name": "req_picture", "label": "2x2 Picture (Owner)", "type": "checkbox"},
                    ]
                },
            ],
            "footer": "This is to certify that the above-named person owns a legitimate business within this barangay and has complied with all barangay requirements.",
            "fields": [
                {"name": "owner_full_name", "label": "Full Name of Owner", "type": "text"},
                {"name": "owner_address", "label": "Owner's Complete Address", "type": "text"},
                {"name": "owner_contact_number", "label": "Contact Number", "type": "text"},
                {"name": "owner_civil_status", "label": "Civil Status", "type": "select"},
                {"name": "business_name", "label": "Business Name", "type": "text"},
                {"name": "business_nature", "label": "Nature of Business", "type": "text"},
                {"name": "business_address", "label": "Business Address (Barangay)", "type": "text"},
                {"name": "business_started_year", "label": "Year Business Started", "type": "number"},
                {"name": "business_started_month", "label": "Month", "type": "number"},
                {"name": "number_of_employees", "label": "No. of Employees", "type": "number"},
                {"name": "monthly_rent", "label": "Monthly Rent (if applicable)", "type": "text"},
                {"name": "capitalization", "label": "Capitalization", "type": "text"},
                {"name": "dti_registration_no", "label": "DTI Registration No.", "type": "text"},
                {"name": "dti_date_registered", "label": "DTI Date Registered", "type": "date"},
                {"name": "tin_number", "label": "TIN No.", "type": "text"},
                {"name": "permit_type", "label": "Type of Permit", "type": "select"},
                {"name": "ctc_number", "label": "CTC No.", "type": "text"},
                {"name": "ctc_date_issued", "label": "CTC Date Issued", "type": "date"},
                {"name": "ctc_place_issued", "label": "CTC Place Issued", "type": "text"},
                {"name": "ctc_amount", "label": "Amount Paid", "type": "text"},
                {"name": "req_dti_cert", "label": "DTI Certificate of Registration", "type": "checkbox"},
                {"name": "req_sss_clearance", "label": "SSS Clearance", "type": "checkbox"},
                {"name": "req_philhealth", "label": "PhilHealth Certificate", "type": "checkbox"},
                {"name": "req_pagibig", "label": "Pag-IBIG Certificate", "type": "checkbox"},
                {"name": "req_bir", "label": "BIR Certificate of Registration", "type": "checkbox"},
                {"name": "req_sanitary", "label": "Sanitary Permit", "type": "checkbox"},
                {"name": "req_fire_safety", "label": "Fire Safety Inspection Certificate", "type": "checkbox"},
                {"name": "req_picture", "label": "2x2 Picture (Owner)", "type": "checkbox"},
            ]
        },
    },
    {
        "name": "Certificate of Indigency",
        "description": "Certificate of Indigency application form for indigent individuals.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "City/Municipality Social Welfare & Development Office",
            "title": "Certificate of Indigency",
            "sections": [
                {
                    "title": "APPLICANT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "full_name", "label": "Full Name", "type": "text", "width": "full"},
                        {"name": "address", "label": "Complete Address", "type": "text", "width": "full"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "age", "label": "Age", "type": "number", "width": "quarter"},
                        {"name": "civil_status", "label": "Civil Status", "type": "select", "width": "quarter", "options": ["Single", "Married", "Widowed", "Separated"]},
                        {"name": "contact_number", "label": "Contact Number", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "FAMILY BACKGROUND",
                    "layout": "table",
                    "fields": [
                        {"name": "spouse_name", "label": "Spouse Name (if married)", "type": "text", "width": "full"},
                        {"name": "father_name", "label": "Father's Name", "type": "text", "width": "full"},
                        {"name": "mother_maiden_name", "label": "Mother's Maiden Name", "type": "text", "width": "full"},
                        {"name": "number_of_dependents", "label": "No. of Dependents", "type": "number", "width": "half"},
                        {"name": "occupation", "label": "Occupation/Source of Income", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "PURPOSE OF INDIGENCY CERTIFICATE",
                    "layout": "table",
                    "fields": [
                        {"name": "purpose_other", "label": "If Other, Please Specify", "type": "text", "width": "full"},
                        {"name": "purpose_school", "label": "School Enrollment/Scholarship", "type": "checkbox"},
                        {"name": "purpose_medical", "label": "Medical Assistance", "type": "checkbox"},
                        {"name": "purpose_financial", "label": "Financial Assistance", "type": "checkbox"},
                        {"name": "purpose_legal", "label": "Legal Aid/Documentary Requirements", "type": "checkbox"},
                        {"name": "purpose_burial", "label": "Burial Assistance", "type": "checkbox"},
                    ]
                },
                {
                    "title": "MONTHLY INCOME",
                    "layout": "table",
                    "fields": [
                        {"name": "monthly_income", "label": "Estimated Monthly Income", "type": "text", "width": "half"},
                        {"name": "monthly_expenses", "label": "Estimated Monthly Expenses", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "CTC INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "ctc_number", "label": "CTC No.", "type": "text", "width": "third"},
                        {"name": "ctc_date_issued", "label": "CTC Date Issued", "type": "date", "width": "third"},
                        {"name": "ctc_place_issued", "label": "CTC Place Issued", "type": "text", "width": "third"},
                    ]
                },
            ],
            "footer": "This is to certify that the above-named person is a bonafide resident of this municipality/city and is financially incapable to avail of basic services due to economic constraints.",
            "fields": [
                {"name": "full_name", "label": "Full Name", "type": "text"},
                {"name": "address", "label": "Complete Address", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "age", "label": "Age", "type": "number"},
                {"name": "civil_status", "label": "Civil Status", "type": "select"},
                {"name": "contact_number", "label": "Contact Number", "type": "text"},
                {"name": "spouse_name", "label": "Spouse Name (if married)", "type": "text"},
                {"name": "father_name", "label": "Father's Name", "type": "text"},
                {"name": "mother_maiden_name", "label": "Mother's Maiden Name", "type": "text"},
                {"name": "number_of_dependents", "label": "No. of Dependents", "type": "number"},
                {"name": "occupation", "label": "Occupation/Source of Income", "type": "text"},
                {"name": "purpose_other", "label": "If Other, Please Specify", "type": "text"},
                {"name": "purpose_school", "label": "School Enrollment/Scholarship", "type": "checkbox"},
                {"name": "purpose_medical", "label": "Medical Assistance", "type": "checkbox"},
                {"name": "purpose_financial", "label": "Financial Assistance", "type": "checkbox"},
                {"name": "purpose_legal", "label": "Legal Aid/Documentary Requirements", "type": "checkbox"},
                {"name": "purpose_burial", "label": "Burial Assistance", "type": "checkbox"},
                {"name": "monthly_income", "label": "Estimated Monthly Income", "type": "text"},
                {"name": "monthly_expenses", "label": "Estimated Monthly Expenses", "type": "text"},
                {"name": "ctc_number", "label": "CTC No.", "type": "text"},
                {"name": "ctc_date_issued", "label": "CTC Date Issued", "type": "date"},
                {"name": "ctc_place_issued", "label": "CTC Place Issued", "type": "text"},
            ]
        },
    },
    {
        "name": "SSS E1 Form (SSS Application)",
        "description": "Social Security System (SSS) E-1 Member Registration Form for new members.",
        "field_schema": {
            "header": "Social Security System",
            "subheader": "Member Registration Form",
            "title": "SSS E-1 Form",
            "sections": [
                {
                    "title": "A. PERSONAL DATA",
                    "layout": "table",
                    "fields": [
                        {"name": "last_name", "label": "Last Name", "type": "text", "width": "full"},
                        {"name": "first_name", "label": "First Name", "type": "text", "width": "full"},
                        {"name": "middle_name", "label": "Middle Name", "type": "text", "width": "full"},
                        {"name": "suffix", "label": "Suffix (Jr., Sr., III, etc.)", "type": "text", "width": "half"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "place_of_birth", "label": "Place of Birth", "type": "text", "width": "full"},
                        {"name": "gender", "label": "Gender", "type": "select", "width": "half", "options": ["Male", "Female"]},
                        {"name": "civil_status", "label": "Civil Status", "type": "select", "width": "half", "options": ["Single", "Married", "Widowed", "Separated/Annulled"]},
                    ]
                },
                {
                    "title": "B. HOME ADDRESS",
                    "layout": "table",
                    "fields": [
                        {"name": "house_lot_block", "label": "House/Lot/Block No.", "type": "text", "width": "half"},
                        {"name": "street", "label": "Street", "type": "text", "width": "half"},
                        {"name": "subdivision", "label": "Subdivision/Village", "type": "text", "width": "full"},
                        {"name": "barangay", "label": "Barangay", "type": "text", "width": "half"},
                        {"name": "city_municipality", "label": "City/Municipality", "type": "text", "width": "half"},
                        {"name": "province", "label": "Province", "type": "text", "width": "half"},
                        {"name": "zip_code", "label": "Zip Code", "type": "text", "width": "half"},
                        {"name": "mailing_address", "label": "Mailing Address (if different)", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "C. CONTACT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "mobile_number", "label": "Mobile Number", "type": "text", "width": "half"},
                        {"name": "telephone_number", "label": "Telephone Number (with area code)", "type": "text", "width": "half"},
                        {"name": "email_address", "label": "Email Address", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "D. CITIZENENSHIP",
                    "layout": "table",
                    "fields": [
                        {"name": "citizenship", "label": "Citizenship", "type": "text", "width": "full"},
                        {"name": "dual_citizenship", "label": "Dual Citizenship", "type": "checkbox"},
                        {"name": "dual_citizenship_type", "label": "If Dual, Type (C/M/R/D)", "type": "select", "width": "half", "options": ["C - CISC", "M - MBR", "R - RA9225", "D - DUAL"]},
                        {"name": "country_of_birth", "label": "Country of Birth (if natural-born Filipino)", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "E. EMPLOYMENT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "employment_status", "label": "Employment Status", "type": "select", "width": "half", "options": ["Employed", "Self-Employed", "Household Helper", "OFW", "None"]},
                        {"name": "employer_name", "label": "Employer/Agency Name", "type": "text", "width": "full"},
                        {"name": "employer_address", "label": "Employer Address", "type": "text", "width": "full"},
                        {"name": "occupation", "label": "Occupation/Position", "type": "text", "width": "full"},
                        {"name": "monthly_income", "label": "Estimated Monthly Income", "type": "text", "width": "half"},
                        {"name": "date_started", "label": "Date Started", "type": "date", "width": "half"},
                    ]
                },
                {
                    "title": "F. BENEFICIARY/IES",
                    "layout": "table",
                    "fields": [
                        {"name": "primary_beneficiary_name", "label": "Primary Beneficiary Name", "type": "text", "width": "full"},
                        {"name": "primary_beneficiary_relationship", "label": "Relationship", "type": "text", "width": "half"},
                        {"name": "primary_beneficiary_dob", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "secondary_beneficiary_name", "label": "Secondary Beneficiary Name", "type": "text", "width": "full"},
                        {"name": "secondary_beneficiary_relationship", "label": "Relationship", "type": "text", "width": "half"},
                        {"name": "secondary_beneficiary_dob", "label": "Date of Birth", "type": "date", "width": "half"},
                    ]
                },
                {
                    "title": "G. IDENTIFICATION CARD PRESENTED",
                    "layout": "table",
                    "fields": [
                        {"name": "id_type", "label": "ID Type", "type": "select", "width": "full", "options": ["UMID", "Driver's License", "Passport", "PRC ID", "Voter's ID", "Postal ID", "TIN ID", "PhilHealth ID", "Pag-IBIG ID", "Other"]},
                        {"name": "id_number", "label": "ID Number", "type": "text", "width": "half"},
                        {"name": "id_date_issued", "label": "Date Issued", "type": "date", "width": "half"},
                    ]
                },
            ],
            "footer": "I certify that the information provided above is true and correct. I agree to be bound by the provisions of the Social Security Act of 1997, as amended.",
            "fields": [
                {"name": "last_name", "label": "Last Name", "type": "text"},
                {"name": "first_name", "label": "First Name", "type": "text"},
                {"name": "middle_name", "label": "Middle Name", "type": "text"},
                {"name": "suffix", "label": "Suffix (Jr., Sr., III, etc.)", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "place_of_birth", "label": "Place of Birth", "type": "text"},
                {"name": "gender", "label": "Gender", "type": "select"},
                {"name": "civil_status", "label": "Civil Status", "type": "select"},
                {"name": "house_lot_block", "label": "House/Lot/Block No.", "type": "text"},
                {"name": "street", "label": "Street", "type": "text"},
                {"name": "subdivision", "label": "Subdivision/Village", "type": "text"},
                {"name": "barangay", "label": "Barangay", "type": "text"},
                {"name": "city_municipality", "label": "City/Municipality", "type": "text"},
                {"name": "province", "label": "Province", "type": "text"},
                {"name": "zip_code", "label": "Zip Code", "type": "text"},
                {"name": "mailing_address", "label": "Mailing Address (if different)", "type": "text"},
                {"name": "mobile_number", "label": "Mobile Number", "type": "text"},
                {"name": "telephone_number", "label": "Telephone Number (with area code)", "type": "text"},
                {"name": "email_address", "label": "Email Address", "type": "text"},
                {"name": "citizenship", "label": "Citizenship", "type": "text"},
                {"name": "dual_citizenship", "label": "Dual Citizenship", "type": "checkbox"},
                {"name": "dual_citizenship_type", "label": "If Dual, Type (C/M/R/D)", "type": "select"},
                {"name": "country_of_birth", "label": "Country of Birth (if natural-born Filipino)", "type": "text"},
                {"name": "employment_status", "label": "Employment Status", "type": "select"},
                {"name": "employer_name", "label": "Employer/Agency Name", "type": "text"},
                {"name": "employer_address", "label": "Employer Address", "type": "text"},
                {"name": "occupation", "label": "Occupation/Position", "type": "text"},
                {"name": "monthly_income", "label": "Estimated Monthly Income", "type": "text"},
                {"name": "date_started", "label": "Date Started", "type": "date"},
                {"name": "primary_beneficiary_name", "label": "Primary Beneficiary Name", "type": "text"},
                {"name": "primary_beneficiary_relationship", "label": "Relationship", "type": "text"},
                {"name": "primary_beneficiary_dob", "label": "Date of Birth", "type": "date"},
                {"name": "secondary_beneficiary_name", "label": "Secondary Beneficiary Name", "type": "text"},
                {"name": "secondary_beneficiary_relationship", "label": "Relationship", "type": "text"},
                {"name": "secondary_beneficiary_dob", "label": "Date of Birth", "type": "date"},
                {"name": "id_type", "label": "ID Type", "type": "select"},
                {"name": "id_number", "label": "ID Number", "type": "text"},
                {"name": "id_date_issued", "label": "Date Issued", "type": "date"},
            ]
        },
    },
    {
        "name": "Pag-IBIG MDF (Member's Data Form)",
        "description": "Home Development Mutual Fund (Pag-IBIG) Member's Data Form for membership registration.",
        "field_schema": {
            "header": "Home Development Mutual Fund",
            "subheader": "Pag-IBIG Fund",
            "title": "Member's Data Form",
            "sections": [
                {
                    "title": "A. PERSONAL INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "last_name", "label": "Last Name", "type": "text", "width": "full"},
                        {"name": "first_name", "label": "First Name", "type": "text", "width": "full"},
                        {"name": "middle_name", "label": "Middle Name", "type": "text", "width": "full"},
                        {"name": "suffix", "label": "Suffix", "type": "text", "width": "half"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "place_of_birth", "label": "Place of Birth", "type": "text", "width": "full"},
                        {"name": "gender", "label": "Gender", "type": "select", "width": "half", "options": ["Male", "Female"]},
                        {"name": "civil_status", "label": "Civil Status", "type": "select", "width": "half", "options": ["Single", "Married", "Widowed", "Separated", "Annulled"]},
                        {"name": "citizenship", "label": "Citizenship", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "B. PRESENT ADDRESS",
                    "layout": "table",
                    "fields": [
                        {"name": "house_no", "label": "House No./Unit/Flr.", "type": "text", "width": "half"},
                        {"name": "street", "label": "Street/Sitio", "type": "text", "width": "half"},
                        {"name": "subdivision", "label": "Subdivision/Village", "type": "text", "width": "full"},
                        {"name": "barangay", "label": "Barangay", "type": "text", "width": "half"},
                        {"name": "city_municipality", "label": "City/Municipality", "type": "text", "width": "half"},
                        {"name": "province", "label": "Province", "type": "text", "width": "half"},
                        {"name": "zip_code", "label": "Zip Code", "type": "text", "width": "half"},
                        {"name": "address_tenure_years", "label": "Length of Stay (Years)", "type": "number", "width": "quarter"},
                        {"name": "address_tenure_months", "label": "Months", "type": "number", "width": "quarter"},
                    ]
                },
                {
                    "title": "C. CONTACT DETAILS",
                    "layout": "table",
                    "fields": [
                        {"name": "mobile_number", "label": "Mobile No.", "type": "text", "width": "half"},
                        {"name": "email_address", "label": "Email Address", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "D. EMPLOYMENT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "employment_type", "label": "Employment Type", "type": "select", "width": "half", "options": ["Employed", "Self-Employed", "None"]},
                        {"name": "employer_name", "label": "Employer Name", "type": "text", "width": "full"},
                        {"name": "employer_address", "label": "Employer Address", "type": "text", "width": "full"},
                        {"name": "position", "label": "Position/Title", "type": "text", "width": "full"},
                        {"name": "monthly_basic_salary", "label": "Monthly Basic Salary", "type": "text", "width": "half"},
                        {"name": "date_employed", "label": "Date Employed", "type": "date", "width": "half"},
                    ]
                },
                {
                    "title": "E. DEPENDENTS",
                    "layout": "table",
                    "fields": [
                        {"name": "spouse_name", "label": "Spouse Full Name", "type": "text", "width": "full"},
                        {"name": "spouse_employment", "label": "Spouse Employed?", "type": "checkbox"},
                        {"name": "spouse_employer", "label": "Spouse Employer Name", "type": "text", "width": "full"},
                        {"name": "number_of_children", "label": "No. of Children", "type": "number", "width": "half"},
                        {"name": "number_of_parents", "label": "No. of Parents", "type": "number", "width": "half"},
                    ]
                },
                {
                    "title": "F. BENEFICIARY(IES)",
                    "layout": "table",
                    "fields": [
                        {"name": "beneficiary_1_name", "label": "Beneficiary 1 Name", "type": "text", "width": "full"},
                        {"name": "beneficiary_1_relationship", "label": "Relationship", "type": "text", "width": "half"},
                        {"name": "beneficiary_1_dob", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "beneficiary_1_share", "label": "Share (%)", "type": "text", "width": "half"},
                        {"name": "beneficiary_2_name", "label": "Beneficiary 2 Name", "type": "text", "width": "full"},
                        {"name": "beneficiary_2_relationship", "label": "Relationship", "type": "text", "width": "half"},
                        {"name": "beneficiary_2_dob", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "beneficiary_2_share", "label": "Share (%)", "type": "text", "width": "half"},
                    ]
                },
            ],
            "footer": "I certify that the information provided in this form is true and correct. I authorize Pag-IBIG Fund to verify and validate the information herein.",
            "fields": [
                {"name": "last_name", "label": "Last Name", "type": "text"},
                {"name": "first_name", "label": "First Name", "type": "text"},
                {"name": "middle_name", "label": "Middle Name", "type": "text"},
                {"name": "suffix", "label": "Suffix", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "place_of_birth", "label": "Place of Birth", "type": "text"},
                {"name": "gender", "label": "Gender", "type": "select"},
                {"name": "civil_status", "label": "Civil Status", "type": "select"},
                {"name": "citizenship", "label": "Citizenship", "type": "text"},
                {"name": "house_no", "label": "House No./Unit/Flr.", "type": "text"},
                {"name": "street", "label": "Street/Sitio", "type": "text"},
                {"name": "subdivision", "label": "Subdivision/Village", "type": "text"},
                {"name": "barangay", "label": "Barangay", "type": "text"},
                {"name": "city_municipality", "label": "City/Municipality", "type": "text"},
                {"name": "province", "label": "Province", "type": "text"},
                {"name": "zip_code", "label": "Zip Code", "type": "text"},
                {"name": "address_tenure_years", "label": "Length of Stay (Years)", "type": "number"},
                {"name": "address_tenure_months", "label": "Months", "type": "number"},
                {"name": "mobile_number", "label": "Mobile No.", "type": "text"},
                {"name": "email_address", "label": "Email Address", "type": "text"},
                {"name": "employment_type", "label": "Employment Type", "type": "select"},
                {"name": "employer_name", "label": "Employer Name", "type": "text"},
                {"name": "employer_address", "label": "Employer Address", "type": "text"},
                {"name": "position", "label": "Position/Title", "type": "text"},
                {"name": "monthly_basic_salary", "label": "Monthly Basic Salary", "type": "text"},
                {"name": "date_employed", "label": "Date Employed", "type": "date"},
                {"name": "spouse_name", "label": "Spouse Full Name", "type": "text"},
                {"name": "spouse_employment", "label": "Spouse Employed?", "type": "checkbox"},
                {"name": "spouse_employer", "label": "Spouse Employer Name", "type": "text"},
                {"name": "number_of_children", "label": "No. of Children", "type": "number"},
                {"name": "number_of_parents", "label": "No. of Parents", "type": "number"},
                {"name": "beneficiary_1_name", "label": "Beneficiary 1 Name", "type": "text"},
                {"name": "beneficiary_1_relationship", "label": "Relationship", "type": "text"},
                {"name": "beneficiary_1_dob", "label": "Date of Birth", "type": "date"},
                {"name": "beneficiary_1_share", "label": "Share (%)", "type": "text"},
                {"name": "beneficiary_2_name", "label": "Beneficiary 2 Name", "type": "text"},
                {"name": "beneficiary_2_relationship", "label": "Relationship", "type": "text"},
                {"name": "beneficiary_2_dob", "label": "Date of Birth", "type": "date"},
                {"name": "beneficiary_2_share", "label": "Share (%)", "type": "text"},
            ]
        },
    },
    {
        "name": "BIR Form 1901 (Registration)",
        "description": "Bureau of Internal Revenue Form 1901 - Application for Registration for Self-Employed and Mixed Income Earners.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "Bureau of Internal Revenue",
            "title": "Application for Registration - Form 1901",
            "sections": [
                {
                    "title": "A. TAXPAYER INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "tin", "label": "Taxpayer Identification Number (TIN)", "type": "text", "width": "full"},
                        {"name": "registered_name", "label": "Registered Name", "type": "text", "width": "full"},
                        {"name": "trade_name", "label": "Trade/Business Name", "type": "text", "width": "full"},
                        {"name": "mailing_address", "label": "Mailing Address", "type": "text", "width": "full"},
                        {"name": "rdo_code", "label": "Revenue District Office (RDO) Code", "type": "text", "width": "half"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "birth_place", "label": "Place of Birth", "type": "text", "width": "full"},
                        {"name": "gender", "label": "Sex", "type": "select", "width": "half", "options": ["Male", "Female"]},
                        {"name": "civil_status", "label": "Civil Status", "type": "select", "width": "half", "options": ["Single", "Married", "Widowed", "Separated"]},
                        {"name": "citizenship", "label": "Citizenship", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "B. CONTACT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "telephone_number", "label": "Telephone Number", "type": "text", "width": "half"},
                        {"name": "mobile_number", "label": "Mobile Number", "type": "text", "width": "half"},
                        {"name": "email_address", "label": "Email Address", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "C. TAX TYPE REGISTRATION",
                    "layout": "table",
                    "fields": [
                        {"name": "tax_type_income", "label": "Income Tax", "type": "checkbox"},
                        {"name": "tax_type_percentage", "label": "Percentage Tax", "type": "checkbox"},
                        {"name": "tax_type_vat", "label": "Value Added Tax (VAT)", "type": "checkbox"},
                        {"name": "tax_type_excise", "label": "Excise Tax", "type": "checkbox"},
                        {"name": "tax_type_documentary", "label": "Documentary Stamp Tax", "type": "checkbox"},
                        {"name": "tax_type_compensating", "label": "Compensating Tax", "type": "checkbox"},
                        {"name": "withholding_agent", "label": "Withholding Agent Type", "type": "select", "width": "full", "options": ["Non-Withholding Agent", "Withholding Agent (Non-Remittable)", "Withholding Agent (Remittable)", "Top Withholding Agent"]},
                    ]
                },
                {
                    "title": "D. BUSINESS INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "business_address", "label": "Business Address", "type": "text", "width": "full"},
                        {"name": "nature_of_business", "label": "Nature of Business", "type": "text", "width": "full"},
                        {"name": "business_registration_type", "label": "Business Registration Type", "type": "select", "width": "half", "options": ["Single Proprietorship", "Partnership", "Corporation", "Professional Practice"]},
                        {"name": "registration_date", "label": "Date of Registration", "type": "date", "width": "half"},
                        {"name": "dti_reg_number", "label": "DTI Registration Number", "type": "text", "width": "half"},
                        {"name": "sec_reg_number", "label": "SEC Registration Number", "type": "text", "width": "half"},
                        {"name": "initial_monthly_sales", "label": "Initial Monthly Sales/Receipts", "type": "text", "width": "full"},
                        {"name": "initial_gross_receipts", "label": "Annual Gross Receipts", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "E. BOOKS OF ACCOUNT",
                    "layout": "table",
                    "fields": [
                        {"name": "books_type", "label": "Type of Books of Account", "type": "select", "width": "full", "options": ["Manual", "Loose Leaf", "Computerized"]},
                        {"name": "books_accreditation_no", "label": "Accreditation Number (if computerized)", "type": "text", "width": "half"},
                        {"name": "books_date_accredited", "label": "Date Accredited", "type": "date", "width": "half"},
                    ]
                },
            ],
            "footer": "I hereby certify that the information given in this application is true and correct. I agree to be bound by the provisions of the National Internal Revenue Code.",
            "fields": [
                {"name": "tin", "label": "Taxpayer Identification Number (TIN)", "type": "text"},
                {"name": "registered_name", "label": "Registered Name", "type": "text"},
                {"name": "trade_name", "label": "Trade/Business Name", "type": "text"},
                {"name": "mailing_address", "label": "Mailing Address", "type": "text"},
                {"name": "rdo_code", "label": "Revenue District Office (RDO) Code", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "birth_place", "label": "Place of Birth", "type": "text"},
                {"name": "gender", "label": "Sex", "type": "select"},
                {"name": "civil_status", "label": "Civil Status", "type": "select"},
                {"name": "citizenship", "label": "Citizenship", "type": "text"},
                {"name": "telephone_number", "label": "Telephone Number", "type": "text"},
                {"name": "mobile_number", "label": "Mobile Number", "type": "text"},
                {"name": "email_address", "label": "Email Address", "type": "text"},
                {"name": "tax_type_income", "label": "Income Tax", "type": "checkbox"},
                {"name": "tax_type_percentage", "label": "Percentage Tax", "type": "checkbox"},
                {"name": "tax_type_vat", "label": "Value Added Tax (VAT)", "type": "checkbox"},
                {"name": "tax_type_excise", "label": "Excise Tax", "type": "checkbox"},
                {"name": "tax_type_documentary", "label": "Documentary Stamp Tax", "type": "checkbox"},
                {"name": "tax_type_compensating", "label": "Compensating Tax", "type": "checkbox"},
                {"name": "withholding_agent", "label": "Withholding Agent Type", "type": "select"},
                {"name": "business_address", "label": "Business Address", "type": "text"},
                {"name": "nature_of_business", "label": "Nature of Business", "type": "text"},
                {"name": "business_registration_type", "label": "Business Registration Type", "type": "select"},
                {"name": "registration_date", "label": "Date of Registration", "type": "date"},
                {"name": "dti_reg_number", "label": "DTI Registration Number", "type": "text"},
                {"name": "sec_reg_number", "label": "SEC Registration Number", "type": "text"},
                {"name": "initial_monthly_sales", "label": "Initial Monthly Sales/Receipts", "type": "text"},
                {"name": "initial_gross_receipts", "label": "Annual Gross Receipts", "type": "text"},
                {"name": "books_type", "label": "Type of Books of Account", "type": "select"},
                {"name": "books_accreditation_no", "label": "Accreditation Number (if computerized)", "type": "text"},
                {"name": "books_date_accredited", "label": "Date Accredited", "type": "date"},
            ]
        },
    },
    {
        "name": "NBI Clearance Application",
        "description": "National Bureau of Investigation (NBI) Clearance Application Form for individuals.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "National Bureau of Investigation",
            "title": "NBI Clearance Application Form",
            "sections": [
                {
                    "title": "A. PERSONAL DATA",
                    "layout": "table",
                    "fields": [
                        {"name": "last_name", "label": "Last Name", "type": "text", "width": "full"},
                        {"name": "first_name", "label": "First Name", "type": "text", "width": "full"},
                        {"name": "middle_name", "label": "Middle Name", "type": "text", "width": "full"},
                        {"name": "suffix", "label": "Suffix", "type": "text", "width": "half"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "place_of_birth", "label": "Place of Birth (City/Municipality, Province)", "type": "text", "width": "full"},
                        {"name": "gender", "label": "Sex", "type": "select", "width": "half", "options": ["Male", "Female"]},
                        {"name": "civil_status", "label": "Civil Status", "type": "select", "width": "half", "options": ["Single", "Married", "Widowed", "Separated", "Annulled"]},
                        {"name": "height", "label": "Height (cm)", "type": "text", "width": "half"},
                        {"name": "weight", "label": "Weight (kg)", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "B. ADDRESS",
                    "layout": "table",
                    "fields": [
                        {"name": "house_no", "label": "House/Lot/Block No.", "type": "text", "width": "half"},
                        {"name": "street", "label": "Street", "type": "text", "width": "half"},
                        {"name": "barangay", "label": "Barangay", "type": "text", "width": "half"},
                        {"name": "city_municipality", "label": "City/Municipality", "type": "text", "width": "half"},
                        {"name": "province", "label": "Province", "type": "text", "width": "half"},
                        {"name": "zip_code", "label": "Zip Code", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "C. CONTACT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "email_address", "label": "Email Address", "type": "text", "width": "full"},
                        {"name": "mobile_number", "label": "Mobile Number", "type": "text", "width": "half"},
                        {"name": "telephone_number", "label": "Telephone Number", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "D. OTHER INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "birthplace_city_municipality", "label": "Birthplace City/Municipality", "type": "text", "width": "half"},
                        {"name": "birthplace_province", "label": "Birthplace Province", "type": "text", "width": "half"},
                        {"name": "citizenship", "label": "Citizenship", "type": "text", "width": "full"},
                        {"name": "mother_maiden_name", "label": "Mother's Maiden Name", "type": "text", "width": "full"},
                        {"name": "complexion", "label": "Complexion", "type": "select", "width": "half", "options": ["Fair", "Light Brown", "Dark", "Morena", "Kayumanggi"]},
                        {"name": "eyes_color", "label": "Color of Eyes", "type": "select", "width": "half", "options": ["Black", "Brown", "Blue", "Green", "Hazel"]},
                        {"name": "hair_type", "label": "Type of Hair", "type": "select", "width": "half", "options": ["Straight", "Curly", "Wavy", "Kinky"]},
                        {"name": "hair_color", "label": "Color of Hair", "type": "select", "width": "half", "options": ["Black", "Brown", "Blonde", "Gray", "White"]},
                        {"name": "distinguishing_marks", "label": "Distinguishing Marks", "type": "textarea", "width": "full"},
                    ]
                },
                {
                    "title": "E. PURPOSE OF CLEARANCE",
                    "layout": "table",
                    "fields": [
                        {"name": "purpose_employment", "label": "Local Employment", "type": "checkbox"},
                        {"name": "purpose_abroad", "label": "Abroad", "type": "checkbox"},
                        {"name": "purpose_travel", "label": "Travel/Visa Requirement", "type": "checkbox"},
                        {"name": "purpose_id", "label": "ID Requirement/Gun License", "type": "checkbox"},
                        {"name": "purpose_government", "label": "Government Requirement", "type": "checkbox"},
                        {"name": "purpose_other", "label": "Other (Please Specify)", "type": "text", "width": "full"},
                    ]
                },
            ],
            "footer": "I hereby certify that all information given in this application are true and correct to the best of my knowledge.",
            "fields": [
                {"name": "last_name", "label": "Last Name", "type": "text"},
                {"name": "first_name", "label": "First Name", "type": "text"},
                {"name": "middle_name", "label": "Middle Name", "type": "text"},
                {"name": "suffix", "label": "Suffix", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "place_of_birth", "label": "Place of Birth (City/Municipality, Province)", "type": "text"},
                {"name": "gender", "label": "Sex", "type": "select"},
                {"name": "civil_status", "label": "Civil Status", "type": "select"},
                {"name": "height", "label": "Height (cm)", "type": "text"},
                {"name": "weight", "label": "Weight (kg)", "type": "text"},
                {"name": "house_no", "label": "House/Lot/Block No.", "type": "text"},
                {"name": "street", "label": "Street", "type": "text"},
                {"name": "barangay", "label": "Barangay", "type": "text"},
                {"name": "city_municipality", "label": "City/Municipality", "type": "text"},
                {"name": "province", "label": "Province", "type": "text"},
                {"name": "zip_code", "label": "Zip Code", "type": "text"},
                {"name": "email_address", "label": "Email Address", "type": "text"},
                {"name": "mobile_number", "label": "Mobile Number", "type": "text"},
                {"name": "telephone_number", "label": "Telephone Number", "type": "text"},
                {"name": "birthplace_city_municipality", "label": "Birthplace City/Municipality", "type": "text"},
                {"name": "birthplace_province", "label": "Birthplace Province", "type": "text"},
                {"name": "citizenship", "label": "Citizenship", "type": "text"},
                {"name": "mother_maiden_name", "label": "Mother's Maiden Name", "type": "text"},
                {"name": "complexion", "label": "Complexion", "type": "select"},
                {"name": "eyes_color", "label": "Color of Eyes", "type": "select"},
                {"name": "hair_type", "label": "Type of Hair", "type": "select"},
                {"name": "hair_color", "label": "Color of Hair", "type": "select"},
                {"name": "distinguishing_marks", "label": "Distinguishing Marks", "type": "textarea"},
                {"name": "purpose_employment", "label": "Local Employment", "type": "checkbox"},
                {"name": "purpose_abroad", "label": "Abroad", "type": "checkbox"},
                {"name": "purpose_travel", "label": "Travel/Visa Requirement", "type": "checkbox"},
                {"name": "purpose_id", "label": "ID Requirement/Gun License", "type": "checkbox"},
                {"name": "purpose_government", "label": "Government Requirement", "type": "checkbox"},
                {"name": "purpose_other", "label": "Other (Please Specify)", "type": "text"},
            ]
        },
    },
    {
        "name": "PhilHealth Member Registration Form (PMRF)",
        "description": "PhilHealth Member Registration Form (PMRF) for new members.",
        "field_schema": {
            "header": "Philippine Health Insurance Corporation",
            "subheader": "Member Registration Form",
            "title": "PMRF - PhilHealth Member Registration Form",
            "sections": [
                {
                    "title": "A. MEMBER INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "last_name", "label": "Last Name", "type": "text", "width": "full"},
                        {"name": "first_name", "label": "First Name", "type": "text", "width": "full"},
                        {"name": "middle_name", "label": "Middle Name", "type": "text", "width": "full"},
                        {"name": "suffix", "label": "Suffix", "type": "text", "width": "half"},
                        {"name": "date_of_birth", "label": "Date of Birth", "type": "date", "width": "half"},
                        {"name": "place_of_birth", "label": "Place of Birth", "type": "text", "width": "full"},
                        {"name": "gender", "label": "Sex", "type": "select", "width": "half", "options": ["Male", "Female"]},
                        {"name": "civil_status", "label": "Civil Status", "type": "select", "width": "half", "options": ["Single", "Married", "Widowed", "Legally Separated"]},
                        {"name": "philhealth_id", "label": "PhilHealth Identification Number (PIN)", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "B. MEMBER CATEGORY",
                    "layout": "table",
                    "fields": [
                        {"name": "member_category", "label": "Member Category", "type": "select", "width": "full", "options": ["Employed in Private Sector", "Employed in Government Sector", "Self-Employing", "Sponsored Member", "Lifetime Member", "Indigent Member", "Kasambahay", "OFW", "Informal Economy"]},
                        {"name": "employer_name", "label": "Employer Name (for Employed Members)", "type": "text", "width": "full"},
                        {"name": "employer_address", "label": "Employer Address", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "C. ADDRESS",
                    "layout": "table",
                    "fields": [
                        {"name": "house_no", "label": "House/Unit/Block No.", "type": "text", "width": "half"},
                        {"name": "street", "label": "Street", "type": "text", "width": "half"},
                        {"name": "barangay", "label": "Barangay", "type": "text", "width": "half"},
                        {"name": "city_municipality", "label": "City/Municipality", "type": "text", "width": "half"},
                        {"name": "province", "label": "Province", "type": "text", "width": "third"},
                        {"name": "zip_code", "label": "Zip Code", "type": "text", "width": "third"},
                        {"name": "region", "label": "Region", "type": "text", "width": "third"},
                    ]
                },
                {
                    "title": "D. CONTACT DETAILS",
                    "layout": "table",
                    "fields": [
                        {"name": "mobile_number", "label": "Mobile Number", "type": "text", "width": "half"},
                        {"name": "telephone_number", "label": "Telephone Number", "type": "text", "width": "half"},
                        {"name": "email_address", "label": "Email Address", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "E. BENEFICIARIES",
                    "layout": "table",
                    "fields": [
                        {"name": "legal_spouse_name", "label": "Legal Spouse Name", "type": "text", "width": "full"},
                        {"name": "legal_spouse_dob", "label": "Spouse Date of Birth", "type": "date", "width": "half"},
                        {"name": "legal_spouse_dob", "label": "Spouse PhilHealth ID (if member)", "type": "text", "width": "half"},
                        {"name": "child_1_name", "label": "Child 1 Name", "type": "text", "width": "full"},
                        {"name": "child_1_dob", "label": "Child 1 Date of Birth", "type": "date", "width": "half"},
                        {"name": "child_1_philhealth_id", "label": "Child 1 PhilHealth ID", "type": "text", "width": "half"},
                        {"name": "child_2_name", "label": "Child 2 Name", "type": "text", "width": "full"},
                        {"name": "child_2_dob", "label": "Child 2 Date of Birth", "type": "date", "width": "half"},
                        {"name": "child_2_philhealth_id", "label": "Child 2 PhilHealth ID", "type": "text", "width": "half"},
                        {"name": "child_3_name", "label": "Child 3 Name", "type": "text", "width": "full"},
                        {"name": "child_3_dob", "label": "Child 3 Date of Birth", "type": "date", "width": "half"},
                        {"name": "child_3_philhealth_id", "label": "Child 3 PhilHealth ID", "type": "text", "width": "half"},
                        {"name": "child_4_name", "label": "Child 4 Name", "type": "text", "width": "full"},
                        {"name": "child_4_dob", "label": "Child 4 Date of Birth", "type": "date", "width": "half"},
                        {"name": "child_4_philhealth_id", "label": "Child 4 PhilHealth ID", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "F. PAYMENT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "start_period", "label": "Period Covered (From)", "type": "date", "width": "half"},
                        {"name": "end_period", "label": "Period Covered (To)", "type": "date", "width": "half"},
                        {"name": "payment_amount", "label": "Amount Paid", "type": "text", "width": "half"},
                        {"name": "or_number", "label": "OR Number", "type": "text", "width": "half"},
                    ]
                },
            ],
            "footer": "I certify that the information herein is true and correct. I understand that any false statement made will subject me to penalties under the law.",
            "fields": [
                {"name": "last_name", "label": "Last Name", "type": "text"},
                {"name": "first_name", "label": "First Name", "type": "text"},
                {"name": "middle_name", "label": "Middle Name", "type": "text"},
                {"name": "suffix", "label": "Suffix", "type": "text"},
                {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
                {"name": "place_of_birth", "label": "Place of Birth", "type": "text"},
                {"name": "gender", "label": "Sex", "type": "select"},
                {"name": "civil_status", "label": "Civil Status", "type": "select"},
                {"name": "philhealth_id", "label": "PhilHealth Identification Number (PIN)", "type": "text"},
                {"name": "member_category", "label": "Member Category", "type": "select"},
                {"name": "employer_name", "label": "Employer Name (for Employed Members)", "type": "text"},
                {"name": "employer_address", "label": "Employer Address", "type": "text"},
                {"name": "house_no", "label": "House/Unit/Block No.", "type": "text"},
                {"name": "street", "label": "Street", "type": "text"},
                {"name": "barangay", "label": "Barangay", "type": "text"},
                {"name": "city_municipality", "label": "City/Municipality", "type": "text"},
                {"name": "province", "label": "Province", "type": "text"},
                {"name": "zip_code", "label": "Zip Code", "type": "text"},
                {"name": "region", "label": "Region", "type": "text"},
                {"name": "mobile_number", "label": "Mobile Number", "type": "text"},
                {"name": "telephone_number", "label": "Telephone Number", "type": "text"},
                {"name": "email_address", "label": "Email Address", "type": "text"},
                {"name": "legal_spouse_name", "label": "Legal Spouse Name", "type": "text"},
                {"name": "legal_spouse_dob", "label": "Spouse Date of Birth", "type": "date"},
                {"name": "legal_spouse_dob", "label": "Spouse PhilHealth ID (if member)", "type": "text"},
                {"name": "child_1_name", "label": "Child 1 Name", "type": "text"},
                {"name": "child_1_dob", "label": "Child 1 Date of Birth", "type": "date"},
                {"name": "child_1_philhealth_id", "label": "Child 1 PhilHealth ID", "type": "text"},
                {"name": "child_2_name", "label": "Child 2 Name", "type": "text"},
                {"name": "child_2_dob", "label": "Child 2 Date of Birth", "type": "date"},
                {"name": "child_2_philhealth_id", "label": "Child 2 PhilHealth ID", "type": "text"},
                {"name": "child_3_name", "label": "Child 3 Name", "type": "text"},
                {"name": "child_3_dob", "label": "Child 3 Date of Birth", "type": "date"},
                {"name": "child_3_philhealth_id", "label": "Child 3 PhilHealth ID", "type": "text"},
                {"name": "child_4_name", "label": "Child 4 Name", "type": "text"},
                {"name": "child_4_dob", "label": "Child 4 Date of Birth", "type": "date"},
                {"name": "child_4_philhealth_id", "label": "Child 4 PhilHealth ID", "type": "text"},
                {"name": "start_period", "label": "Period Covered (From)", "type": "date"},
                {"name": "end_period", "label": "Period Covered (To)", "type": "date"},
                {"name": "payment_amount", "label": "Amount Paid", "type": "text"},
                {"name": "or_number", "label": "OR Number", "type": "text"},
            ]
        },
    },
    {
        "name": "Building Permit Application",
        "description": "Building Permit Application Form for construction, renovation, or demolition projects.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "Office of the Building Official",
            "title": "Building Permit Application Form",
            "sections": [
                {
                    "title": "A. APPLICANT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "owner_full_name", "label": "Property Owner's Full Name", "type": "text", "width": "full"},
                        {"name": "owner_address", "label": "Owner's Complete Address", "type": "text", "width": "full"},
                        {"name": "owner_contact_number", "label": "Contact Number", "type": "text", "width": "half"},
                        {"name": "owner_email", "label": "Email Address", "type": "text", "width": "half"},
                        {"name": "tin_number", "label": "TIN Number", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "B. PROJECT LOCATION",
                    "layout": "table",
                    "fields": [
                        {"name": "project_house_lot_no", "label": "House/Lot/Block No.", "type": "text", "width": "half"},
                        {"name": "project_street", "label": "Street", "type": "text", "width": "half"},
                        {"name": "project_barangay", "label": "Barangay", "type": "text", "width": "half"},
                        {"name": "project_city_municipality", "label": "City/Municipality", "type": "text", "width": "half"},
                        {"name": "project_province", "label": "Province", "type": "text", "width": "half"},
                        {"name": "project_region", "label": "Region", "type": "text", "width": "half"},
                        {"name": "project_lot_no", "label": "Lot No.", "type": "text", "width": "third"},
                        {"name": "project_block_no", "label": "Block No.", "type": "text", "width": "third"},
                        {"name": "project_tct_no", "label": "TCT/CCT No.", "type": "text", "width": "third"},
                    ]
                },
                {
                    "title": "C. BUILDING DATA",
                    "layout": "table",
                    "fields": [
                        {"name": "project_type", "label": "Type of Project", "type": "select", "width": "half", "options": ["New Building Construction", "Alteration/Repair", "Additional Building", "Demolition", "Renovation"]},
                        {"name": "use_classification", "label": "Use Classification", "type": "select", "width": "half", "options": ["Residential", "Commercial", "Industrial", "Institutional", "Agricultural", "Mixed Use"]},
                        {"name": "building_type", "label": "Type of Building", "type": "select", "width": "half", "options": ["Single Detached", "Duplex", "Townhouse", "Multi-Unit Residential", "Commercial Building", "Industrial Building"]},
                        {"name": "fire_resistive", "label": "Fire Resistive Group", "type": "select", "width": "half", "options": ["Group I", "Group II", "Group III", "Group IV", "Group V"]},
                        {"name": "total_floor_area", "label": "Total Floor Area (sqm)", "type": "number", "width": "half"},
                        {"name": "number_of_floors", "label": "Number of Floors/Storeys", "type": "number", "width": "half"},
                        {"name": "estimated_project_cost", "label": "Estimated Project Cost (PhP)", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "D. PROFESSIONALS IN CHARGE",
                    "layout": "table",
                    "fields": [
                        {"name": "architect_name", "label": "Name of Architect", "type": "text", "width": "full"},
                        {"name": "architect_prc_no", "label": "PRC License No.", "type": "text", "width": "half"},
                        {"name": "architect_ptr_no", "label": "PTR No.", "type": "text", "width": "half"},
                        {"name": "engineer_name", "label": "Name of Civil/Structural Engineer", "type": "text", "width": "full"},
                        {"name": "engineer_prc_no", "label": "PRC License No.", "type": "text", "width": "half"},
                        {"name": "engineer_ptr_no", "label": "PTR No.", "type": "text", "width": "half"},
                        {"name": "electrical_engineer_name", "label": "Name of Electrical Engineer", "type": "text", "width": "full"},
                        {"name": "sanitary_engineer_name", "label": "Name of Sanitary/Plumbing Engineer", "type": "text", "width": "full"},
                        {"name": "master_planner_name", "label": "Name of Master Planner/Architect", "type": "text", "width": "full"},
                        {"name": "master_planner_prc_no", "label": "PRC License No.", "type": "text", "width": "half"},
                        {"name": "master_planner_ptr_no", "label": "PTR No.", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "E. ATTACHED DOCUMENTS",
                    "layout": "table",
                    "fields": [
                        {"name": "doc_5_sets_plans", "label": "5 Sets of Building Plans", "type": "checkbox"},
                        {"name": "doc_2_sets_spec", "label": "2 Sets of Specifications", "type": "checkbox"},
                        {"name": "doc_bills_materials", "label": "Bill of Materials", "type": "checkbox"},
                        {"name": "doc_lot_plan", "label": "Lot Plan w/in 200m radius", "type": "checkbox"},
                        {"name": "doc_compute_cost", "label": "Form 2 - Computation of Fees", "type": "checkbox"},
                        {"name": "doc_clearance_bfire", "label": "Barangay Clearance", "type": "checkbox"},
                        {"name": "doc_fire_safety", "label": "Fire Safety evaluation", "type": "checkbox"},
                        {"name": "doc_cert_title", "label": "Certified True Copy of Title", "type": "checkbox"},
                        {"name": "doc_tax_declaration", "label": "Tax Declaration", "type": "checkbox"},
                        {"name": "doc_deed_sale", "label": "Deed of Absolute Sale", "type": "checkbox"},
                        {"name": "doc_pictures", "label": "Pictures of Location", "type": "checkbox"},
                        {"name": "doc_dti_cert", "label": "DTI Certificate (if commercial)", "type": "checkbox"},
                        {"name": "doc_sec_cert", "label": "SEC Certificate (if corporation)", "type": "checkbox"},
                        {"name": "doc_hazard_clearance", "label": "Geohazard Clearance", "type": "checkbox"},
                    ]
                },
                {
                    "title": "F. FEES & PAYMENT",
                    "layout": "table",
                    "fields": [
                        {"name": "building_permit_fee", "label": "Building Permit Fee", "type": "text", "width": "half"},
                        {"name": "occupancy_permit_fee", "label": "Occupancy Permit Fee", "type": "text", "width": "half"},
                        {"name": "inspection_fee", "label": "Inspection Fees", "type": "text", "width": "half"},
                        {"name": "sanitary_fee", "label": "Sanitary Permit Fee", "type": "text", "width": "half"},
                        {"name": "electrical_fee", "label": "Electrical Inspection Fee", "type": "text", "width": "half"},
                        {"name": "building_line_fee", "label": "Building Line Fee", "type": "text", "width": "half"},
                        {"name": "zoning_fee", "label": "Zoning Fee", "type": "text", "width": "half"},
                        {"name": "certificate_fee", "label": "Certificate of Completion Fee", "type": "text", "width": "half"},
                        {"name": "other_fees", "label": "Other Fees", "type": "text", "width": "half"},
                        {"name": "total_amount", "label": "Total Amount Due", "type": "text", "width": "half"},
                    ]
                },
            ],
            "footer": "I certify that all information and documents submitted are true and correct. I understand that any false statement will subject me to penalties under applicable laws and regulations.",
            "fields": [
                {"name": "owner_full_name", "label": "Property Owner's Full Name", "type": "text"},
                {"name": "owner_address", "label": "Owner's Complete Address", "type": "text"},
                {"name": "owner_contact_number", "label": "Contact Number", "type": "text"},
                {"name": "owner_email", "label": "Email Address", "type": "text"},
                {"name": "tin_number", "label": "TIN Number", "type": "text"},
                {"name": "project_house_lot_no", "label": "House/Lot/Block No.", "type": "text"},
                {"name": "project_street", "label": "Street", "type": "text"},
                {"name": "project_barangay", "label": "Barangay", "type": "text"},
                {"name": "project_city_municipality", "label": "City/Municipality", "type": "text"},
                {"name": "project_province", "label": "Province", "type": "text"},
                {"name": "project_region", "label": "Region", "type": "text"},
                {"name": "project_lot_no", "label": "Lot No.", "type": "text"},
                {"name": "project_block_no", "label": "Block No.", "type": "text"},
                {"name": "project_tct_no", "label": "TCT/CCT No.", "type": "text"},
                {"name": "project_type", "label": "Type of Project", "type": "select"},
                {"name": "use_classification", "label": "Use Classification", "type": "select"},
                {"name": "building_type", "label": "Type of Building", "type": "select"},
                {"name": "fire_resistive", "label": "Fire Resistive Group", "type": "select"},
                {"name": "total_floor_area", "label": "Total Floor Area (sqm)", "type": "number"},
                {"name": "number_of_floors", "label": "Number of Floors/Storeys", "type": "number"},
                {"name": "estimated_project_cost", "label": "Estimated Project Cost (PhP)", "type": "text"},
                {"name": "architect_name", "label": "Name of Architect", "type": "text"},
                {"name": "architect_prc_no", "label": "PRC License No.", "type": "text"},
                {"name": "architect_ptr_no", "label": "PTR No.", "type": "text"},
                {"name": "engineer_name", "label": "Name of Civil/Structural Engineer", "type": "text"},
                {"name": "engineer_prc_no", "label": "PRC License No.", "type": "text"},
                {"name": "engineer_ptr_no", "label": "PTR No.", "type": "text"},
                {"name": "electrical_engineer_name", "label": "Name of Electrical Engineer", "type": "text"},
                {"name": "sanitary_engineer_name", "label": "Name of Sanitary/Plumbing Engineer", "type": "text"},
                {"name": "master_planner_name", "label": "Name of Master Planner/Architect", "type": "text"},
                {"name": "master_planner_prc_no", "label": "PRC License No.", "type": "text"},
                {"name": "master_planner_ptr_no", "label": "PTR No.", "type": "text"},
                {"name": "doc_5_sets_plans", "label": "5 Sets of Building Plans", "type": "checkbox"},
                {"name": "doc_2_sets_spec", "label": "2 Sets of Specifications", "type": "checkbox"},
                {"name": "doc_bills_materials", "label": "Bill of Materials", "type": "checkbox"},
                {"name": "doc_lot_plan", "label": "Lot Plan w/in 200m radius", "type": "checkbox"},
                {"name": "doc_compute_cost", "label": "Form 2 - Computation of Fees", "type": "checkbox"},
                {"name": "doc_clearance_bfire", "label": "Barangay Clearance", "type": "checkbox"},
                {"name": "doc_fire_safety", "label": "Fire Safety evaluation", "type": "checkbox"},
                {"name": "doc_cert_title", "label": "Certified True Copy of Title", "type": "checkbox"},
                {"name": "doc_tax_declaration", "label": "Tax Declaration", "type": "checkbox"},
                {"name": "doc_deed_sale", "label": "Deed of Absolute Sale", "type": "checkbox"},
                {"name": "doc_pictures", "label": "Pictures of Location", "type": "checkbox"},
                {"name": "doc_dti_cert", "label": "DTI Certificate (if commercial)", "type": "checkbox"},
                {"name": "doc_sec_cert", "label": "SEC Certificate (if corporation)", "type": "checkbox"},
                {"name": "doc_hazard_clearance", "label": "Geohazard Clearance", "type": "checkbox"},
                {"name": "building_permit_fee", "label": "Building Permit Fee", "type": "text"},
                {"name": "occupancy_permit_fee", "label": "Occupancy Permit Fee", "type": "text"},
                {"name": "inspection_fee", "label": "Inspection Fees", "type": "text"},
                {"name": "sanitary_fee", "label": "Sanitary Permit Fee", "type": "text"},
                {"name": "electrical_fee", "label": "Electrical Inspection Fee", "type": "text"},
                {"name": "building_line_fee", "label": "Building Line Fee", "type": "text"},
                {"name": "zoning_fee", "label": "Zoning Fee", "type": "text"},
                {"name": "certificate_fee", "label": "Certificate of Completion Fee", "type": "text"},
                {"name": "other_fees", "label": "Other Fees", "type": "text"},
                {"name": "total_amount", "label": "Total Amount Due", "type": "text"},
            ]
        },
    },
    {
        "name": "Real Property Tax Declaration",
        "description": "Real Property Tax Declaration Form for declaring land, building, and machinery ownership for taxation purposes.",
        "field_schema": {
            "header": "Republic of the Philippines",
            "subheader": "Provincial/City Assessor's Office",
            "title": "Real Property Tax Declaration",
            "sections": [
                {
                    "title": "A. DECLARANT INFORMATION",
                    "layout": "table",
                    "fields": [
                        {"name": "declarant_name", "label": "Full Name of Declarant", "type": "text", "width": "full"},
                        {"name": "address", "label": "Complete Address", "type": "text", "width": "full"},
                        {"name": "contact_number", "label": "Contact Number", "type": "text", "width": "half"},
                        {"name": "tin", "label": "Tax Identification Number (TIN)", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "B. PROPERTY LOCATION",
                    "layout": "table",
                    "fields": [
                        {"name": "property_lot_no", "label": "Lot No.", "type": "text", "width": "half"},
                        {"name": "property_block_no", "label": "Block No.", "type": "text", "width": "half"},
                        {"name": "property_street", "label": "Street", "type": "text", "width": "half"},
                        {"name": "property_barangay", "label": "Barangay", "type": "text", "width": "half"},
                        {"name": "property_city_municipality", "label": "City/Municipality", "type": "text", "width": "half"},
                        {"name": "property_province", "label": "Province", "type": "text", "width": "half"},
                        {"name": "property_region", "label": "Region", "type": "text", "width": "half"},
                        {"name": "tct_cct_no", "label": "TCT/CCT No.", "type": "text", "width": "half"},
                        {"name": "tct_date_issued", "label": "TCT Date Issued", "type": "date", "width": "half"},
                    ]
                },
                {
                    "title": "C. PROPERTY CLASSIFICATION",
                    "layout": "table",
                    "fields": [
                        {"name": "property_classification", "label": "Property Classification", "type": "select", "width": "full", "options": ["Residential", "Agricultural", "Commercial", "Industrial", "Mineral", "Timber", "Special", "Hospital/Educational", "Charitable Institution"]},
                        {"name": "property_kind", "label": "Kind of Property", "type": "checkbox-group", "width": "full", "options": ["Land", "Land & Building", "Land, Building & Machinery", "Machinery Only"]},
                        {"name": "actual_use", "label": "Actual Use", "type": "select", "width": "full", "options": ["Residential", "Commercial", "Industrial", "Agricultural", "Leasehold", "Recreational", "Other"]},
                        {"name": "tax_exempt", "label": "Tax Exemption Status", "type": "select", "width": "half", "options": ["None", "Government", "Religious", "Charitable", "Educational", "Other"]},
                        {"name": "exemption_code", "label": "Exemption Code (if applicable)", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "D. LAND DETAILS",
                    "layout": "table",
                    "fields": [
                        {"name": "land_area_hectares", "label": "Area (in Hectares)", "type": "text", "width": "half"},
                        {"name": "land_area_sqm", "label": "Area (in Sqm)", "type": "text", "width": "half"},
                        {"name": "land_perimeter", "label": "Perimeter (Linear Meters)", "type": "text", "width": "half"},
                        {"name": "land_boundaries_north", "label": "North Boundary", "type": "text", "width": "full"},
                        {"name": "land_boundaries_south", "label": "South Boundary", "type": "text", "width": "full"},
                        {"name": "land_boundaries_east", "label": "East Boundary", "type": "text", "width": "full"},
                        {"name": "land_boundaries_west", "label": "West Boundary", "type": "text", "width": "full"},
                    ]
                },
                {
                    "title": "E. ASSESSMENT DETAILS",
                    "layout": "table",
                    "fields": [
                        {"name": "market_value", "label": "Market Value", "type": "text", "width": "half"},
                        {"name": "assessment_level", "label": "Assessment Level (%)", "type": "text", "width": "half"},
                        {"name": "assessed_value", "label": "Assessed Value", "type": "text", "width": "half"},
                        {"name": "assessment_effective", "label": "Effective Year of Assessment", "type": "number", "width": "half"},
                        {"name": "total_current_rpt", "label": "Total Current Real Property Tax Due", "type": "text", "width": "half"},
                    ]
                },
                {
                    "title": "F. OWNER'S TAXPAYER INFO",
                    "layout": "table",
                    "fields": [
                        {"name": "owner_name", "label": "Registered Owner Name", "type": "text", "width": "full"},
                        {"name": "owner_address", "label": "Owner's Mailing Address", "type": "text", "width": "full"},
                        {"name": "owner_taxpayer_id", "label": "Taxpayer ID / RPT Account No.", "type": "text", "width": "half"},
                    ]
                },
            ],
            "footer": "I hereby certify that the information stated in this declaration is true and correct to the best of my knowledge and belief.",
            "fields": [
                {"name": "declarant_name", "label": "Full Name of Declarant", "type": "text"},
                {"name": "address", "label": "Complete Address", "type": "text"},
                {"name": "contact_number", "label": "Contact Number", "type": "text"},
                {"name": "tin", "label": "Tax Identification Number (TIN)", "type": "text"},
                {"name": "property_lot_no", "label": "Lot No.", "type": "text"},
                {"name": "property_block_no", "label": "Block No.", "type": "text"},
                {"name": "property_street", "label": "Street", "type": "text"},
                {"name": "property_barangay", "label": "Barangay", "type": "text"},
                {"name": "property_city_municipality", "label": "City/Municipality", "type": "text"},
                {"name": "property_province", "label": "Province", "type": "text"},
                {"name": "property_region", "label": "Region", "type": "text"},
                {"name": "tct_cct_no", "label": "TCT/CCT No.", "type": "text"},
                {"name": "tct_date_issued", "label": "TCT Date Issued", "type": "date"},
                {"name": "property_classification", "label": "Property Classification", "type": "select"},
                {"name": "property_kind", "label": "Kind of Property", "type": "checkbox-group"},
                {"name": "actual_use", "label": "Actual Use", "type": "select"},
                {"name": "tax_exempt", "label": "Tax Exemption Status", "type": "select"},
                {"name": "exemption_code", "label": "Exemption Code (if applicable)", "type": "text"},
                {"name": "land_area_hectares", "label": "Area (in Hectares)", "type": "text"},
                {"name": "land_area_sqm", "label": "Area (in Sqm)", "type": "text"},
                {"name": "land_perimeter", "label": "Perimeter (Linear Meters)", "type": "text"},
                {"name": "land_boundaries_north", "label": "North Boundary", "type": "text"},
                {"name": "land_boundaries_south", "label": "South Boundary", "type": "text"},
                {"name": "land_boundaries_east", "label": "East Boundary", "type": "text"},
                {"name": "land_boundaries_west", "label": "West Boundary", "type": "text"},
                {"name": "market_value", "label": "Market Value", "type": "text"},
                {"name": "assessment_level", "label": "Assessment Level (%)", "type": "text"},
                {"name": "assessed_value", "label": "Assessed Value", "type": "text"},
                {"name": "assessment_effective", "label": "Effective Year of Assessment", "type": "number"},
                {"name": "total_current_rpt", "label": "Total Current Real Property Tax Due", "type": "text"},
                {"name": "owner_name", "label": "Registered Owner Name", "type": "text"},
                {"name": "owner_address", "label": "Owner's Mailing Address", "type": "text"},
                {"name": "owner_taxpayer_id", "label": "Taxpayer ID / RPT Account No.", "type": "text"},
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
            normalized_schema = normalize_template_schema(tmpl["field_schema"])
            result = await db.execute(
                select(FormTemplate).where(FormTemplate.name == tmpl["name"])
            )
            existing = result.scalar_one_or_none()

            if existing is None:
                template = FormTemplate(
                    name=tmpl["name"],
                    description=tmpl["description"],
                    field_schema=normalized_schema,
                )
                db.add(template)
                print(f"✅ Template created: {tmpl['name']}")
            else:
                existing.field_schema = normalized_schema
                existing.description = tmpl["description"]
                print(f"🔄 Template updated: {tmpl['name']}")

        await db.commit()

    await engine.dispose()
    print("\n🎉 Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
