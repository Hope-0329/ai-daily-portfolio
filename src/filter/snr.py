"""信噪比（SNR）指标计算。"""

from __future__ import annotations


def calculate_snr(
    raw_count: int,
    l1_count: int,
    l2_count: int,
    l2_high_quality_count: int | None = None,
) -> dict[str, float]:
    """
    计算多层 SNR 指标。

    raw_count: 原始拉取的文章数
    l1_count: L1 规则过滤后的数量
    l2_count: L2 LLM 精选后的数量
    l2_high_quality_count: L2 中 score >= 80 的数量
    """
    if l2_high_quality_count is None:
        l2_high_quality_count = 0

    filter_efficiency = round(l2_count / raw_count, 3) if raw_count else 0.0
    l1_pass_rate = round(l1_count / raw_count, 3) if raw_count else 0.0
    l2_quality = round(l2_high_quality_count / l2_count, 3) if l2_count else 0.0

    return {
        # 新指标（Phase 9）
        "filter_efficiency": filter_efficiency,
        "l1_pass_rate": l1_pass_rate,
        "l2_quality": l2_quality,
        # 兼容旧字段名
        "raw_to_l1_ratio": l1_pass_rate,
        "l1_to_l2_ratio": round(l2_count / l1_count, 3) if l1_count else 0.0,
        "overall_snr": filter_efficiency,
        "quality_rate": l2_quality,
    }
