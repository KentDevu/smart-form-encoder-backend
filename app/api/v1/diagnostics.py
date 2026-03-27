"""
Diagnostics API for OCR Confidence Analysis

This module provides REST endpoints to diagnose OCR extraction confidence,
identify bottlenecks, and measure improvement across the enhancement phases.

Endpoints:
- GET /api/v1/diagnostics/confidence-report       - Overall confidence metrics
- GET /api/v1/diagnostics/template-analysis       - Per-template breakdown
- GET /api/v1/diagnostics/field-analysis          - Per-field correction rates
- GET /api/v1/diagnostics/low-confidence-fields   - Fields with <0.7 confidence
- GET /api/v1/diagnostics/image-quality-impact    - Correlation with image properties
- GET /api/v1/diagnostics/confidence-distribution - Histogram by bin
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/diagnostics", tags=["ml_diagnostics"])


@router.get("/confidence-report")
async def get_confidence_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="Days to analyze (1-365)"),
) -> ApiResponse:
    """
    Get overall OCR confidence metrics for the specified time period.
    
    Returns:
    - system_confidence: Overall average confidence (0.0-1.0)
    - total_entries: Number of entries analyzed
    - confidence_distribution: Histogram by bin
    - median_confidence: 50th percentile
    - p25 / p75: 25th and 75th percentiles
    """
    try:
        query = text("""
            SELECT 
              ROUND(AVG(confidence_score)::numeric, 4) as system_confidence,
              ROUND(MEDIAN(confidence_score)::numeric, 4) as median_confidence,
              ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY confidence_score)::numeric, 4) as p25,
              ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY confidence_score)::numeric, 4) as p75,
              ROUND(MIN(confidence_score)::numeric, 4) as min_confidence,
              ROUND(MAX(confidence_score)::numeric, 4) as max_confidence,
              COUNT(*) as total_entries,
              COUNT(CASE WHEN confidence_score < 0.3 THEN 1 END) as very_low_count,
              COUNT(CASE WHEN confidence_score >= 0.3 AND confidence_score < 0.7 THEN 1 END) as low_count,
              COUNT(CASE WHEN confidence_score >= 0.7 AND confidence_score < 0.85 THEN 1 END) as medium_count,
              COUNT(CASE WHEN confidence_score >= 0.85 AND confidence_score < 0.95 THEN 1 END) as high_count,
              COUNT(CASE WHEN confidence_score >= 0.95 THEN 1 END) as very_high_count
            FROM form_entries
            WHERE created_at > NOW() - INTERVAL '{{days}} days'
              AND status IN ('EXTRACTED', 'VERIFIED')
        """.replace("{days}", str(days)))

        result = db.execute(query).mappings().first()
        
        if not result:
            return ApiResponse(
                success=True,
                data={
                    "message": "No data available for the specified period",
                    "period_days": days,
                },
            )

        return ApiResponse(
            success=True,
            data={
                "system_confidence": float(result["system_confidence"]),
                "median_confidence": float(result["median_confidence"]),
                "percentile_25": float(result["p25"]),
                "percentile_75": float(result["p75"]),
                "min_confidence": float(result["min_confidence"]),
                "max_confidence": float(result["max_confidence"]),
                "total_entries": int(result["total_entries"]),
                "distribution": {
                    "very_low_0_0_to_0_3": int(result["very_low_count"]),
                    "low_0_3_to_0_7": int(result["low_count"]),
                    "medium_0_7_to_0_85": int(result["medium_count"]),
                    "high_0_85_to_0_95": int(result["high_count"]),
                    "very_high_0_95_to_1_0": int(result["very_high_count"]),
                },
                "analyzed_period_days": days,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostics query failed: {str(e)}")


@router.get("/template-analysis")
async def get_template_analysis(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
) -> ApiResponse:
    """
    Get per-template confidence analysis.
    
    Returns: List of templates with their confidence metrics and variance.
    """
    try:
        query = text("""
            SELECT 
              ft.id as template_id,
              ft.name as template_name,
              COUNT(fe.id) as total_entries,
              ROUND(AVG(fe.confidence_score)::numeric, 4) as avg_confidence,
              ROUND(STDDEV(fe.confidence_score)::numeric, 4) as stddev_confidence,
              ROUND(MIN(fe.confidence_score)::numeric, 4) as min_confidence,
              ROUND(MAX(fe.confidence_score)::numeric, 4) as max_confidence,
              ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fe.confidence_score)::numeric, 4) as median_confidence
            FROM form_entries fe
            JOIN form_templates ft ON fe.template_id = ft.id
            WHERE fe.created_at > NOW() - INTERVAL '{{days}} days'
              AND fe.status IN ('EXTRACTED', 'VERIFIED')
            GROUP BY ft.id, ft.name
            ORDER BY avg_confidence ASC
        """.replace("{days}", str(days)))

        results = db.execute(query).mappings().fetchall()
        
        templates = [
            {
                "template_id": str(row["template_id"]),
                "template_name": row["template_name"],
                "total_entries": int(row["total_entries"]),
                "avg_confidence": float(row["avg_confidence"]),
                "stddev_confidence": float(row["stddev_confidence"]) if row["stddev_confidence"] else None,
                "min_confidence": float(row["min_confidence"]),
                "max_confidence": float(row["max_confidence"]),
                "median_confidence": float(row["median_confidence"]),
            }
            for row in results
        ]

        return ApiResponse(
            success=True,
            data={
                "templates": templates,
                "total_templates": len(templates),
                "analyzed_period_days": days,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template analysis query failed: {str(e)}")


@router.get("/field-analysis")
async def get_field_analysis(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    sort_by: str = Query("correction_rate", regex="^(correction_rate|avg_confidence|field_name)$"),
) -> ApiResponse:
    """
    Get per-field confidence and correction rate analysis.
    
    Returns: List of fields sorted by correction rate (highest first).
    """
    try:
        order_clause = {
            "correction_rate": "correction_rate_pct DESC",
            "avg_confidence": "avg_field_confidence ASC",
            "field_name": "field_name ASC",
        }.get(sort_by, "correction_rate_pct DESC")

        query = text(f"""
            SELECT 
              field_name,
              COUNT(*) as total_instances,
              ROUND(AVG(confidence)::numeric, 4) as avg_field_confidence,
              COUNT(CASE WHEN was_corrected THEN 1 END) as correction_count,
              ROUND(100.0 * COUNT(CASE WHEN was_corrected THEN 1 END) / COUNT(*)::numeric, 2) as correction_rate_pct,
              ROUND(AVG(CASE WHEN confidence < 0.7 THEN 1 ELSE 0 END) * 100::numeric, 2) as low_conf_pct,
              ROUND(MIN(confidence)::numeric, 4) as min_confidence,
              ROUND(MAX(confidence)::numeric, 4) as max_confidence
            FROM form_fields
            WHERE created_at > NOW() - INTERVAL '{{days}} days'
            GROUP BY field_name
            ORDER BY {order_clause}
        """.replace("{days}", str(days)))

        results = db.execute(query).mappings().fetchall()
        
        fields = [
            {
                "field_name": row["field_name"],
                "total_instances": int(row["total_instances"]),
                "avg_confidence": float(row["avg_field_confidence"]),
                "correction_count": int(row["correction_count"]),
                "correction_rate_pct": float(row["correction_rate_pct"]),
                "low_confidence_pct": float(row["low_conf_pct"]),
                "min_confidence": float(row["min_confidence"]),
                "max_confidence": float(row["max_confidence"]),
            }
            for row in results
        ]

        return ApiResponse(
            success=True,
            data={
                "fields": fields,
                "total_fields": len(fields),
                "sorted_by": sort_by,
                "analyzed_period_days": days,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Field analysis query failed: {str(e)}")


@router.get("/low-confidence-fields")
async def get_low_confidence_fields(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Confidence threshold"),
) -> ApiResponse:
    """
    Get fields with confidence below threshold (default 0.7).
    
    Returns: Problem fields that likely need fixes.
    """
    try:
        query = text(f"""
            SELECT 
              field_name,
              ROUND(AVG(confidence)::numeric, 4) as avg_confidence,
              COUNT(*) as occurrences,
              COUNT(CASE WHEN was_corrected THEN 1 END) as corrections,
              ROUND(100.0 * COUNT(CASE WHEN was_corrected THEN 1 END) / COUNT(*)::numeric, 1) as correction_rate_pct
            FROM form_fields
            WHERE confidence < {{threshold}} 
              AND created_at > NOW() - INTERVAL '{{days}} days'
            GROUP BY field_name
            ORDER BY correction_rate_pct DESC, avg_confidence ASC
        """.replace("{threshold}", str(threshold)).replace("{days}", str(days)))

        results = db.execute(query).mappings().fetchall()
        
        low_conf_fields = [
            {
                "field_name": row["field_name"],
                "avg_confidence": float(row["avg_confidence"]),
                "total_occurrences": int(row["occurrences"]),
                "corrected_count": int(row["corrections"]),
                "correction_rate_pct": float(row["correction_rate_pct"]),
            }
            for row in results
        ]

        return ApiResponse(
            success=True,
            data={
                "low_confidence_threshold": threshold,
                "fields": low_conf_fields,
                "total_low_conf_fields": len(low_conf_fields),
                "analyzed_period_days": days,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Low confidence fields query failed: {str(e)}")


@router.get("/image-quality-impact")
async def get_image_quality_impact(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
) -> ApiResponse:
    """
    Analyze correlation between image properties and OCR confidence.
    
    Returns: Confidence grouped by line count and processing time.
    """
    try:
        query = text("""
            SELECT 
              (raw_ocr_data->>'raw_lines_count')::int as line_count,
              ROUND(confidence_score::numeric, 1) as confidence_bin,
              COUNT(*) as entry_count,
              ROUND(AVG(CAST(raw_ocr_data->>'processing_time' AS FLOAT))::numeric, 2) as avg_processing_time_s,
              ROUND(MIN(CAST(raw_ocr_data->>'processing_time' AS FLOAT))::numeric, 2) as min_time_s,
              ROUND(MAX(CAST(raw_ocr_data->>'processing_time' AS FLOAT))::numeric, 2) as max_time_s
            FROM form_entries
            WHERE created_at > NOW() - INTERVAL '{{days}} days'
              AND raw_ocr_data IS NOT NULL
              AND status IN ('EXTRACTED', 'VERIFIED')
            GROUP BY line_count, confidence_bin
            ORDER BY line_count DESC, confidence_bin ASC
        """.replace("{days}", str(days)))

        results = db.execute(query).mappings().fetchall()
        
        impact_data = [
            {
                "line_count": int(row["line_count"]) if row["line_count"] else None,
                "confidence_bin": float(row["confidence_bin"]) if row["confidence_bin"] else None,
                "entry_count": int(row["entry_count"]),
                "avg_processing_time_s": float(row["avg_processing_time_s"]) if row["avg_processing_time_s"] else None,
                "min_processing_time_s": float(row["min_time_s"]) if row["min_time_s"] else None,
                "max_processing_time_s": float(row["max_time_s"]) if row["max_time_s"] else None,
            }
            for row in results
        ]

        return ApiResponse(
            success=True,
            data={
                "image_quality_impact": impact_data,
                "total_correlation_points": len(impact_data),
                "analyzed_period_days": days,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image quality impact query failed: {str(e)}")


@router.get("/confidence-distribution")
async def get_confidence_distribution(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
) -> ApiResponse:
    """
    Get distribution of confidence scores in histogram format.
    
    Returns: Count and percentage in each confidence bin.
    """
    try:
        query = text("""
            WITH total AS (
              SELECT COUNT(*) as cnt FROM form_entries 
              WHERE created_at > NOW() - INTERVAL '{{days}} days'
                AND status IN ('EXTRACTED', 'VERIFIED')
            )
            SELECT 
              CASE 
                WHEN confidence_score < 0.3 THEN '0.0-0.3 (Very Low)'
                WHEN confidence_score < 0.7 THEN '0.3-0.7 (Low)'
                WHEN confidence_score < 0.85 THEN '0.7-0.85 (Medium)'
                WHEN confidence_score < 0.95 THEN '0.85-0.95 (High)'
                ELSE '0.95-1.0 (Very High)'
              END as confidence_bin,
              COUNT(*) as entry_count,
              ROUND(100.0 * COUNT(*) / (SELECT cnt FROM total)::numeric, 1) as percentage
            FROM form_entries
            WHERE created_at > NOW() - INTERVAL '{{days}} days'
              AND status IN ('EXTRACTED', 'VERIFIED')
            GROUP BY confidence_bin
            ORDER BY 
              CASE confidence_bin
                WHEN '0.0-0.3 (Very Low)' THEN 1
                WHEN '0.3-0.7 (Low)' THEN 2
                WHEN '0.7-0.85 (Medium)' THEN 3
                WHEN '0.85-0.95 (High)' THEN 4
                WHEN '0.95-1.0 (Very High)' THEN 5
              END
        """.replace("{days}", str(days)))

        results = db.execute(query).mappings().fetchall()
        
        distribution = [
            {
                "confidence_bin": row["confidence_bin"],
                "entry_count": int(row["entry_count"]),
                "percentage": float(row["percentage"]),
            }
            for row in results
        ]

        return ApiResponse(
            success=True,
            data={
                "distribution": distribution,
                "total_entries": sum(d["entry_count"] for d in distribution),
                "analyzed_period_days": days,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Confidence distribution query failed: {str(e)}")
