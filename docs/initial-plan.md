# Catalyx SmartForm Encoder

AI-Assisted Handwritten Form Digitization System

## 1. Executive Summary

Catalyx SmartForm Encoder is an AI-assisted system designed to digitize handwritten paper
forms used in City Hall operations.
The system scans handwritten forms, extracts probable field values using OCR and AI,
presents suggested data side-by-side with the form image for human verification, saves
structured data to a database, and automatically generates reports.
This ensures 70–90% faster encoding, near 100% final accuracy, and eliminates operational
risk from full automation errors.

## 2. Problem Statement

Current manual encoding workflow causes delays, typing errors, overtime workload, and
operational inefficiencies.
Paper-based systems create reporting bottlenecks and increase administrative costs.

## 3. Proposed Solution

An AI-assisted encoding system where automation suggests extracted data and humans
verify before saving.
Core principle: Automation suggests. Humans confirm.

## 4. System Architecture Overview

Workflow:

1. Staff scans form (mobile or scanner)
2. Image preprocessing (crop, deskew, noise reduction)
3. OCR and AI field extraction
4. Field mapping to structured schema
5. Side-by-side verification interface
6. Human correction if needed
7. Save to database
8. Auto-report generation

## 5. Detailed Workflow

Step 1 – Form Scanning

- Upload via phone camera or scanner


- Supports JPG, PNG, PDF
Step 2 – OCR + AI Extraction
- Detect form template
- Identify field regions
- Extract text
- Map to structured fields
- Generate confidence score per field
Step 3 – Verification Interface
- Left: scanned image
- Right: editable auto-filled form
- Low-confidence fields highlighted
- Encoder reviews and confirms
Step 4 – Database Storage
- Structured storage with audit logs
- Image URL reference
- Timestamped entries
Step 5 – Reporting Module
- Daily and monthly reports
- CSV and PDF export
- Filtering by department and date

## 6. System Components

Frontend:

- Web-based dashboard
- Encoder and Admin roles
- Responsive UI
Backend:
- API server
- OCR processing queue
- Database layer
- Report generator
Storage:
- Secure object storage
- Encrypted at rest

## 7. Security & Compliance

- HTTPS encryption
- Role-based authentication


- Audit logging
- Encrypted storage
- Backup system
- Data retention policies
- Compliance with Philippine Data Privacy Act

## 8. Performance Targets

- OCR extraction time: < 5 seconds
- Verification time: < 30 seconds per form
- Accuracy before correction: 70–85%
- Final accuracy after correction: Near 100%
- System uptime target: 99%

## 9. Implementation Roadmap

Phase 1 – MVP (2–4 weeks)

- Upload and OCR extraction
- Basic verification UI
- Save to DB
- CSV export
Phase 2 – Production
- Template detection
- Confidence scoring
- Reporting dashboard
- Role-based access
- Security hardening
Phase 3 – Advanced Features
- Template learning
- Multi-department support
- Analytics dashboard

## 10. Deployment Model

Option A – Cloud Hosted

- Subscription-based
- Lower upfront cost
Option B – On-Premise
- One-time license
- Maintenance contract

## 11. Success Metrics

- Reduced encoding time
- Reduced overtime


- Faster reporting
- Improved data accuracy
- Staff satisfaction

## 12. Future Expansion

- Business permits digitization
- Health office records
- Event registration systems
- Barangay-level deployments
- Full LGU digital operations suite


